default:
  @just --list

seal:
    kubeseal -f private/minio-secret.yaml -w active/sealed-minio-secret.yaml --namespace minio-homelab --name minio-secret
