# Falcon2 `/mnt/vault` ownership inventory
> Historical snapshot from September 2026. Figures and pending actions describe that date.
> See [the recovery review](cleanup-recovery-2026-10-02.md) for later evidence.
> Recheck live state before using this document for an operation.

**Snapshot:** 2026-09-21

**Status:** Incomplete. Use `UNKNOWN—HOLD` for unproven ownership.

This is a read-only inventory. It does not authorize a copy, cutover, or
deletion. No source data was changed.

## Safety result

`just storage-backup-check` passed. The Longhorn backup target is healthy.
That result does not protect hostPath data on `/mnt/vault`.

Current `/mnt/vault` state:

- Device: `/dev/sdb1`
- Filesystem: `ext4`
- Total: `3,936,789,286,912` bytes reported by the host query
- Used: `3,726,740,676,608` bytes
- Available: `9,994,162,176` bytes
- Use: `100%`
- Longhorn disk: `falcon2/vault`
- Longhorn scheduling: disabled
- Longhorn scheduled replicas: zero

The filesystem has less than 10 GB available. Do not use ext4 reserved blocks
as migration space. Do not write backup artifacts to this filesystem.

## Immich result

Kubernetes has no `immich` namespace, pod, deployment, StatefulSet, Service,
PVC, or Argo `Application`. The three Immich PVs are `Available` and were
created on 2024-12-31.

The declared source directory does not exist on Falcon2:

```text
/mnt/vault/nfs/general/pv/immich                         MISSING
/mnt/vault/nfs/general/pv/immich/immich-library           MISSING
/mnt/vault/nfs/general/pv/immich/immich-postgres          MISSING
/mnt/vault/nfs/general/pv/immich/immich-typesense         MISSING
```

The repository contains only historical, commented Immich definitions. They
reference chart `0.9.0`, image `v1.119.0`, and PostgreSQL 14. Those values do
not prove the version that created the missing data.

The old AIO definition references `ghcr.io/imagegenius/immich:latest` and a
PostgreSQL 14 image. It is not live evidence.

**Immich status:** Dormant in Kubernetes. External status is unresolved.

**Immich writers:** Unresolved. No active Immich process or pod was found, but
the broad NFS export and active Samba service prevent a complete ownership proof.

No CP0 checksum record was created because the declared source paths are
missing and the writer inventory is not complete.

## Ownership inventory

`Actual size` and `file count` are host observations. A missing path is not
treated as proof that the related PV or data is disposable.

