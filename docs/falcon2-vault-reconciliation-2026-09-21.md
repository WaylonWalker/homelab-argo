# Falcon2 `/mnt/vault` reconciliation

**Snapshot:** 2026-09-21 local time; evidence collection continued through
2026-09-22T02:17Z.

**Scope:** Read-only ownership and writer reconciliation for Falcon2
`/mnt/vault`, with targeted checks on Kubernetes, Falcon3, NFS, Samba, and Git.

**Status:** Discovery, the Frigate application-state backup, and the service-aware
MinIO inventory are complete enough for this phase. No production source data was
deleted or modified. Cleanup is not approved by this report.

## Decision summary

- Keep Frigate recordings and local Frigate runtime data on `/mnt/vault`.
- `FRIGATE CONFIG BACKUP: PROVEN` for the configuration and SQLite application
  state. The backup does not include recordings.
- Keep Longhorn scheduling disabled on `falcon2/vault`.
- Do not resurrect Immich. Its declared Falcon2 paths do not exist.
- Treat Immich, Photoview, Home Assistant, Podfetch, and Podgrab as retired
  workloads. A future Immich deployment is greenfield.
- Treat `.rancher`, the NFS root, and unowned child directories as
  `UNKNOWN—HOLD`.
- Treat the legacy Falcon2 MinIO hostPath as `PARTIALLY REPLACED` with
  `UNIQUE DATA PRESENT` in specific buckets. Keep it.
- Treat `.rancher` MinIO remnants as `UNKNOWN—HOLD`; their ownership and full
  relationship to current collections are not established.
- Do not remove a PV or dataset only because its application is absent.
- Do not call the Photoview data unique. It is historical photo data that was
  not compared with current photo collections.

## Safety boundary

The investigation used read-only SSH, Kubernetes, Argo, Git, NFS, Samba,
Longhorn, S3-aware MinIO queries, and bounded file queries. It did not move,
delete, overwrite, or reconfigure production data. It created one approved
Frigate backup on Falcon3. Disposable local copies of MinIO data and restored
Frigate state were used for isolated tests and then removed.

The working checkout was dirty and diverged from `origin/main`. The report was
written in a clean detached worktree based on `origin/main`.

The default rule is `UNKNOWN—HOLD`. A future cleanup requires all of these:

1. Identify the owner and current writer.
2. Identify the replacement, or record that the data is rebuildable.
3. Preserve the source until the replacement is tested.
4. Obtain explicit approval for the cleanup.

## Falcon2 filesystem baseline

The final live query reported the following values for `/mnt/vault`:

| Item | Value |
| --- | --- |
| Device | `/dev/sdb1` |
| Filesystem | `ext4` |
| Total | `3,936,789,286,912` bytes |
| Used | `3,723,023,343,616` bytes |
| Available | `13,711,495,168` bytes |
| Use | `100%` |

The `Available` value is the filesystem space available to the normal writer.
The difference between `Total - Used` and `Available` is approximately `200 GB`
of ext4 reserved space. It is not usable cleanup capacity for the Frigate or NFS
writers, so this table must not be read as having `214 GB` of free space.

The owner decision is that Frigate retention intentionally consumes this disk.
This phase does not delete recordings, change retention, or use the small normal
free-space value as a cleanup target. If Frigate retention or health degrades,
capacity planning is a separate operational review.

Top-level entries are `nfs`, `.rancher`, `longhorn`, and `.Trash-1000`.

The Longhorn disk `falcon2/vault` uses `/mnt/vault/longhorn`. Scheduling is
disabled, and no Longhorn replica uses this disk. Do not enable scheduling.

## Classification table

