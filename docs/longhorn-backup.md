# Longhorn backup transport

## S3-compatible contract

Longhorn sends backups to an S3-compatible backup object store.

```text
Longhorn
   │
   │ S3-compatible API
   ▼
backup-object-store
   │
   ├── current: MinIO
   └── future: RustFS
```

The current object store runs in the `minio-longhorn-backup` namespace. Longhorn
uses the Kubernetes Service endpoint:

```text
http://minio-longhorn-backup.minio-longhorn-backup.svc.cluster.local:9000
```

The backup target remains `s3://longhorn-system@us-east-1/`. The bucket name is
`longhorn-system`. The Longhorn credential Secret is
`longhorn-system/minio-longhorn-backup-secret`.

The Longhorn Helm values in `argo-apps/core-apps/longhorn.yaml` own the target
Settings. Keep one target source instead of adding a second Setting manifest.

The internal endpoint keeps signed S3 requests inside the cluster. It avoids the
Cloudflare proxy that can change a signed header and cause `SignatureDoesNotMatch`.
This diagnosis remains unproven until the endpoint change is synced and a new
backup succeeds.

## Bucket provisioning

The object-store Deployment runs a pinned `minio/mc` sidecar. The sidecar waits
for the MinIO S3 API, creates `longhorn-system` with an idempotent command, and
stays alive after provisioning. The sidecar reports Ready only after the bucket
operation succeeds. The MinIO server and client images use explicit release tags
and immutable image digests.

## Read-only diagnostic

Run this command from a GNU/Linux workstation with an authorized Kubernetes
context. The workstation needs `kubectl`, `jq`, `base64`, and GNU `date`.

```bash
just storage-backup-check
```

The command reads Services, endpoints, pod readiness, the health endpoint,
Secret key names, credential identities, endpoint values, bucket names, the
Longhorn BackupTarget, and recent Backup objects. It does not print plaintext
credentials. It does not apply resources, create a backup, or restore a volume.

**This command is diagnostic only. A successful diagnostic is not the backup
safety gate. It does not prove that a new backup works or that a restore works.**

## Backup safety gate

After this repair is approved and synced:

1. Wait for the Longhorn BackupTarget to become Available.
2. Create a disposable test PVC.
3. Write a known sentinel file to the PVC.
4. Create a **new** Longhorn backup.
5. Restore that backup to a **new** volume and PVC.
6. Read the sentinel from the restored PVC.
7. Pass the gate only when the sentinel matches the original content.

Do not migrate production storage until this gate passes. Do not perform the
RustFS migration in this change. RustFS can be evaluated later behind the same
S3-compatible contract.