| PATH | OWNER / WORKLOAD | NAMESPACE | CURRENT CONSUMERS | ACTIVE WRITERS | PV / PVC | PV STATE | ACTUAL SIZE | FILE COUNT | DATA TYPE | CRITICALITY | CURRENT BACKUP | TARGET | MIGRATION METHOD | RESTORE TEST | ROLLBACK | STATUS |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| `/mnt/vault/longhorn` | Longhorn disk data | `longhorn-system` | Longhorn disk object | None observed; disk remains disabled | `falcon2/vault` | Disk, no scheduled replicas | 12 KiB allocated | Unknown | Longhorn data or metadata | Unknown | Longhorn backup does not cover this hostPath | None | Do not move in this phase | Not run | Retain in place | `UNKNOWN—HOLD` |
| `/mnt/vault/.rancher` | Unknown | Unknown | Unknown | Unknown | None found | Not applicable | About 285.8 GB; scan timed out | Unknown | Unknown | Unknown | Not proven | Unknown | Do not move or delete | Not run | Retain in place | `UNKNOWN—HOLD` |
| `/mnt/vault/.Trash-1000` | User trash | Unknown | Unknown | Unknown | None found | Not applicable | 12 KiB allocated | Unknown | User data | Unknown | Not proven | Unknown | Do not move or delete | Not run | Retain in place | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs` | NFS export root | Host service | NFS clients can reach the export | External writers unknown | None found | Not applicable | About 3.43 TB; scan timed out | Unknown | Shared data root | Unknown | Not proven | Workload-specific targets | Classify each child before movement | Not run | Retain in place | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/frigate4/frigate-storage` | Frigate recordings and clips | `frigate` | Frigate reads and writes `/media/frigate`; notify-bridge reads it at `/media/frigate` | Frigate | `pv-hostpath-general-storage` / `frigate/storage` | Bound | 3,408,871,301,120 bytes | 1,455,332 files | Frigate retention | Approved Frigate auxiliary storage | No verified backup | Remain on `/mnt/vault` | Keep local; use bounded retention | Not run | Retain in place | Active |
| `/mnt/vault/nfs/general/pv/frigate4/frigate-config` | Frigate configuration and database | `frigate` | Frigate reads and writes `/config` | Frigate | `pv-hostpath-general-config` / `frigate/config` | Bound | 2,389,180,416 bytes | 14 files | Application state | Critical | Tracked archive exists; currentness is not proven | `tank` backup; runtime stays local | Quiesce Frigate, then copy with metadata | Not run | Retain in place | Active |
| `/mnt/vault/nfs/general/pv/minio/minio-storage` | Legacy MinIO PV | `minio` | PV is bound; live MinIO uses `minio-storage-longhorn` instead | Unknown | `minio-pv` / `minio/minio-storage` | Bound | 3,141,648,384 bytes | Unknown | Object data | Criticality unknown | Not proven | Resolve authoritative store first | Service-aware object comparison | Not run | Retain in place | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/dev-waylonwalker-com` | Dev site build data | `dev-waylonwalker-com` | Site and cleanup CronJobs | Dev site jobs | `dev-waylonwalker-com-build-hostpath2` / same | Bound | 39,399,424 bytes | Unknown | Build data | Rebuildable or source-critical | Not proven | `falcon3/main` or cache tier | Separate source, output, and cache | Not run | Retain in place | Active |
| `/mnt/vault/nfs/general/pv/reader/markata-cache` | Reader cache | `reader` | PVC is bound; live CronJob mount is commented out | None observed | `markata-cache-pv` / `reader/markata-cache-pvc` | Bound | 828,153,856 bytes | Unknown | Cache | Rebuildable | None required | `longhorn-cache` or pod-local storage | Rebuild after a cold start | Not run | Retain in place | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/shots/cache` | Shots cache | `shot` | Shots pods | Shots pods | `pv-hostpath-general-cache` / `shot/cache` | Bound | 40,960 bytes | Unknown | Cache | Rebuildable | None required | `longhorn-cache` or pod-local storage | Rebuild and compare output | Not run | Retain in place | Active |
| `/mnt/vault/nfs/general/pv/shots-dev/cache` | Shots development cache | `shots-dev` | Shots-dev pods | Shots-dev pods | `pv-hostpath-general-shots-dev-cache` / `shots-dev/cache` | Bound | 4,096 bytes | Unknown | Cache | Rebuildable | None required | `longhorn-cache` or pod-local storage | Rebuild and compare output | Not run | Retain in place | Active |
| `/mnt/vault/nfs/general/pv/immich/immich-library` | Immich library | `immich` | No Kubernetes consumer found; path missing | External writer unknown | `immich-library-pv` / none | Available | Missing path | Not applicable | Originals and media | Critical | Not proven; Longhorn backup does not cover it | Candidate: `/mnt/main/immich/library` | Find the real source, freeze writers, then copy with metadata | Not run | Retain the original source | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/immich/immich-postgres` | Immich PostgreSQL | `immich` | No Kubernetes consumer found; path missing | External writer unknown | `immich-postgres-pv` / none | Available | Missing path | Not applicable | Database | Critical | Not proven; Longhorn backup does not cover it | Candidate: new `longhorn-backup` PVC | Find the real source, identify the major, then use native backup | Not run | Retain the original source | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/immich/immich-typesense` | Immich Typesense index | `immich` | No Kubernetes consumer found; path missing | External writer unknown | `immich-typesense-pv` / none | Available | Missing path | Not applicable | Rebuildable index | Cache | Not required until Immich is found | Candidate: `longhorn-cache` or rebuild | Rebuild during an isolated restore | Not run | Retain the original source | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/markata-go-docs-build` | Markata docs build data | `markata-go-docs` | No current PV consumer found | Unknown | `markata-go-docs-build-hostpath` / old claim | Released | Missing path | Not applicable | Build data | Rebuildable | Not proven | Cache tier or a disposable workspace | Rebuild from verified source | Not run | Retain the original source | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/home-assistant/home-assistant-config` | Home Assistant state | `home-assistant` | No current pod found | Unknown | `pv-hostpath-general-home-assistant-config` / old claim | Released | Missing path | Not applicable | Application state | Critical | Not proven | New `longhorn-backup` PVC or approved backup storage | Native or quiesced copy, then isolated startup | Not run | Retain the original source | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/podfetch/db` | Podfetch database | `podfetch` | No current pod found | Unknown | `pv-hostpath-general-podfetch-db` / old claim | Released | Missing path | Not applicable | Database | Critical | Not proven | New `longhorn-backup` PVC or approved backup storage | SQLite-aware or application-native backup | Not run | Retain the original source | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/podfetch/podcasts` | Podfetch downloads | `podfetch` | No current pod found | Unknown | `pv-hostpath-general-podfetch-podcasts` / old claim | Released | Missing path | Not applicable | Primary bulk data | Owner review | Not proven | `falcon3/main` if retained | Copy after ownership and replay review | Not run | Retain the original source | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/podgrab/config` | Podgrab configuration | `podgrab` | No current pod found | Unknown | `pv-hostpath-general-podgrab-config` / old claim | Released | Missing path | Not applicable | Application state | Critical | Not proven | New `longhorn-backup` PVC or approved backup storage | Quiesced copy and isolated startup | Not run | Retain the original source | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/podgrab/data` | Podgrab downloads | `podgrab` | No current pod found | Unknown | `pv-hostpath-general-podgrab-data` / old claim | Released | Missing path | Not applicable | Primary bulk data | Owner review | Not proven | `falcon3/main` if retained | Copy after owner review | Not run | Retain the original source | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/` | Terraria broad mount | `terraria`, `terraria-challenge` | Repository manifests declare broad access; no current matching pod found | External writer unknown | Direct hostPath declarations | Not applicable | Unknown | Unknown | Shared application data | Unknown | Not proven | Named workload paths | Replace broad access only after ownership proof | Not run | Retain in place | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/dev-app-fokais` | Unknown | Unknown | Unknown | Unknown | None found | Not applicable | Unknown | Unknown | Unknown | Unknown | Not proven | Unknown | Do not move or delete | Not run | Retain in place | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/rhiannonwalker` | Unknown | Unknown | Unknown | Unknown | None found | Not applicable | Unknown | Unknown | Unknown | Unknown | Not proven | Unknown | Do not move or delete | Not run | Retain in place | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/terraria` | Unknown | Unknown | Unknown | Unknown | None found | Not applicable | Unknown | Unknown | Unknown | Unknown | Not proven | Unknown | Do not move or delete | Not run | Retain in place | `UNKNOWN—HOLD` |
| `/mnt/vault/nfs/general/pv/waylonwalker-com` | Unknown | Unknown | Unknown | Unknown | None found | Unknown | Unknown | Unknown | Unknown | Not proven | Unknown | Do not move or delete | Not run | Retain in place | `UNKNOWN—HOLD` |