| Path or dataset | Evidence | Current writer or consumer | Classification | Confidence | Action |
| --- | --- | --- | --- | --- | --- |
| `/mnt/vault/nfs/general/pv/frigate4/frigate-storage` | About `3.4 TB` and `1,455,332` files in the prior bounded inventory | Frigate writes it. `notify-bridge` reads it read-only. | `KEEP` / active | High | Keep in place. Do not use as a migration workspace. |
| `/mnt/vault/nfs/general/pv/frigate4/frigate-config` | Current SQLite database, WAL, YAML, and runtime state are present. A tested Falcon3 backup now exists. | Frigate reads and writes the path. | `KEEP` / `FRIGATE CONFIG BACKUP: PROVEN` | High | Keep in place. Use the versioned Falcon3 backup and add recurring automation later. |
| `/mnt/vault/nfs/general/backup/k3s` | Daily K3s backup files reach the snapshot date. | A K3s backup job writes the directory. | `ACTIVE HERE` | High | Keep. Do not use this same filesystem as the only backup target. |
| `/mnt/vault/nfs/general/pv/dev-waylonwalker-com` | About `40 MB`. | Dev site and cleanup jobs mount the path. | `ACTIVE HERE` | High | Keep until the build workspace has a tested replacement. |
| `/mnt/vault/nfs/general/pv/shots/cache` | About `45 KB`. The PV has a deletion timestamp from `2026-03-07`, but the claim remains bound. | `shot` pods use the claim on all three nodes. | `ACTIVE HERE` | High | Do not remove the PV or path. Resolve the stuck deletion separately. |
| `/mnt/vault/nfs/general/pv/shots-dev/cache` | About `8 KB`. | `shots-dev` pods use the claim on all three nodes. | `ACTIVE HERE` | High | Keep until the workload moves or becomes retired. |
| `/mnt/vault/nfs/general/pv/minio/minio-storage` | About `3.14 GB`, with 17 S3-visible buckets. The newest legacy object is from `2025-07-12`. | The old PV is bound, but the live MinIO pod uses `minio-storage-longhorn`. | `PARTIALLY REPLACED` / `UNIQUE DATA PRESENT` | High | Keep. The `mypages` and `thoughts` source objects are not in current MinIO; do not delete. |
| `/mnt/vault/nfs/general/pv/reader/markata-cache` | About `828 MB`. | The PV is bound, but no current reader pod mounts it. | `REBUILDABLE` | Medium | Keep until external writers are excluded. Then consider a cache cleanup. |
| `/mnt/vault/nfs/general/pv/markata-go-docs-build` | The path is missing. The PV is `Released`. | Current docs builds use Longhorn site storage. | `REBUILDABLE` / data absent | High | Retain the PV record until normal PV cleanup is approved. |
| `/mnt/vault/nfs/general/pv/waylonwalker-com/site` | About `674 MB`. The latest directory content is from March 2025. | Current production web output uses Falcon3 Walkershare. Current build jobs use Longhorn. | `PROBABLE MOVED` | Medium | Keep until a content comparison and owner approval exist. |
| `/mnt/vault/nfs/general/pv/rhiannonwalker` | About `360 MB`. | No pod uses this path. Current Rhiannon notes workloads use Longhorn claims. | `PROBABLE MOVED` | Medium | Keep until the old content is compared with the current source and site. |
| `/mnt/vault/nfs/general/pv/dev-app-fokais` | About `131 KB`. | No current namespace or pod was found. | `UNKNOWN—HOLD` | Low | Identify the owner before any action. |
| `/mnt/vault/nfs/general/pv/terraria` | About `9.5 MB`. | No current `terraria` namespace or matching pod was found. | `UNKNOWN—HOLD` | Low | Retain. Historical manifests use a broad NFS mount. |
| `/mnt/vault/.rancher` | A previous bounded estimate was about `285.8 GB`. It contains old K3s local-path data, including two MinIO remnants and historical Photoview data. | Current K3s uses `/var/lib/rancher/k3s`; complete old-path writer proof is unavailable. | `UNKNOWN—HOLD` | Low | Do not scan broadly, move, or delete. Review bounded MinIO evidence below separately. |
| `/mnt/vault/nfs` | About `3.43 TB` in the prior bounded inventory. | NFS exports the root to `*`; external writers are not proven absent. | `UNKNOWN—HOLD` | Low | Keep the export and data unchanged until client ownership is known. |
| `/mnt/vault/.Trash-1000` | Small user-trash directory. | No writer was identified. | `UNKNOWN—HOLD` | Low | Do not empty it in this phase. |

