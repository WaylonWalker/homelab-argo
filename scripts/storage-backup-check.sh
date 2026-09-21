#!/usr/bin/env bash
set -euo pipefail

# This script only reads Kubernetes resources and sends read-only S3 requests.
# It never creates a backup, restores a volume, or changes a cluster resource.

longhorn_namespace="${LONGHORN_NAMESPACE:-longhorn-system}"
object_store_namespace="${BACKUP_OBJECT_STORE_NAMESPACE:-${BACKUP_MINIO_NAMESPACE:-minio-longhorn-backup}}"
object_store_service="${BACKUP_OBJECT_STORE_SERVICE:-${BACKUP_MINIO_SERVICE:-minio-longhorn-backup}}"
backup_secret="${LONGHORN_BACKUP_SECRET:-minio-longhorn-backup-secret}"
backup_age_hours="${LONGHORN_BACKUP_MAX_AGE_HOURS:-30}"
s3_mode="${STORAGE_BACKUP_CHECK_S3:-auto}"
service_dns="${object_store_service}.${object_store_namespace}.svc.cluster.local"
expected_endpoint="${BACKUP_OBJECT_STORE_ENDPOINT:-${BACKUP_MINIO_ENDPOINT:-http://${service_dns}:9000}}"

longhorn_access_key=""
longhorn_secret_key=""
longhorn_endpoint=""
longhorn_bucket=""
longhorn_region=""
backup_target_url=""
target_bucket=""

failures=0

pass_message() {
  printf 'PASS: %s\n' "$1"
}

info_message() {
  printf 'INFO: %s\n' "$1"
}

warn_message() {
  printf 'WARN: %s\n' "$1" >&2
}

fail_message() {
  printf 'FAIL: %s\n' "$1" >&2
  failures=$((failures + 1))
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail_message "required command is not installed: $1"
  fi
}

secret_value() {
  local secret_json="$1"
  local key="$2"

  jq -r --arg key "$key" '.data[$key] // empty' <<<"$secret_json" | base64 --decode
}

secret_has_key() {
  local secret_json="$1"
  local key="$2"

  jq -e --arg key "$key" '.data[$key] != null' <<<"$secret_json" >/dev/null
}