## notify-bridge

The live `notify-bridge` application uses image `0.1.64`.

- It mounts Frigate storage at `/media/frigate` as read-only.
- It resolves event media paths and reads files from that mount.
- It reads Frigate event and review messages from MQTT.
- It writes generated media and state to `/data/media` on its Longhorn PVC.
- Its cleanup job deletes old files under `/data/media` only.
- No code path inspected in the live image deletes, renames, or writes under
  `/media/frigate`.
- It can depend on Frigate recordings when an event points to an existing
  thumbnail or clip. The required historical retention period is unknown.

This dependency does not reach the Immich source paths. It remains part of the
vault inventory and blocks a claim that the disk is Frigate-only.

## Target checks

`falcon3/main` is the candidate library target.

- ZFS pool `main`: `ONLINE`
- ZFS errors: zero reported
- Pool free: about 8.90 TB
- Filesystem available: about 8.77 TB
- `rsync`: 3.4.1
- `getfacl` and `getfattr`: available
- ZFS `xattr`: on
- ZFS `acltype`: off (`noacl`)
- Casesensitivity: sensitive
- Normalization: none

No Immich target directory was created. A workload-specific path such as
`/mnt/main/immich/library` remains a candidate, not a completed target.

`longhorn-critical` is not live and is not tracked in `origin/main`. The live
`longhorn-backup` class requests two replicas, uses `Retain`, and selects
`snapshot-hourly`, `backup-daily`, and `backup-weekly`. No Longhorn replica
uses `falcon2/vault`.

Use `longhorn-backup` for an Immich database only after the real source and
PostgreSQL major are found. Check replica placement after a target volume is
created. Do not create that volume in this blocked phase.

## Checkpoint decision

Stop before CP0 and CP1 for Immich.

The declared source paths are missing. The application version and PostgreSQL
major are unknown. The broad NFS export and Samba service leave external
ownership unresolved. Therefore, no library copy, database backup, target
PVC, restore rehearsal, or GitOps cutover is safe.

No source data was deleted. No PV, PVC, Longhorn volume, snapshot, or backup
was deleted. No production resource was changed.