## Historical applications with missing data

The following historical applications have no current workload, and their old
Falcon2 paths are missing. The Immich PVs are `Available`; the other PVs below
are `Released`. These applications are retired. No recovery work is required.

| Application | PVs | Current result |
| --- | --- | --- |
| Immich | `immich-library-pv`, `immich-postgres-pv`, `immich-typesense-pv` | `RETIRED`; no namespace, pod, Argo application, or source path exists. A future deployment is greenfield. Do not resurrect. |
| Photoview | Historical `.rancher` local-path data | `RETIRED`; historical photo data remains on Falcon2. It was not compared with current photo collections, so uniqueness is not established. Future cleanup candidate after owner review. Do not recover or delete it here. |
| Home Assistant | `pv-hostpath-general-home-assistant-config` | `RETIRED`; no namespace or pod exists and the path is missing. No recovery work is required. |
| Podfetch | `pv-hostpath-general-podfetch-db`, `pv-hostpath-general-podfetch-podcasts` | `RETIRED`; no namespace or pod exists and both paths are missing. No recovery work is required. |
| Podgrab | `pv-hostpath-general-podgrab-config`, `pv-hostpath-general-podgrab-data` | `RETIRED`; no namespace or pod exists and both paths are missing. No recovery work is required. |

The missing paths are not evidence that another copy is disposable. They only
show that these PV declarations no longer point to data on Falcon2.

## Current Kubernetes writer evidence

The following live mounts were confirmed:

- `frigate/frigate-84ff867d5b-jbxx6` writes the Frigate config and recording paths.
- `notify-bridge` reads the Frigate recording path at `/mnt/vault/nfs/general/pv/frigate4/frigate-storage`.
- `dev-waylonwalker-com` mounts the old build hostPath in active build jobs.
- `shot` and `shots-dev` mount their active cache claims.
- `minio/minio2-6f8ffc875-ns7vg` uses Longhorn PVC `minio-storage-longhorn`.
- `markata-go-docs` uses Longhorn PVC `markata-go-docs-site`.
- `waylonwalker-com` uses Longhorn site storage and Falcon3 Walkershare output.
- Current Rhiannon notes workloads use Longhorn claims on Falcon3.

No current pod mounts the old Home Assistant, Podfetch, Podgrab, or Immich
paths. No current pod mounts the old `waylonwalker-com` vault path.

## `.rancher` evidence

The old directory contains local-path data for several former workloads,
including old MinIO, Frigate, Photoview, Wyze, Syncthing, Matrix, ntfy,
Kanboard, registry, and application data.

The following Photoview directory contains historical photo data:

```text
/mnt/vault/.rancher/k3s/storage/pvc-5e571b8e-1c24-428e-aea9-40ef0de5fdcc_photoview_photoview/waylons-camera
```

It contains about `7.57 GB` and `642` files. It was not compared with the
current photo collections, so its uniqueness is not established. This data
needs owner review, does not justify rebuilding Immich, and must remain
untouched.

The current user cannot read all old K3s storage. `sudo -n` is unavailable, and
bounded scans reached permission errors and timeouts. The directory remains
`UNKNOWN—HOLD`.

## MinIO service-aware inventory

Filesystem directory names were not treated as S3 bucket names. The legacy
Falcon2 store was copied to a disposable local directory and opened with the
historical MinIO image `RELEASE.2025-04-08T15-41-24Z`. The original Falcon2
directory was not mounted by that test server and was not modified. The current
primary store was queried through its live S3 service. Object names were not
included in this report.

