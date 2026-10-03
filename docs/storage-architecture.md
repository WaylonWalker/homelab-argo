# Storage architecture and migration plan
> Historical proposal from September 2026. Figures and pending actions describe that date.
> See [the recovery review](cleanup-recovery-2026-10-02.md) for later evidence.
> Recheck live state before using this document for an operation.
> The proposed StorageClasses were not deployed. Vault scheduling is now enabled,
> backup jobs still use the default group, and the old Frigate cache is not disposable footage.

**Status:** plan and safe repository changes only

**Inventory date:** 2026-09-20

**Source inventory:** [`storage-inventory-2026-09-20.md`](storage-inventory-2026-09-20.md)

This document defines the storage roles for the homelab. It also records the
current storage consumers, the backup failure, and the migration order.

This document does not authorize live data movement. Do not delete data, change
replica counts, enable the `falcon2` vault disk, or sync a destructive Argo
change until the backup gate passes.

## Safety gate

The following gate applies to every live migration:

1. Make sure that the Longhorn backup target accepts a new test backup.
2. Make sure that the test backup appears in the backup store.
3. Restore the test backup into a new disposable volume.
4. Read a known test file from the restored volume.
5. Record the backup and restore results.

Until all five steps pass, the following operations are blocked:

- Deleting a Longhorn volume, snapshot, backup, PV, or dataset.
- Reducing replicas on an existing PVC.
- Moving a production PVC or hostPath dataset.
- Enabling Longhorn scheduling on `/mnt/vault`.
- Rebuilding or rebalancing existing replicas by force.
- Moving the Longhorn backup store.
- Allowing Argo to prune a migration source.

### Milestone status

| Milestone | Status for this round | Evidence or next action |
| --- | --- | --- |
| Repository inventory | Complete | This document and the dated inventory |
| Desired storage policy in Git | In progress | Additive classes and this document are prepared |
| Live target and Secret comparison | Failing in the cluster | The live target is unavailable and still uses the public Cloudflare route; Git now selects the in-cluster endpoint pending sync |
| Test backup | Not complete | Repair the S3 signature failure first |
| Test restore | Not complete | Restore only a disposable test volume |
| Production data migration | Not started | Requires the safety gate and human approval |
| Old data retirement | Not started | Requires a separate review after validation |

## Current-state storage map

The dated inventory found three Ready K3s nodes, 65 bound Longhorn PVCs, and 9
released Longhorn volumes. Longhorn health changed during collection. A healthy
volume does not prove that its replicas occupy different nodes.

### Physical roles

| Node | Current device or pool | Current use | Role problem |
| --- | --- | --- | --- |
| `falcon1` | 238.5G SSD at `/var` | OS, K3s, container storage, Longhorn | Longhorn has about 61G free and about 92.6% scheduled capacity |
| `falcon2` | 931.5G SSD | OS, K3s, local-path, Longhorn | This is the Frigate appliance, but its SSD also carries unrelated state |
| `falcon2` | 3.6T HDD at `/mnt/vault` | Frigate, MinIO, site builds, caches, hostPath PVs | About 99.8% full; Longhorn reports a conflicting free-space value |
| `falcon2` | 200G loop-backed `/var/lib/frigate-cache` | Frigate temporary cache | Disposable, but the manifest and live size differ |
| `falcon3` | 465.8G NVMe | OS and K3s | Do not use this device as the bulk-data target |
| `falcon3` | 2.7T internal HDD at `/var/lib/longhorn/disks/wd3tb` | Dedicated Longhorn disk | The largest Longhorn free-capacity reserve |
| `falcon3` | ZFS `main`, 14T mirror | Primary bulk data and backup MinIO | Primary storage and backup storage share one host |
| `falcon3` | ZFS `tank`, 4T mirror | Mixed personal and bulk data | It is not yet a controlled backup tier |

### Current Longhorn layout

The current default Longhorn class requests three replicas and uses `Delete`.
The cluster cannot reliably place three replicas on three different nodes.
Some two-replica volumes have both replicas on `falcon3`. Some three-replica
volumes have an unassigned replica.

The `falcon2` `/mnt/vault` Longhorn disk has scheduling disabled. Keep it
disabled. Its filesystem has about 8.7G free, while Longhorn reports about
208.9G free. The two values must be reconciled before any scheduling change.

The current classes have different meanings:

| Class | Current policy | Current meaning |
| --- | --- | --- |
| `longhorn` | 3 replicas, `Delete`, no recurring jobs | Legacy default; do not assign new critical claims |
| `longhorn-backup` | 2 replicas, `Retain`, hourly snapshots and daily/weekly backups | Legacy stateful tier; its name does not mean that the PVC is the backup store |
| `longhorn-fast-replicated` | 3 replicas, `Retain`, no recurring jobs | Legacy three-copy tier; it is not three-node HA today |
| `longhorn-site` | 1 replica, `Retain`, no backup jobs | Live class reported by the inventory; full live definition is not yet in Git |
| `longhorn-cache` | 1 replica, `Delete`, no backup jobs | Live class reported by the inventory; full live definition is not yet in Git |
| `longhorn-static` | Delete policy, replica value not recorded | Legacy class that needs claim-by-claim review |