latest_completed_timestamp() {
  jq -r '
    [
      .items[]
      | select((.status.state // "" | ascii_upcase) == "COMPLETED")
      | (.status.completionTime // .status.completedAt // .metadata.creationTimestamp)
    ]
    | map(select(. != null))
    | max // empty
  ' <<<"$1"
}

printf 'Longhorn backup diagnostic (read-only)\n'
printf 'S3-compatible backup object store namespace: %s\n' "$object_store_namespace"
printf 'Backup age limit: %s hours\n' "$backup_age_hours"
printf 'Expected S3 endpoint: %s\n' "$expected_endpoint"
printf 'DIAGNOSTIC ONLY: this command does not create a backup or prove a restore.\n'
printf 'The backup safety gate requires a new backup and a disposable restore with a matching sentinel.\n'

require_command kubectl
require_command jq
require_command base64

if ! [[ "$backup_age_hours" =~ ^[0-9]+$ ]]; then
  fail_message "LONGHORN_BACKUP_MAX_AGE_HOURS must be a non-negative integer"
fi

case "$s3_mode" in
  auto|always|never) ;;
  *) fail_message "STORAGE_BACKUP_CHECK_S3 must be auto, always, or never" ;;
esac

if (( failures > 0 )); then
  exit 2
fi

if ! kubectl get namespace "$longhorn_namespace" >/dev/null 2>&1; then
  fail_message "namespace does not exist: $longhorn_namespace"
fi

if ! kubectl get namespace "$object_store_namespace" >/dev/null 2>&1; then
  fail_message "namespace does not exist: $object_store_namespace"
fi

service_json=""
if service_json="$(kubectl get service "$object_store_service" -n "$object_store_namespace" -o json 2>/dev/null)"; then
  if jq -e '.spec.ports[]? | select(.port == 9000)' <<<"$service_json" >/dev/null; then
    pass_message "S3-compatible object-store Service exposes port 9000"
  else
    fail_message "object-store Service does not expose port 9000"
  fi
else
  fail_message "object-store Service is not readable: $object_store_namespace/$object_store_service"
fi

endpoint_count=0
if endpoint_json="$(kubectl get endpoints "$object_store_service" -n "$object_store_namespace" -o json 2>/dev/null)"; then
  endpoint_count="$(jq '[.subsets[]?.addresses[]?] | length' <<<"$endpoint_json")"
fi

if (( endpoint_count > 0 )); then
  pass_message "object-store Service has $endpoint_count ready endpoint address(es)"
else
  endpoint_slice_count=0
  if endpoint_slice_json="$(kubectl get endpointslices.discovery.k8s.io \
    -n "$object_store_namespace" \
    -l "kubernetes.io/service-name=$object_store_service" \
    -o json 2>/dev/null)"; then
    endpoint_slice_count="$(jq '[.items[].endpoints[]? | select(any(.conditions[]?; .ready == true))] | length' <<<"$endpoint_slice_json")"
  fi
  if (( endpoint_slice_count > 0 )); then
    pass_message "object-store Service has $endpoint_slice_count ready EndpointSlice address(es)"
  else
    fail_message "object-store Service has no ready endpoint addresses"
  fi
fi

object_store_pods_json=""
if object_store_pods_json="$(kubectl get pods -n "$object_store_namespace" -l "service=$object_store_service" -o json 2>/dev/null)"; then
  ready_pod_count="$(jq '[.items[] | select(any(.status.conditions[]?; .type == "Ready" and .status == "True"))] | length' <<<"$object_store_pods_json")"
  if (( ready_pod_count > 0 )); then
    pass_message "object store has $ready_pod_count Ready pod(s)"
    object_store_pod="$(jq -r '[.items[] | select(any(.status.conditions[]?; .type == "Ready" and .status == "True")) | .metadata.name] | first // empty' <<<"$object_store_pods_json")"
    health_status=0
    kubectl exec -n "$object_store_namespace" "$object_store_pod" -c minio-longhorn-backup -- \
      env "SERVICE_DNS=$service_dns" sh -c '
        if command -v wget >/dev/null 2>&1; then
          wget -q -O /dev/null "http://${SERVICE_DNS}:9000/minio/health/ready"
        elif command -v curl >/dev/null 2>&1; then
          curl --fail --silent --show-error "http://${SERVICE_DNS}:9000/minio/health/ready" >/dev/null
        else
          exit 125
        fi
      ' >/dev/null 2>&1 || health_status=$?
    if (( health_status == 0 )); then
      pass_message "object-store Service DNS and readiness endpoint work from the object-store pod"
    elif (( health_status == 125 )); then
      warn_message "object-store pod has neither wget nor curl; Service HTTP reachability was not tested"
    else
      fail_message "object-store Service DNS or readiness endpoint failed from the object-store pod"
    fi
  else
    fail_message "object store has no Ready pod"
  fi
else
  fail_message "object-store pods are not readable"
fi

longhorn_secret_json=""
object_store_secret_json=""
if longhorn_secret_json="$(kubectl get secret "$backup_secret" -n "$longhorn_namespace" -o json 2>/dev/null)"; then
  pass_message "Longhorn backup Secret exists: $longhorn_namespace/$backup_secret"
else
  fail_message "Longhorn backup Secret is not readable: $longhorn_namespace/$backup_secret"
fi

if object_store_secret_json="$(kubectl get secret "$backup_secret" -n "$object_store_namespace" -o json 2>/dev/null)"; then
  pass_message "object-store Secret exists: $object_store_namespace/$backup_secret"
else
  fail_message "object-store Secret is not readable: $object_store_namespace/$backup_secret"
fi

required_longhorn_keys=(
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_BUCKET
  AWS_BUCKET_NAME
  AWS_ENDPOINT_URL
  AWS_ENDPOINTS
  AWS_REGION
)
required_object_store_keys=(MINIO_ROOT_USER MINIO_ROOT_PASSWORD)

if [[ -n "$longhorn_secret_json" ]]; then
  for key in "${required_longhorn_keys[@]}"; do
    if secret_has_key "$longhorn_secret_json" "$key"; then
      pass_message "Longhorn Secret contains key: $key"
    else
      fail_message "Longhorn Secret is missing key: $key"
    fi
  done
fi

if [[ -n "$object_store_secret_json" ]]; then
  for key in "${required_object_store_keys[@]}"; do
    if secret_has_key "$object_store_secret_json" "$key"; then
      pass_message "object-store Secret contains key: $key"
    else
      fail_message "object-store Secret is missing key: $key"
    fi
  done
fi

backup_target_json=""
target_credential_secret=""
if backup_target_json="$(kubectl get backuptargets.longhorn.io/default -n "$longhorn_namespace" -o json 2>/dev/null)"; then
  backup_target_url="$(jq -r '.spec.backupTargetURL // empty' <<<"$backup_target_json")"
  target_credential_secret="$(jq -r '.spec.credentialSecret // empty' <<<"$backup_target_json")"
  available="$(jq -r 'if .status.available == true or any(.status.conditions[]?; .type == "Available" and .status == "True") then "true" else "false" end' <<<"$backup_target_json")"
  unavailable_reason="$(jq -r '[.status.conditions[]? | select(.type == "Unavailable" and .status == "True") | .reason] | first // empty' <<<"$backup_target_json")"
  if [[ -z "$backup_target_url" ]]; then
    fail_message "Longhorn BackupTarget has no backupTargetURL"
  else
    pass_message "Longhorn BackupTarget resource exists"
    target_bucket="${backup_target_url#s3://}"
    target_bucket="${target_bucket%%@*}"
  fi
  if [[ "$target_credential_secret" == "$backup_secret" ]]; then
    pass_message "Longhorn BackupTarget references the expected Secret name"
  else
    fail_message "Longhorn BackupTarget references an unexpected Secret name"
  fi
  if [[ "$available" == "true" ]]; then
    pass_message "Longhorn BackupTarget is Available"
  else
    if [[ -n "$unavailable_reason" ]]; then
      fail_message "Longhorn BackupTarget is unavailable (reason: $unavailable_reason)"
    else
      fail_message "Longhorn BackupTarget is not Available"
    fi
  fi
else
  backup_target_setting_json=""
  backup_credential_setting_json=""
  if backup_target_setting_json="$(kubectl get settings.longhorn.io/backup-target -n "$longhorn_namespace" -o json 2>/dev/null)"; then
    backup_target_url="$(jq -r '.value // empty' <<<"$backup_target_setting_json")"
    target_bucket="${backup_target_url#s3://}"
    target_bucket="${target_bucket%%@*}"
    pass_message "Longhorn backup-target Setting exists"
  else
    fail_message "Longhorn BackupTarget resource and backup-target Setting are missing"
  fi
  if backup_credential_setting_json="$(kubectl get settings.longhorn.io/backup-target-credential-secret -n "$longhorn_namespace" -o json 2>/dev/null)"; then
    credential_setting_value="$(jq -r '.value // empty' <<<"$backup_credential_setting_json")"
    if [[ "$credential_setting_value" == "$backup_secret" ]]; then
      pass_message "Longhorn backup credential Setting references the expected Secret name"
    else
      fail_message "Longhorn backup credential Setting references an unexpected Secret name"
    fi
  else
    fail_message "Longhorn backup-target-credential-secret Setting is missing"
  fi
fi

if [[ -n "$longhorn_secret_json" && -n "$object_store_secret_json" ]]; then
  longhorn_access_key="$(secret_value "$longhorn_secret_json" AWS_ACCESS_KEY_ID)"
  object_store_access_key="$(secret_value "$object_store_secret_json" MINIO_ROOT_USER)"
  longhorn_secret_key="$(secret_value "$longhorn_secret_json" AWS_SECRET_ACCESS_KEY)"
  object_store_secret_key="$(secret_value "$object_store_secret_json" MINIO_ROOT_PASSWORD)"
  longhorn_endpoint="$(secret_value "$longhorn_secret_json" AWS_ENDPOINTS)"
  endpoint_url="$(secret_value "$longhorn_secret_json" AWS_ENDPOINT_URL)"
  longhorn_bucket="$(secret_value "$longhorn_secret_json" AWS_BUCKET_NAME)"
  bucket_alias="$(secret_value "$longhorn_secret_json" AWS_BUCKET)"
  longhorn_region="$(secret_value "$longhorn_secret_json" AWS_REGION)"

  if [[ -n "$longhorn_access_key" && -n "$object_store_access_key" && \
    "$longhorn_access_key" == "$object_store_access_key" ]]; then
    pass_message "Longhorn access-key identity matches the object-store root-user identity"
  else
    fail_message "Longhorn access-key identity does not match the object-store root-user identity"
  fi

  if [[ -n "$longhorn_secret_key" && -n "$object_store_secret_key" && \
    "$longhorn_secret_key" == "$object_store_secret_key" ]]; then
    pass_message "Longhorn secret-key identity matches the object-store root-password identity"
  else
    fail_message "Longhorn secret-key identity does not match the object-store root-password identity"
  fi

  if [[ -n "$longhorn_endpoint" && "$longhorn_endpoint" == "$endpoint_url" ]]; then
    pass_message "Longhorn endpoint keys agree"
  else
    fail_message "Longhorn endpoint keys do not agree"
  fi

  if [[ -n "$longhorn_endpoint" && "$longhorn_endpoint" == "$expected_endpoint" ]]; then
    pass_message "Longhorn uses the in-cluster object-store Service endpoint"
  else
    fail_message "Longhorn does not use the expected in-cluster object-store Service endpoint"
  fi

  if [[ -n "$target_bucket" && "$longhorn_bucket" == "$bucket_alias" && \
    "$longhorn_bucket" == "$target_bucket" ]]; then
    pass_message "Longhorn bucket keys agree with the BackupTarget bucket"
  else
    fail_message "Longhorn bucket keys do not agree with the BackupTarget bucket"
  fi
fi

backups_json=""
if backups_json="$(kubectl get backups.longhorn.io -n "$longhorn_namespace" -o json 2>/dev/null)"; then
  backup_count="$(jq '.items | length' <<<"$backups_json")"
  completed_count="$(jq '[.items[] | select((.status.state // "" | ascii_upcase) == "COMPLETED")] | length' <<<"$backups_json")"
  info_message "Longhorn Backup objects: $backup_count total, $completed_count completed"
  if (( backup_count > 0 )); then
    pass_message "Longhorn Backup objects exist"
  else
    fail_message "Longhorn has no Backup objects"
  fi

  if backup_volumes_json="$(kubectl get backupvolumes.longhorn.io -n "$longhorn_namespace" -o json 2>/dev/null)"; then
    backup_volume_count="$(jq '.items | length' <<<"$backup_volumes_json")"
    info_message "Longhorn BackupVolume objects: $backup_volume_count"
  else
    fail_message "Longhorn BackupVolume objects are not readable"
  fi

  latest_timestamp="$(latest_completed_timestamp "$backups_json")"
  if [[ -z "$latest_timestamp" ]]; then
    fail_message "Longhorn has no completed backup timestamp"
  else
    latest_epoch="$(date --date="$latest_timestamp" +%s 2>/dev/null || true)"
    now_epoch="$(date +%s)"
    if [[ -z "$latest_epoch" ]]; then
      fail_message "Could not parse the latest completed backup timestamp"
    else
      age_seconds=$((now_epoch - latest_epoch))
      max_age_seconds=$((backup_age_hours * 3600))
      if (( age_seconds < 0 )); then
        fail_message "Latest completed backup timestamp is in the future"
      elif (( age_seconds <= max_age_seconds )); then
        pass_message "Latest completed backup is within the configured age limit"
      else
        fail_message "Latest completed backup is older than the configured age limit"
      fi
      info_message "Latest completed backup timestamp: $latest_timestamp"
    fi
  fi
else
  fail_message "Longhorn Backup objects are not readable"
fi

if [[ "$s3_mode" != "never" && -n "$longhorn_secret_json" ]]; then
  endpoint="${longhorn_endpoint:-$(secret_value "$longhorn_secret_json" AWS_ENDPOINTS)}"
  bucket="${longhorn_bucket:-$(secret_value "$longhorn_secret_json" AWS_BUCKET_NAME)}"

  if [[ "$s3_mode" == "auto" && "$endpoint" == *".svc.cluster.local"* ]]; then
    warn_message "Skipped direct S3 request because the endpoint is cluster-internal"
  elif command -v aws >/dev/null 2>&1; then
    if AWS_ACCESS_KEY_ID="$longhorn_access_key" \
      AWS_SECRET_ACCESS_KEY="$longhorn_secret_key" \
      AWS_REGION="$longhorn_region" \
      AWS_EC2_METADATA_DISABLED=true \
      aws --no-cli-pager --endpoint-url "$endpoint" s3api head-bucket --bucket "$bucket" \
      >/dev/null 2>&1; then
      pass_message "S3 bucket request succeeded without printing credentials"
    else
      fail_message "S3 bucket request failed; credentials and endpoint values were not printed"
    fi
  elif [[ "$s3_mode" == "always" ]]; then
    fail_message "STORAGE_BACKUP_CHECK_S3=always requires the aws command"
  else
    warn_message "Skipped direct S3 request because the aws command is not installed"
  fi
fi

if (( failures > 0 )); then
  printf '%s diagnostic check(s) failed. No cluster resource was changed.\n' "$failures" >&2
  exit 1
fi

printf 'DIAGNOSTIC ONLY: read-only storage checks passed.\n'
printf 'Run the disposable new-backup and restore gate separately before storage migration.\n'