### Store boundaries

These stores are separate and must not be combined during cleanup:

| Store | Service and storage | Result |
| --- | --- | --- |
| Longhorn backup object store | Namespace `minio-longhorn-backup`; hostPath `/mnt/main/minio-longhorn-backup`; bucket `longhorn-system` | Critical backup infrastructure. The final `just storage-backup-check` observed `956` backup objects, `946` completed, and `115` backup-volume objects. Do not touch or compare as application data. |
| Current primary MinIO | Namespace `minio`; pod `minio2-6f8ffc875-ns7vg`; image `minio/minio:RELEASE.2025-04-08T15-41-24Z`; PVC `minio-storage-longhorn`; PV/Longhorn volume `pvc-1b9b4bd6-0175-4b9e-82ef-ce569af150b5`; `50Gi`, StorageClass `longhorn-backup`, configured for 2 replicas and currently healthy/attached | `ACTIVE PRIMARY`. Read-only S3 inventory below. |
| Legacy Falcon2 MinIO | `/mnt/vault/nfs/general/pv/minio/minio-storage`; PV `minio-pv`; old claim `minio/minio-storage`; about `3.14 GB` | No current pod uses the old claim. S3 inventory proves replacement only by bucket/object subset, not for the whole store. Keep. |
| `.rancher` MinIO remnants | `pvc-700cef2a-44f4-41bd-b347-a254c99d89f1_minio_minio-storage` (`418M`) and `pvc-b92579cb-e1ca-49f4-a26c-fd8870dd5f7e_minio-fokais_minio-storage` (`4.3M`) | Historical local-path stores. Bounded S3 inventory is below; ownership and complete replacement are not proven. `UNKNOWN—HOLD`. |

S3-visible buckets in the current primary and legacy Falcon2 stores reported
versioning enabled and no lifecycle configuration. The `.rancher` main store's
`waylonwalker.com` bucket returned an indeterminate versioning result. Dates are
point-in-time observations; active current buckets can change between queries.

### Current primary versus legacy Falcon2

The table gives `objects / logical bytes`, followed by the oldest and newest
visible object timestamps. `Exact old payloads` means the legacy key, size, and
ETag matched in the current bucket. ETags are used as representative S3
metadata, not as a universal content hash for multipart objects.