Do not rename an existing class. A bound PVC does not change storage class by
editing a class name. Create a new claim and migrate one workload at a time.

### Current ZFS layout

`main` is the large mirror. It has about 8.9T free and stores primary services.
`tank` is a smaller mirror. It has about 1.8T free, but it contains a mixture
of personal data, media, VMs, Git data, and possible critical files.

The repository declares a nearly empty `main/longhorn-backup` dataset. The
Longhorn backup MinIO PV uses `/mnt/main/minio-longhorn-backup` instead. Do not
assume that the empty dataset contains the backup objects.

## Desired-state architecture

### Node roles

#### `falcon1`: small general K3s node

- Keep the OS, K3s, and container storage on its SSD.
- Keep Longhorn use within measured capacity.
- Do not use this node as the reason for three-copy storage policy.
- Revisit capacity only after a dedicated Longhorn SSD is installed.

#### `falcon2`: Frigate appliance

Keep this node focused on Frigate and local compute:

```text
SSD
├── OS
├── K3s
├── local-path storage
└── Longhorn

Coral TPU
└── Frigate inference through /dev/apex_0

Intel iGPU
└── Frigate video acceleration through /dev/dri

old HDD at /mnt/vault
└── Frigate recordings, clips, and retention only
```

The old HDD is expendable. Frigate recordings are not a backup target. Frigate
configuration is separate from recordings and needs a verified backup.

Do not move high-write Frigate recordings to Longhorn without a performance and
capacity test. Do not remove unrelated `/mnt/vault` data until each owner
approves a destination and a verified copy exists.

#### `falcon3`: primary storage server

```text
14T + 14T Exos mirror
└── ZFS main: primary bulk data

4T + 4T IronWolf mirror
└── ZFS tank: critical local backups

internal 3T HDD
└── Longhorn replicas
```

`tank` is a local backup tier. It is not disaster recovery because it shares a
chassis and failure domain with `main`.

### Storage tiers

The first repository change adds only new class names. It does not migrate any
PVC. The manifest is
[`k8s/minio-longhorn-backup/storage-tiers.yaml`](../k8s/minio-longhorn-backup/storage-tiers.yaml).

| Tier | Replicas | Reclaim | Recurring jobs | Approved use |
| --- | ---: | --- | --- | --- |
| `longhorn-critical` | 2 | `Retain` | Explicit daily and weekly backups | Databases, application state, authentication, small critical files |
| `longhorn-ha` | 3 | `Retain` | Explicit daily and weekly backups | Small workloads that need three-node storage HA |
| `longhorn-site` | 1 | `Retain` | None | Generated site output and release history |
| `longhorn-cache` | 1 | `Delete` | None | Search indexes, thumbnails, build cache, and rebuildable state |

Use `longhorn-ha` only after three Longhorn nodes can schedule one replica each.
Three replicas on two nodes do not provide three-node availability.

Adopt the live `longhorn-site` and `longhorn-cache` definitions only after a
live export proves their immutable fields. Do not add a guessed definition for
an existing StorageClass.

The daily and weekly jobs must not belong to the Longhorn `default` group. A
default-group job attaches to volumes without an explicit job selection. That
would back up cache and site volumes that declare an empty selection.

### Storage policy

1. Put primary bulk data on `falcon3/main`.
2. Put critical application state on `longhorn-critical` when the workload has
   an application-aware backup or a tested Longhorn restore.
3. Use `longhorn-ha` only for a small set of workloads with a real three-node
   availability requirement.
4. Put generated site output on `longhorn-site`.
5. Put indexes, thumbnails, build cache, and transcode data on
   `longhorn-cache` or pod-local storage.
6. Keep backup storage outside the Longhorn system that it protects.
7. Keep `/mnt/vault` out of Longhorn scheduling.
8. Treat `Retain` as a safety net, not as a backup.

## Workload storage classification

The table uses these classes:

- **EPHEMERAL:** data can be recreated and has no required retention.
- **CACHE:** derived data that can be rebuilt.
- **PRIMARY BULK:** the main copy of large user or service data.
- **KUBERNETES STATE:** state required to recreate or operate a service.
- **CRITICAL:** loss requires a deliberate recovery action or causes unacceptable loss.
- **BACKUP:** a recovery copy or backup control plane.

The node column is the manifest or inventory location. Longhorn replica nodes
can change, so the current Longhorn node list must be joined to each PVC before
any migration.