| Bucket | Legacy Falcon2 | Current primary | Object-level reconciliation |
| --- | --- | --- | --- |
| `config-editor` | `2 / 15,530`; 2025-01-25 14:36:57 to 14:37:03 | `2 / 15,530`; 2025-01-25 14:36:57 to 14:37:03 | All 2 exact; no unmatched legacy objects. |
| `dropper` | `752 / 1,576,771,371`; 2024-12-15 to 2025-07-07 | `10,537 / 37,147,346,009`; 2024-12-15 to 2026-09-21 | All 752 exact; 9,785 current extras. `PROVEN REPLACED` for the legacy subset. |
| `duckdb-playground` | `2 / 18,450,644`; 2025-03-14 to 2025-03-15 | `2 / 18,450,644`; 2025-03-14 to 2025-03-15 | All 2 exact; no unmatched legacy objects. |
| `k8s-pages` | `9,402 / 373,868,148`; 2025-02-04 to 2025-07-11 | `9,501 / 378,995,585`; 2025-02-04 to 2026-07-19 | `9,397` exact, `5` common objects changed, `99` current extras. `PARTIALLY REPLACED`. |
| `longhorn-system` | `612 / 260,747,955`; 2025-03-29 to 2025-03-30 | `612 / 260,747,955`; 2025-03-29 to 2025-03-30 | All 612 exact. This is the application bucket, not the separate Longhorn backup store. |
| `my-test-bucket` | `1 / 34`; 2024-12-04 | `1 / 34`; 2024-12-04 | Exact; no unmatched legacy objects. |
| `mypages` | `8 / 40,686`; 2025-02-02 to 2025-02-04 | `0 / 0` | All 8 legacy objects are unmatched. `UNIQUE DATA PRESENT`; do not delete. |
| `photoprism` | `9 / 2,563,861`; 2025-04-07 | `9 / 2,563,861`; 2025-04-07 | All 9 exact; no unmatched legacy objects. |
| `postiz` | `444 / 14,995,088`; 2025-04-14 to 2025-07-12 | `696 / 21,344,521`; 2025-04-14 to 2026-09-20 | All 444 exact; 252 current extras. `PROVEN REPLACED` for the legacy subset. |
| `redis` | `21 / 33,565`; 2025-06-28 to 2025-07-11 | `21 / 33,565`; 2026-08-27 to 2026-09-03 | Same 21 keys, but all 21 ETags changed. `PARTIALLY REPLACED`; old payload identity is not proven. |
| `rhiannonwalker` | `0 / 0` | `0 / 0` | No objects in either store. |
| `rhiannonwalker-dev` | `183 / 4,609,325`; 2025-03-02 | `183 / 4,609,325`; 2025-03-02 | All 183 exact; no unmatched legacy objects. |
| `shots` | `20,360 / 523,644,907`; 2024-12-05 to 2025-07-12 | `66,914 / 2,026,529,925`; 2024-12-05 to 2026-09-21 | All 20,360 exact; 46,554 current extras. `PROVEN REPLACED` for the legacy subset. |
| `shots-dev` | `244 / 5,605,222`; 2025-01-16 to 2025-01-20 | `570 / 22,265,915`; 2025-01-16 to 2026-03-07 | All 244 exact; 326 current extras. `PROVEN REPLACED` for the legacy subset. |
| `shots2` | `7 / 597,856`; 2025-02-15 | `7 / 597,856`; 2025-02-15 | All 7 exact; no unmatched legacy objects. |
| `thoughts` | `4 / 1,828,747`; 2025-07-11 to 2025-07-12 | `2 / 2,291,564`; 2026-05-10 to 2026-09-21 | All 4 legacy objects are unmatched. `UNIQUE DATA PRESENT`; do not delete. |
| `waylonwalker.com` | `1,119 / 82,605,026`; 2025-01-02 | `1,119 / 82,605,026`; 2025-01-02 | All 1,119 exact; no unmatched legacy objects. |

Current-only buckets not present in the legacy Falcon2 hostPath are:

| Bucket | Current objects / logical bytes | Oldest to newest visible object |
| --- | --- | --- |
| `nextcloud` | `8 / 99,435` | 2025-07-29 to 2025-08-20 |
| `performpeoria-dev-cnpg-backups` | `47 / 33,616,906` | 2026-09-13 to 2026-09-20 |
| `performpeoria-prod-cnpg-backups` | `125 / 129,824,241` | 2026-05-06 to 2026-09-20 |

Representative objects from every legacy bucket classified as a replaced
subset were read successfully from both the isolated legacy server and the
current primary. The old `mypages` and `thoughts` objects have no current
bucket counterparts. A hidden `try-litestream` directory was visible inside
the copied legacy `.minio.sys` area but was not returned as an S3 bucket; it is
not classified as disposable.

### `.rancher` MinIO inventory

The two bounded local-path stores are separate from the legacy hostPath store:

| Store | S3-visible buckets and aggregate data | Comparison evidence |
| --- | --- | --- |
| `pvc-700cef2a-44f4-41bd-b347-a254c99d89f1_minio_minio-storage` (`418M`) | `images.thoughts`: `4,542 / 119,760,946`; `matrix.wayl.one`: `1,595 / 260,984,687`; `nic`: `0`; `thoughts`: `27 / 421,094`; `waylonwalker.com`: `833 / 2,764,225` | All 27 old `thoughts` objects are absent from current `thoughts`. For `waylonwalker.com`, `431` payloads matched, `397` common payloads changed, and `5` old objects are absent. The other bucket names have no current bucket counterpart. `UNKNOWN—HOLD`. |
| `pvc-b92579cb-e1ca-49f4-a26c-fd8870dd5f7e_minio-fokais_minio-storage` (`4.3M`) | `dev-shots`: `9 / 154,240`; `local-shots`: `37 / 686,536`; `shots`: `1 / 5,620`; `voices`: `2 / 3,023,226` | The one old `shots` key is present in current `shots` but its ETag changed. The other buckets have no current bucket counterpart. `UNKNOWN—HOLD`. |

The `.rancher` buckets may contain historical site, image, voice, Matrix, or
other application data. They are not promoted to cleanup candidates until an
owner identifies each collection and approves a disposition.

## NFS and Samba

`showmount -e 127.0.0.1` reports this export:

```text
/mnt/vault/nfs *
```

NFS services are active. `showmount -a` and `/var/lib/nfs/rmtab` showed no
clients, and the cluster has no NFS PV or `falcon-nfs` PVC. Falcon1 and Falcon3
showed Longhorn CSI NFS mounts, not mounts of Falcon2 vault data.

The readable `/etc/exports` contains only comments. `exportfs` cannot read the
runtime export table because it cannot lock `/var/lib/nfs/.etab.lock`. External
clients therefore remain unresolved.

Samba is active on Falcon2, but the readable configuration contains no explicit
`/mnt/vault` share. It exposes only default printer paths. No established
connections were found on ports `139` or `445`. The configuration includes a
Samba registry, so this result does not prove that no dynamic share exists.

Samba does not explain the current Walkershare data. Walkershare runs on Falcon3
at `/mnt/main/walkershare`.

## Frigate backup result

Live state was established before the backup:

- Pod `frigate-84ff867d5b-jbxx6` runs on `falcon2` with image tag `stable`,
  image digest `sha256:d4351369984d4a9e2a49ac59736f6490856a7ea11f7790040746d21496967010`,
  and API version `0.17.2-3d4dd3a`.
- Config hostPath: `/mnt/vault/nfs/general/pv/frigate4/frigate-config`.
- Recording hostPath: `/mnt/vault/nfs/general/pv/frigate4/frigate-storage`.
- The database is SQLite with `journal_mode=wal`.
- At collection, `frigate.db` was `1,115,684,864` bytes, its WAL was
  `4,672,112` bytes, and `backup.db` was `1,268,838,400` bytes. The config
  directory also contained `config.yaml`, `backup_config.yaml`,
  `config.yaml.bak.1774756595`, `go2rtc_homekit.yml`, `.jwt_secret`, and
  Frigate-managed state files.

The backup is:

```text
falcon3:/mnt/tank/backups/critical-files/frigate/20260922T012617Z/
├── config/
├── database/frigate.db
├── database/backup.db
├── manifest.txt
└── checksums.sha256
```

The two database files were created with the SQLite online backup API through
`sqlite3.Connection.backup` from read-only source connections. The live WAL and
SHM files were not copied as raw sidecars; their committed state was included
in the standalone database snapshots. Recordings were not included. The
manifest records the source paths, image digest, Frigate version, source UID/GID
and modes, backup method, and database metadata. The backup directories are
mode `700`; all backup files are mode `600` on Falcon3.

The primary and secondary SQLite files were backed up sequentially, not as one
cross-database transaction. Each is independently consistent, and the primary
`frigate.db` is the database that ties Review/events to retained media. The
ordinary config files were copied while Frigate remained live; their source
metadata and destination checksums are recorded, but ordinary files do not have
SQLite's transactional snapshot guarantee.

The repository archive `frigate-backups/frigate-config-backup-20260328-225654.tgz`
contains configuration YAML only and remains historical context, not the live
database backup.

Restore proof:

1. Source snapshot hashes matched the `kubectl cp` staging copies and the SCP
   copies on Falcon3.
2. Falcon3 `checksums.sha256` passed, and a fresh copy restored from Falcon3
   passed the same checksums.
3. Read-only SQLite `PRAGMA integrity_check` returned `ok` for both databases;
   the restored `frigate.db` has 12 tables and the restored `backup.db` has 9.
4. The exact live image digest accepted the restored configuration with
   `python3 -u -m frigate --validate-config`, exited `0`, and reported that no
   migration was needed and that the config was valid.
5. A second isolated run with `--network none`, an empty media directory, and
   no Coral/GPU devices started Frigate, opened the database, ran migrations
   with nothing to migrate, started FastAPI, and then stopped after the
   intentionally unavailable detector and cameras failed. It could not touch
   production cameras, MQTT, ports, recordings, or the source database.

Therefore:

```text
FRIGATE CONFIG BACKUP: PROVEN
```

This proves recoverability of the configuration and database application state,
not a full recording-tree or hardware restore. Falcon3 `tank` is a second local
host copy, not off-site disaster recovery. Recurring automation was not changed
in this session; a visible, checksummed, versioned daily/weekly job with
sensible rotation and an off-node copy remains a follow-up.

### Proposed recurring automation (not deployed)

Use a Git-managed Falcon3 host automation or an explicitly owned systemd timer,
not an undocumented cron entry. Each run should:

1. Use a lock so only one run operates at a time.
2. Create SQLite snapshots with the same online backup API while Frigate stays
   running.
3. Capture the config files, source metadata, image digest, and backup method
   into a new temporary directory on `tank`.
4. Write checksums, run SQLite integrity checks, and atomically rename the
   directory only after verification passes.
5. Keep a small rotation, such as seven daily copies and four weekly copies,
   after measuring the actual logical and compressed change rate.
6. Report failures and later replicate selected copies off-node or off-site.

The current two database snapshots are about `2.4 GB` logical data, while
`tank` has about `1.52T` available. This is enough room for a modest rotation,
but the retention count must remain bounded and the off-site destination must
be chosen before automation is promoted.

## Falcon3 destination evidence

Falcon3 ZFS pools `main` and `tank` are online with zero reported read, write,
or checksum errors. `tank` has about `1.52T` available in the live `zfs list`
output. The approved backup path is `/mnt/tank/backups/critical-files/frigate`;
the live host resolves `/mnt/tank` through `/var/mnt/tank`. The completed
Frigate backup has `2,384,555,530` bytes of apparent tree size
(`2,384,523,264` bytes in the two database files) and uses about
`1,308,685,312` allocated bytes because the SQLite files contain sparse/free
pages. The known primary bulk-data path remains `/mnt/main/walkershare`.

This is a useful local second host copy because the source is on Falcon2. It is
not disaster recovery: `main` and `tank` share the Falcon3 chassis, power, and
site. `tank` encryption is currently `off`; the backup contains secret-bearing
Frigate configuration and is protected here by the `700` directory and `600`
file modes, but it is not encrypted at rest. Do not put this copy in Git or
replicate it off-site without encryption, access control, and a rotation plan.
An off-node or off-site copy is still required for critical Frigate state.

Targeted observations found these existing photo collections:

- `/mnt/main/walkershare/parents/photos`: about `805 GB`.
- `/mnt/main/walkershare/waylon/photos`: about `49 GB`.
- `/mnt/main/walkershare/rhiannon/photos`: about `32 GB`.
- `/mnt/main/google-takeout`: about `457 GB`.

No observation links these collections to the missing Immich paths. The old
Photoview data on Falcon2 is historical data; it was not compared with these
collections and needs owner review before any photo cleanup.

## Git evidence

Git history supports workload intent, not data movement:

- Frigate hostPath changes: `0cbce27`, `4c9d1b1`, and `2d542f3`.
- MinIO hostPath declaration: `4064ae1`.
- Immich disable and removal: `e62d981`, `9319a0a`, and `a6a0c2a`.
- Home Assistant retirement: `1a9af11`.
- Podfetch retirement: `0686eb9`.
- Podgrab retirement: `7157fdb`.
- Photoprism Walkershare move intent: `25ebc33`.

No Git commit proves that a source dataset was copied, compared, restored, and
cut over successfully.

## Backup gate and limitations

`just storage-backup-check` passed before and after this phase. The final live
Longhorn `BackupTarget/default` was available, the backup target was reachable,
and the target last synced at `2026-09-22T02:13:26Z`. The final check found
`956` backup objects, `946` completed objects, and `115` backup-volume objects.
The `falcon2/vault` Longhorn disk remained `allowScheduling=false` with zero
replicas.

The check does not prove a restore. The `aws` command is not installed, and no
Longhorn disposable restore was run in this phase. That limitation applies to
Longhorn data only; the separate Frigate hostPath backup was restored and tested
as documented above.

The following evidence gaps remain:

- Complete `.rancher` ownership and size breakdown beyond the bounded MinIO and
  Photoview observations.
- External NFS client and writer inventory.
- Dynamic Samba registry share inventory.
- Owner disposition for unmatched legacy MinIO objects and historical `.rancher`
  MinIO buckets.
- Content comparison for old site and Rhiannon paths.
- An off-site copy and recurring automation for the now-proven Frigate backup.

## Next actions

1. Obtain owner review for the unmatched legacy MinIO buckets and the historical
   Photoview directory.
2. Keep all `UNKNOWN—HOLD` paths and all unmatched MinIO objects unchanged.
3. Define recurring Frigate backup automation with rotation, checksums, and an
   off-node/off-site copy. Do not add a hidden cron job.
4. Resolve the active `shot` PV deletion timestamp without deleting its claim
   or data.
5. Revisit cleanup only after owner approval, a tested replacement or rebuild
   path, and a rollback plan.

## Final classifications for a later cleanup proposal

### ACTIVE ON FALCON2 — KEEP

- Frigate recording retention storage.
- Frigate configuration and database source files.
- The K3s backup path at `/mnt/vault/nfs/general/backup/k3s`.
- The active `dev-waylonwalker-com` build hostPath.
- The active `shots` and `shots-dev` cache paths.

### REBUILDABLE

- Reader and Markata build caches after external writers are excluded.
- The missing `markata-go-docs-build` path and its released PV data.
- Retired application paths that are already absent; no recovery is required.

### UNKNOWN—HOLD

- The `.rancher` tree, including both bounded MinIO remnants and Photoview
  historical data.
- The NFS root and any external clients or writers.
- Dynamic Samba registry shares.
- `/mnt/vault/nfs/general/pv/dev-app-fokais`, `/mnt/vault/nfs/general/pv/terraria`,
  and `.Trash-1000`.
- The hidden legacy MinIO `.minio.sys` `try-litestream` area.

### FUTURE CLEANUP CANDIDATES — NOT APPROVED

- Retired Immich, Home Assistant, Podfetch, and Podgrab PV records after a
  separate stale-PV review. No PV object is deleted here.
- Photoview historical data after owner review and a real collection comparison.
- Rebuildable caches after writer and mount checks.
- Legacy MinIO buckets only after the unmatched `mypages`, `thoughts`, changed
  `redis` payloads, and `.rancher` collections have an owner and disposition.
- Old site and Rhiannon paths after content comparison.

No source data, PV, PVC, Longhorn volume, snapshot, or production MinIO object
was deleted. No production workload, Frigate retention policy, MinIO service,
or Longhorn scheduling setting was changed. The only persistent data addition
was the approved Frigate application-state backup on Falcon3.