| Workload | Namespace | Class | Current backend and path | Current node | Backup coverage | Desired backend and target | Difficulty |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Frigate configuration | `frigate` | CRITICAL | `hostpath`, `/mnt/vault/nfs/general/pv/frigate4/frigate-config` | `falcon2` | A repository archive exists; currentness is not proven | Keep local for runtime; copy to `tank/backups/critical-files` after backup testing | Medium |
| Frigate recordings and clips | `frigate` | EPHEMERAL | `hostpath`, `/mnt/vault/nfs/general/pv/frigate4/frigate-storage` | `falcon2` | No verified backup | Keep on the old HDD as disposable retention | High |
| Frigate temporary cache | `frigate` | CACHE | `hostpath`, `/var/lib/frigate-cache` | `falcon2` | None needed | Local SSD or `emptyDir` | Low |
| Longhorn backup MinIO | `minio-longhorn-backup` | BACKUP | Static PV, `/mnt/main/minio-longhorn-backup` | `falcon3` | This is the target under repair; no restore test passed | Later, a dedicated `tank/backups/longhorn` dataset with an old copy retained | High |
| Primary MinIO object data | `minio` | CRITICAL | `minio-storage-longhorn` on `longhorn-backup`; a legacy `/mnt/vault` PV is also declared | Longhorn or `falcon2`; live use must be reconciled | Longhorn target is failing; hostPath copy is not proven | Service-aware move to `falcon3/main/minio` or tested `longhorn-critical` | High |
| Walkershare | `walkershare` | PRIMARY BULK | Static PV and direct `/mnt/main/walkershare` | `falcon3` | No complete backup plan found | ZFS `main/walkershare`, with selected off-node backup | High |
| Jellyfin media | `jellyfin` | PRIMARY BULK | Manual PV, `/mnt/main/media/media` | `falcon3` | No verified backup | ZFS `main/media` | High |
| Jellyfin configuration | `jellyfin` | CRITICAL | Manual PV, `/mnt/main/media/config` | `falcon3` | No verified backup | ZFS dataset with a small application backup | Medium |
| Jellyfin cache and transcode | `jellyfin` | CACHE | Manual PVs, `/mnt/main/media/cache` and `/mnt/main/media/transcoded` | `falcon3` | None needed | Local rebuildable storage | Low |
| Nextcloud files | `nextcloud` | PRIMARY BULK / CRITICAL | Direct paths under `/mnt/main/nextcloud` | `falcon3` | Incomplete application backup | ZFS `main/nextcloud` plus database-consistent backup | High |
| Photoprism originals | `photoprism` | CRITICAL | Direct paths under `/mnt/main/walkershare/*/photos` | `falcon3` | No complete restore test found | `falcon3/main` with a selected off-node copy | High |
| Photoprism database and storage | `photoprism` | CRITICAL | HostPath PVC and SQLite storage under `/mnt/main/walkershare/photoprism` | `falcon3` | Application database backup is not proven | ZFS `main` plus an explicit export or database backup | Medium |
| Models library | `models`, `models-dev` | PRIMARY BULK | Static PVs under `/mnt/main/walkershare/waylon/3d` and `3d-dev` | `falcon3` | No verified backup | ZFS `main/models` or the existing `main/walkershare` dataset | Medium |
| Models databases | `models`, `models-dev` | KUBERNETES STATE | `longhorn-fast-replicated` | Longhorn | No recurring backup for the three-copy class | `longhorn-critical` plus native database backup | Medium |
| Production site source | `*-com-prod-notes` | CRITICAL | Longhorn PVCs, usually generic `longhorn` | Longhorn | Target is failing; source backup is not separately proven | `longhorn-critical` plus source repository backup | Medium |
| Production generated site | `*-com-prod-notes` | PRIMARY BULK | Longhorn PVCs, usually generic `longhorn` | Longhorn | Rebuildable, but release history is useful | `longhorn-site` | Medium |
| Production site cache | `*-com-prod-notes` | CACHE | Generic Longhorn or hostPath | Longhorn or `falcon3` | None needed | `longhorn-cache` or hostPath on `main` | Low |
| Production search index | `*-com-prod-notes` | CACHE | Generic Longhorn or local-path | Longhorn or `falcon2` | None needed | `longhorn-cache` or pod-local storage | Low |
| Markata dev source and site | `go-waylonwalker-com-notes` | PRIMARY BULK / CRITICAL | HostPath under `/mnt/main/walkershare/waylon` | `falcon3` | No complete backup found | Keep source and site on `main`; keep cache rebuildable | Medium |
| Markata reader cache | `reader` | CACHE | HostPath, `/mnt/vault/nfs/general/pv/reader/markata-cache` | `falcon2` | None needed | `longhorn-cache`, local-path, or `emptyDir` | Low |
| Markata docs build cache | `markata-go-docs` | CACHE | HostPath, `/mnt/vault/nfs/general/pv/markata-go-docs-build` | `falcon2` | None needed | `longhorn-cache` or a disposable workspace | Low |
| Forgejo application data | `forgejo` | CRITICAL | `forgejo-data-v2`, 50Gi, `longhorn-backup` | Longhorn | A backup failure is recorded | `longhorn-critical` plus a Forgejo export | Medium |
| Forgejo PostgreSQL | `forgejo` | KUBERNETES STATE / CRITICAL | CNPG, 10Gi, `longhorn-backup` | Longhorn | No CNPG object-store backup block found | `longhorn-critical` plus CNPG native backup | Medium |
| Forgejo runner registration | `forgejo` | KUBERNETES STATE | `forgejo-runner-data-v2`, 5Gi, generic `longhorn` | Longhorn | No separate backup | Keep registration on `longhorn-critical`; separate the action cache first | Medium |
| Prometheus TSDB | `observability` | KUBERNETES STATE | 50Gi, generic `longhorn`, 15-day retention | Longhorn | Target is failing; one replica is unassigned in the inventory | `longhorn-critical` or remote write after size analysis | High |
| Grafana and Alertmanager | `observability` | KUBERNETES STATE | 10Gi claims, generic `longhorn` | Longhorn | Target is failing | `longhorn-critical` plus Git-managed configuration | Medium |
| Loki and Tempo data | `observability` | CACHE or KUBERNETES STATE | Longhorn claims | Longhorn | No explicit restore path | `longhorn-cache` unless incident history must survive | Medium |
| CNPG application databases | Several namespaces | KUBERNETES STATE / CRITICAL | Mixed generic and `longhorn-backup` classes | Longhorn | Native backup declarations are incomplete | `longhorn-critical` plus CNPG object-store backup | High |
| Redis data and backup job | `redis` | CACHE / KUBERNETES STATE | PVC; backup job writes to primary MinIO | Longhorn or local-path | Backup depends on primary MinIO | Rebuildable tier; use an independent target for required state | Medium |
| Home Assistant state | `home-assistant` | CRITICAL | HostPath, `/mnt/vault/nfs/general/pv/home-assistant/home-assistant-config` | `falcon2` | No verified backup | `longhorn-critical` or `tank/backups/application-state` | Medium |
| Podgrab configuration | `podgrab` | CRITICAL | HostPath under `/mnt/vault/nfs/general/pv/podgrab/config` | `falcon2` | No verified backup | `longhorn-critical` or `main` with backup | Medium |
| Podgrab downloaded data | `podgrab` | PRIMARY BULK | HostPath under `/mnt/vault/nfs/general/pv/podgrab/data` | `falcon2` | No verified backup | Human review, then `main` if retained | High |
| Podfetch database | `podfetch` | CRITICAL | HostPath under `/mnt/vault/nfs/general/pv/podfetch/db` | `falcon2` | No verified backup | `longhorn-critical` or `main` with application backup | Medium |
| Podfetch podcasts | `podfetch` | PRIMARY BULK | HostPath under `/mnt/vault/nfs/general/pv/podfetch/podcasts` | `falcon2` | Feeds can be reproducible; retention is an owner decision | `main` or disposable storage | Medium |
| Immich library | `immich` | CRITICAL | Live inventory reports hostPath under `/mnt/vault/nfs/general/pv/immich` | `falcon2` | No verified backup | `main` or future `tank/backups/critical-files` | High |
| Immich PostgreSQL | `immich` | KUBERNETES STATE / CRITICAL | Live inventory reports a hostPath database PV | `falcon2` | No verified backup | CNPG or `longhorn-critical` with native backup | High |
| Immich Typesense index | `immich` | CACHE | HostPath under the Immich PV root | `falcon2` | None needed | `longhorn-cache` or rebuildable storage | Medium |
| Terraria worlds | `terraria`, `terraria-challenge` | KUBERNETES STATE | Broad hostPath `/mnt/vault/nfs/general/` | `falcon2` | No verified backup | Human review, then a named dataset or Longhorn | High |
| K3s archive | host filesystem | BACKUP | `/mnt/vault/nfs/general/backup/k3s` | `falcon2` | Script creates archives; off-node copy is not proven | `tank/backups/infrastructure`, then off-node storage | Medium |

Other Longhorn namespaces, including Dropper, Postiz, Perform Peoria, Omada,
Thoughts, Aylawalker, Notify Bridge, Zigbee2MQTT, and game services, need a
claim-to-pod review. Treat databases, configuration, and user uploads as
`KUBERNETES STATE` or `CRITICAL`. Treat queues, indexes, thumbnails, and
generated media as `CACHE` only after a cold-start test proves that they rebuild.

## `/mnt/vault` consumer and migration table

The old HDD must become Frigate-only storage. The table lists the required
classification work. It does not authorize a move.

| Current path | Workload | Data type | Critical? | Target | Migration notes |
| --- | --- | --- | --- | --- | --- |
| `/mnt/vault/nfs/general/pv/frigate4/frigate-config` | Frigate | Config and database | Yes | Runtime stays on `falcon2`; backup copy to `tank` | Verify the live config before using the tracked archive |
| `/mnt/vault/nfs/general/pv/frigate4/frigate-storage` | Frigate | Recordings, clips, retention | No by default | Remain on the old HDD | Set a bounded retention policy and reserve free space |
| `/mnt/vault/nfs/general/pv/minio/minio-storage` | Legacy MinIO PV | Object data | Review | `falcon3/main` or a service-aware migration | Reconcile this PV with `minio-storage-longhorn` before moving either |
| `/mnt/vault/nfs/general/pv/markata-go-docs-build` | Markata docs | Build workspace | No | Rebuildable storage or `longhorn-cache` | Do not change the PV path in place |
| `/mnt/vault/nfs/general/pv/reader/markata-cache` | Reader | Feed cache | No | `longhorn-cache` or `emptyDir` | The live CronJob mount needs confirmation |
| `/mnt/vault/nfs/general/pv/shots/cache` | Shots | Render cache | No | `longhorn-cache` or `emptyDir` | Rebuild and compare output before retirement |
| `/mnt/vault/nfs/general/pv/shots-dev/cache` | Shots dev | Render cache | No | `longhorn-cache` or `emptyDir` | Treat as disposable after a developer review |
| `/mnt/vault/nfs/general/pv/podgrab/config` | Podgrab | Application state | Yes | `longhorn-critical` or `main` | Copy config separately from downloaded data |
| `/mnt/vault/nfs/general/pv/podgrab/data` | Podgrab | Downloads | Review | `falcon3/main` or disposable storage | Do not assume downloads are disposable |
| `/mnt/vault/nfs/general/pv/podfetch/podcasts` | Podfetch | Downloads | Review | `falcon3/main` or disposable storage | Confirm feed replay and retention policy |
| `/mnt/vault/nfs/general/pv/podfetch/db` | Podfetch | Database | Yes | `longhorn-critical` or `main` | Use an application-consistent export |
| `/mnt/vault/nfs/general/pv/immich/immich-library` | Immich | Originals and media | Yes | `falcon3/main` and selected `tank` backup | Do not treat photos as cache |
| `/mnt/vault/nfs/general/pv/immich/immich-typesense` | Immich | Search index | No | `longhorn-cache` | Rebuild after the library move |
| `/mnt/vault/nfs/general/pv/immich/immich-postgres` | Immich | Database | Yes | `longhorn-critical` and native backup | Quiesce the application before export |
| `/mnt/vault/nfs/general/pv/home-assistant/home-assistant-config` | Home Assistant | Configuration and state | Yes | `longhorn-critical` or `main` | Preserve permissions and application version |
| `/mnt/vault/nfs/general/` | Terraria | Game worlds and broad shared data | Review | Named dataset or Longhorn | Replace the broad root mount only after ownership review |
| `/mnt/vault/nfs/general/pv/dev-waylonwalker-com` | Dev site | Source and site output | Rebuildable, source may matter | `falcon3/main` or site/cache tiers | Source and generated output need separate treatment |
| `/mnt/vault/nfs/general/backup/k3s` | K3s backup script | Cluster recovery archive | Yes | `tank/backups/infrastructure` and off-node copy | The current archive is on the same node as the source |

After every row has an owner and target, measure the remaining HDD use. Only
then can the HDD become Frigate-only storage. Do not use a blanket path rewrite.

## Longhorn backup failure analysis

### Declared path

The Longhorn Helm application declares:

- target: `s3://longhorn-system@us-east-1/`
- credential Secret: `minio-longhorn-backup-secret`
- poll interval: 300 seconds
- chart: `v1.12.1`

The target MinIO service is declared in
`k8s/minio-longhorn-backup/deployment.yaml`. It listens on port 9000 and uses
the static PV path `/mnt/main/minio-longhorn-backup` on `falcon3`.

The deployment now uses a long-running `minio/mc` sidecar as the bucket
provisioner. It waits for MinIO, creates `longhorn-system` with
`--ignore-existing`, and reports readiness only after that operation succeeds.
The old live init container called `localhost:9000` before the main container
started, suppressed the error, and hard-coded the `longhorn` bucket. The live
data directory currently contains `longhorn-system`, but that does not prove
that the old init step succeeded or that Longhorn can use the bucket. The
target is not the nearly empty `main/longhorn-backup` dataset.

The manifests still use floating `minio/minio` and `minio/mc` image tags. Pin
compatible image digests before treating this repair as the long-term
production configuration. This repair does not change image selection.

### Observed failure

The dated inventory recorded:

```text
AWS Error: SignatureDoesNotMatch The request signature we calculated does not match the signature you provided. Check your key and signing method.
```

The target was unavailable at collection time. The inventory found 926 backup
objects, including 914 completed objects, but old completed objects do not prove
that a new backup can be written or restored.

### Root-cause ranking

The strongest cause is now identified without printing Secret values:

1. **A Cloudflare-proxied S3 endpoint changes a signed header.** The live
   `AWS_ENDPOINTS` value is `https://minio-longhorn-backup.wayl.one`. The
   Ingress routes that hostname through a Cloudflare Tunnel. Longhorn's current
   S3 dependency signs `Accept-Encoding`; Cloudflare rewrites that header, which
   produces `SignatureDoesNotMatch`. The current Longhorn chart predates the
   configurable `AWS_SIGN_ACCEPT_ENCODING` workaround.
2. **The endpoint is also unnecessarily external.** The MinIO Service is
   reachable from a Longhorn manager at
   `http://minio-longhorn-backup.minio-longhorn-backup.svc.cluster.local:9000`.
   Use that endpoint so signed traffic does not cross the proxy.
3. **Credential drift is not supported by the current evidence.** Secret
   identity digests match the running MinIO process, the endpoint keys agree,
   and the decoded values have no trailing newline.
4. **Bucket initialization was a separate repository defect.** The Git
   deployment now provisions the correct bucket from a sidecar, but the live
   Pod must be resynced and observed before this fix is considered complete.

The safe repository policy is to keep Helm as the target source of truth and
keep the live `BackupTarget` as the only target resource. Do not add manual
Longhorn `Setting` resources or rotate credentials automatically.

### Safe diagnostic workflow

Run this command from a workstation with an authorized Kubernetes context:

```bash
just storage-backup-check
```

The command reads Services, Endpoints, pod readiness, Secret key names,
Longhorn Settings, BackupTarget resources when installed, Backup objects, and
BackupVolume objects. It compares the credential identities by an in-memory
digest. It never prints credential values.

The command can use the local `aws` command to send a bucket request when the
endpoint is reachable from the workstation. It skips that request for a
cluster-internal endpoint unless `STORAGE_BACKUP_CHECK_S3=always` is set. A
skipped request is not a successful backup test.

The command does not apply, label, delete, restore, or migrate a resource.

Record these results separately:

| Check | Passing result |
| --- | --- |
| Service | Service exists and has a port 9000 endpoint |
| Pod | MinIO has a Ready pod |
| DNS and health | A MinIO pod reaches the Service readiness endpoint |
| Secret keys | Required key names exist in both namespaces |
| Credential identity | Longhorn access and secret identities match MinIO root identities |
| Longhorn target | The `backuptargets.longhorn.io/default` resource is available, references the expected Secret, and the Secret uses the in-cluster endpoint |
| Backup store | A new Backup object completes after the repair |
| Backup age | A completed backup is newer than the selected threshold |
| Restore | A disposable volume restores and its sentinel file matches |

## Backup and restore validation procedure

Run this procedure only after the diagnostic workflow identifies a repaired
target. Use a dedicated test namespace and a unique test PVC. Do not use a
production PVC, a released production volume, or a production snapshot.

### Create and back up a test volume

1. Ask for approval to create a disposable namespace, PVC, pod, snapshot, and
   backup.
2. Create a small PVC using `longhorn-backup` until the new tiers pass their
   own validation.
3. Mount the PVC in a temporary pod.
4. Write a sentinel file with a known string and a timestamp.
5. Read the sentinel file once before the backup.
6. Create a Longhorn snapshot from the UI or a reviewed `Snapshot` resource.
7. Create an incremental `Backup` resource for that snapshot.
8. Wait for the Backup state to become `Completed`.
9. Record the Backup name, completion time, status, and volume size.
10. Run `just storage-backup-check` again.

Longhorn 1.12.1 uses a `Backup` resource similar to this example. Replace the
snapshot name with a test snapshot. Review the manifest before applying it.

```yaml
apiVersion: longhorn.io/v1beta2
kind: Backup
metadata:
  name: storage-restore-test
  namespace: longhorn-system
spec:
  backupMode: incremental
  snapshotName: REPLACE_WITH_TEST_SNAPSHOT
  labels:
    purpose: storage-restore-test
```

The Longhorn documentation describes the UI and manifest methods:

- [Create a Backup](https://longhorn.io/docs/1.12.1/snapshots-and-backups/backup-and-restore/create-a-backup/)
- [Restore from a Backup](https://longhorn.io/docs/1.12.1/snapshots-and-backups/backup-and-restore/restore-from-a-backup/)

### Restore and read the test volume

1. Stop the test pod.
2. Record the exact `status.url` and `status.volumeSize` from the completed
   Backup resource.
3. Create a new Longhorn `Volume` with a new name and the recorded backup URL.
4. Wait until `restoreRequired` is false and the volume is detached.
5. Bind the restored volume to a new test PV and PVC.
6. Mount the restored PVC in a new test pod.
7. Read the sentinel file and compare its content and timestamp.
8. Record the restored volume name and the verification result.
9. Keep the original test backup until the result is reviewed.
10. Delete only the disposable test resources after approval.

The restore test passes only when the file content matches and the Longhorn
resource reaches the expected restored state. A successful backup object alone
does not pass this gate.

## Tank cleanup and backup proposal

### Current `tank` contents

The inventory reports these datasets. Their names do not establish that they
are disposable.

| Dataset | Approximate use | Classification | First action |
| --- | ---: | --- | --- |
| `tank/steam` | 927G | PRIMARY BULK, owner review | Move to `main` only after an owner approves a copy and checksum plan |
| `tank/rhiannon-spectre` | 887G | CRITICALITY UNKNOWN | Do not move or delete until the owner classifies it |
| `tank/jellyfin` | 180G | PRIMARY BULK | Move related media to `main/media` after a service-aware copy |
| `tank/git` | 95G | CRITICAL | Keep a second copy and include important repositories in off-node backup |
| `tank/vm` | 79G | KUBERNETES STATE or PRIMARY BULK | Inventory guests and take application-consistent backups |
| `tank/waylonwalker-gaming` | 6.8G | KUBERNETES STATE or review | Classify world saves before movement |
| `tank/3d` | 3.9G | PRIMARY BULK | Move models to the primary `main` role if the data is authoritative |
| `tank/roms` | 4.5G | PRIMARY BULK or review | Owner decision; do not delete |
| `tank/brushes` | 2.7G | PRIMARY BULK or review | Owner decision; do not delete |
| `tank/tax` | 8.8M | CRITICAL | Include in `critical-files` backup |
| `tank/work` | 473M | CRITICAL or review | Owner decision; preserve before movement |

Moving only the obvious bulk candidates can free about 1.2T. That estimate is
not a cleanup authorization. `tank/rhiannon-spectre` alone is about 887G and
must remain until its owner classifies it.

### Target hierarchy

After the review and verified copies, create a small hierarchy on `tank`:

```text
tank/backups/
├── longhorn/
├── cnpg/
├── infrastructure/
├── application-state/
└── critical-files/
```

Use separate datasets and retention rules. Do not put Steam, all media,
Frigate recordings, or rebuildable caches in this hierarchy.

The local backup tier must contain selected recovery data, not every primary
dataset. It must later replicate to a different node, host, or provider.

## Ordered implementation plan

### Phase A: safety and backup proof

1. Run the read-only inventory again before any live change.
2. Compare the live MinIO Service, endpoint, bucket, region, and Secret key
   presence without printing Secret values.
3. Make the Longhorn Helm Settings the single target source.
4. Repair the signature failure without rotating credentials automatically.
5. Create and verify a disposable test backup.
6. Restore the test backup and record the result.

**Exit condition:** the diagnostic command passes, a new backup completes, and a
sentinel file survives a restore.

### Phase B: repository storage policy

1. Keep the additive `longhorn-critical` and `longhorn-ha` classes.
2. Keep legacy classes unchanged for existing claims.
3. Export the complete live definitions of `longhorn-site` and
   `longhorn-cache` before adopting them into Git.
4. Keep backup jobs out of the Longhorn `default` group.
5. Keep the backup target in `argo-apps/core-apps/longhorn.yaml`.
6. Render and review manifests before any Argo sync.

**Exit condition:** Git has one documented target source and no class change is
assigned to an existing PVC.

### Phase C: Falcon2 cleanup

1. Produce a directory-level `/mnt/vault` inventory with owners and sizes.
2. Back up Frigate configuration and every critical non-Frigate consumer.
3. Move one non-Frigate workload at a time to its approved target.
4. Keep the old PV or copy until the new workload passes its recovery test.
5. Remove the `/mnt/vault` Longhorn disk from configuration only after no
   Longhorn replica or PV depends on it.
6. Set and monitor a bounded Frigate retention period.

**Exit condition:** only noncritical Frigate retention data remains on the HDD,
with enough free space for normal operation.

### Phase D: Longhorn optimization

1. Stabilize degraded volumes and explain disk accounting first.
2. Verify replica nodes for every important volume.
3. Migrate rebuildable caches to one-copy classes.
4. Migrate generated site output to `longhorn-site`.
5. Migrate important application state to `longhorn-critical` with backups.
6. Keep three-copy policy only for small workloads with a real HA need.
7. Investigate Prometheus retention, snapshots, filesystem use, and trim.
8. Review released volumes only after their owners approve cleanup.

Do not force a rebuild or lower replicas as part of this phase. Use a controlled
workload migration with an old PVC retained for rollback.

### Phase E: make `tank` a backup tier

1. Classify every current `tank` dataset with its owner.
2. Copy approved primary bulk data to `main` with checksums.
3. Keep the source dataset until the copied service passes a recovery test.
4. Create the `tank/backups` dataset hierarchy.
5. Set capacity reservations and retention rules after measuring the selected
   critical subset.

Do not destroy a dataset. Do not use `rsync --delete` for the first copy.

### Phase F: move local Longhorn backup storage

1. Complete Phases A through E.
2. Stop or quiesce the backup MinIO service during the copy.
3. Copy the object store to `tank/backups/longhorn` without deleting the old
   copy.
4. Compare object counts and checksums.
5. Switch the service only after the copy passes review.
6. Create another test backup.
7. Restore another disposable volume from the new target.
8. Keep the old `main` copy until the second restore passes.

This phase requires a written rollback procedure and a maintenance window.

### Phase G: off-node and offsite protection

Protect only the irreplaceable subset:

- Databases and their native backups.
- Important Git repositories.
- Infrastructure configuration and K3s recovery material.
- Family documents and photos.
- Selected Nextcloud and Walkershare data.
- Application state required to rebuild services.

Do not use this tier for all media, Steam data, Frigate retention, or caches.

## Risks and rollback

| Risk | Result | Control | Rollback |
| --- | --- | --- | --- |
| Same-node replicas | A healthy volume can still lose a node copy | Inspect replica node placement, not only robustness | Keep old PVC and restore from a tested backup |
| `falcon1` capacity pressure | New replicas fail to schedule | Do not increase replica count; watch scheduled capacity | Stop the new migration and keep the old claim |
| `/mnt/vault` full | Frigate and unrelated workloads fail | Keep Longhorn scheduling disabled and leave free-space reserve | Restore the old workload from its verified copy |
| S3 signature failure | Backups are not usable | Run the diagnostic and a restore test | Keep the old backup target and do not move its data |
| Argo prune | A migration source disappears | Separate source and destination syncs; retain old PVCs | Revert Git and restore the old manifests |
| Database file copy | An inconsistent database is copied | Use CNPG, Forgejo, or application-native exports | Restore the source service and native backup |
| Frigate retention growth | The HDD fills again | Bound retention and alert on free space | Reduce retention only after owner approval |
| Tank misclassification | Critical personal data is moved or deleted | Owner classification and checksums before movement | Keep the original dataset and restore the copy |
| Backup MinIO move | Longhorn loses its backup store | Keep the old copy and run a second backup and restore test | Switch back to the old service endpoint |

### Human approval required

The following actions require explicit approval for each workload or dataset:

- Any Argo sync that can prune or alter storage resources.
- Any credential or endpoint change.
- Any PVC creation for a production migration.
- Any change to an existing PVC's replica policy.
- Any replica rebuild, rebalance, or disk-tag change.
- Any use of `falcon2:/mnt/vault` for new storage.
- Any hostPath copy or service cutover.
- Any CNPG restore or cluster replacement.
- Any Prometheus snapshot cleanup, trim, or expansion.
- Any deletion of a PVC, PV, Longhorn volume, snapshot, backup, or dataset.
- Any removal of the old MinIO backup copy.
- Any decision that marks `rhiannon-spectre` or another `tank` dataset disposable.

## Repository changes in this round

These changes are safe to review without migrating data:

- `docs/storage-architecture.md` records the policy and migration plan.
- `k8s/minio-longhorn-backup/storage-tiers.yaml` adds two new StorageClasses.
- `k8s/minio-longhorn-backup/deployment.yaml` provisions the target bucket from
  a readiness-gated sidecar.
- `k8s/minio-longhorn-backup/minio-longhorn-backup-longhorn-system-sealed-secret.yaml`
  selects the in-cluster MinIO endpoint for Longhorn.
- `scripts/storage-backup-check.sh` provides a read-only backup diagnostic.
- `just storage-backup-check` runs the diagnostic.
- `k8s/minio-longhorn-backup/RecurringJob.yaml` does not place backup jobs in
  the Longhorn `default` group.
- `argo-apps/core-apps/longhorn.yaml` documents Helm as the target source.

These changes do not prove live backup health. They do not move data or migrate
an existing PVC. A rendered manifest is not a backup test and is not a restore
test.

## Intentionally omitted

This round does not:

- Delete released Longhorn volumes, snapshots, backups, PVs, or datasets.
- Change production replica counts.
- Enable `falcon2:/mnt/vault` for Longhorn scheduling.
- Move MinIO data.
- Move Frigate data.
- Change static PV hostPaths.
- Rotate credentials.
- Sync Argo applications.
- Perform a production restore.
