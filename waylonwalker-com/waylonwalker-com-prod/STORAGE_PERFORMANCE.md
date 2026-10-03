# Production Builder Admin storage measurements

These measurements were taken on 2026-09-27/28 in the live cluster. They are
spot checks, not sustained throughput guarantees. The workload creates many
small files, so sequential throughput alone cannot predict build time.

## Comparable filesystem benchmark — 2026-09-28, 14:00–14:14 UTC

| Node / mounted target | Physical backing | Write + final fsync median (range) | Direct read median | 4 KiB O_SYNC write | P99 write latency |
| --- | --- | ---: | ---: | ---: | ---: |
| falcon3 `/var/tmp` | 500 GB `CT500P5PSSD8` NVMe | **768 (757–970) MiB/s** | 2,098 MiB/s | **922 IOPS** | 4.1 ms |
| falcon2 `/var/tmp` | 1 TB `CT1000MX500SSD1` SSD | 270 (233–272) MiB/s | 330 MiB/s | 394 IOPS | 9.4 ms |
| falcon1 `/var/tmp` | 256 GB SSD | 178 (167–192) MiB/s | 235 MiB/s | 158 IOPS | 12.4 ms |
| falcon3 `tank` at `/mnt/tank` | Mirror of two 4 TB `ST4000VN008-2DR1` HDDs | 126 (97–146) MiB/s | 127 MiB/s | 70 IOPS | 102 ms |
| falcon3 `wd3tb` | 3 TB `WDC WD30EFRX-68E` HDD | 102 (94–102) MiB/s | 99 MiB/s | 16 IOPS | 125 ms |
| falcon2 `/mnt/vault` | 4 TB `ST4000VN008-2DR1` HDD | 88 (55–105) MiB/s | 41 MiB/s | 15 IOPS | 221 ms |
| falcon3 `main` at `/mnt/main` | Mirror of two 14 TB `ST14000NM005G-2K` HDDs | 78 (78–82) MiB/s | 94 MiB/s | 55 IOPS | 58 ms |
| Production `/data/site` on falcon3 | Longhorn: falcon3 NVMe + falcon2 HDD | 49 (47–49) MiB/s | 78 MiB/s | 163 IOPS | 51 ms |

These numbers describe **mounted filesystems under live cluster load**. They
are not raw drive specifications or a power-loss test. Each write trial used
512 MiB of incompressible data with `fio`, direct I/O, and a final `fsync`. The write
result divides 512 MiB by the full wall time, including the final `fsync`.
The table gives the median and range of three trials. Each read trial used
direct I/O on the file from its write trial. Read results can still benefit
from device caches or ZFS ARC; they are not cold-read guarantees.

The 4 KiB result is one 15-second random-write test per target. `O_SYNC`
made each write synchronous. Its IOPS and P99 latency describe one job with
one outstanding write, not maximum parallel IOPS. The ZFS pools have
`sync=standard` and compression enabled. During the ZFS tests, `zpool iostat`
showed physical writes to the matching pool. No raw pool member received
test writes. The script used a private temporary directory on each mount and
removed it afterward. Reproduce the job with
`scripts/benchmark-storage-target.sh` in a pod that has `fio`, `jq`, and
nanosecond-resolution `date`.

The HDD mirrors are measured **per pool**, not per member. Writing a raw
member of an active ZFS mirror would put data at risk. Falcon1 has one
physical SSD, falcon2 has one SSD and one HDD, and falcon3 has one NVMe and
five HDDs. Longhorn virtual disks, the falcon2 Frigate loop cache, and
falcon1's empty card-reader slots are not additional physical drives.

### Earlier spot checks (different methods and load)

| Node and path | Filesystem | 256 MiB direct sequential write | Notes |
| --- | --- | ---: | --- |
| falcon3 root (`/dev/nvme0n1p4`) | XFS on NVMe | ~1,300 MB/s | Local host path, 107 GiB free at test time. |
| falcon2 root (`/var/lib/longhorn`) | ext4 on LVM | ~341 MB/s | 85% full at test time. |
| falcon1 root (`/var/lib/longhorn`) | XFS on SSD | ~167 MB/s | ~80% full at test time. |
| falcon1 local host path (`/mnt/vault`) | XFS on SSD | ~225 MB/s | Same device as the root filesystem. |
| falcon2 `/mnt/vault` | ext4 on IronWolf HDD | ~140 MB/s | Different local disk on each node. |
| falcon3 Longhorn `wd3tb` (`/var/lib/longhorn/disks/wd3tb`) | ext4 on HDD | ~33 MB/s | The slow replica disk. |

## Falcon3 ZFS pools

The sequential-write table does not rank either ZFS pool. Falcon3 also has
four physical HDDs in two ZFS mirrors. The values below come from live
`zpool list -v -p`, `zpool status -P`, and `zfs list -p` on 2026-09-28.
These disks are separate from falcon3's NVMe and Longhorn `wd3tb` HDD.
The cluster has nine physical drives: one on falcon1, two on falcon2, and
six on falcon3. Zero-size card-reader slots, loop devices, and Longhorn
`VIRTUAL-DISK` devices are not additional physical drives.

| Pool and mount | Mirror members | Pool size | Allocated | Pool free | Dataset available | Health |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `main` at `/mnt/main` | Two 14 TB `ST14000NM005G-2K` HDDs (`sdc1`, `sdd1`) | 13.98 TB | 5.18 TB | 8.80 TB | 8.67 TB | ONLINE |
| `tank` at `/mnt/tank` | Two 4 TB `ST4000VN008-2DR1` HDDs (`sda1`, `sdb1`) | 3.99 TB | 2.25 TB | 1.74 TB | 1.61 TB | ONLINE |

Both pools report zero read, write, and checksum errors. Their most recent
recorded scrubs completed on 2025-04-15. These are old scrub results, not
recent proof of disk health. The `main` pool holds media, Nextcloud,
Walkershare, static sites, and the Longhorn backup MinIO data. The `tank`
pool holds Steam, personal data, Git data, VMs, and other datasets.
The backup MinIO PV uses `/mnt/main/minio-longhorn-backup` on the `main`
parent dataset. It does not use the nearly empty `main/longhorn-backup`
child dataset. Both ZFS pools share falcon3's power and chassis, so neither
pool is an off-node backup for the other.

The tests wrote 256 MiB with BusyBox `dd bs=1M count=256 oflag=direct` to
temporary files. The test removed each file afterward. Tests ran at different
times, so load and cache effects can change the results. A separate 512 MiB
direct write to falcon3's `/mnt/main` ZFS pool reported ~4,300 MB/s. This
result is **not a measured sustained HDD write rate**. ZFS cache and
asynchronous writes can affect the result. The comparable tests above
include a final `fsync` and observed pool writes through `zpool iostat`.
Longhorn v1 could **not** run a replica there. Replica rebuild failed with
`file extent is unsupported: operation not supported`. Do not tag this ZFS
path for Longhorn v1 replicas.

The `longhorn-build-fast` class selects two tagged disks: falcon3 NVMe at
`/var/lib/longhorn/fast-nvme`, and falcon2 HDD at `/mnt/vault/longhorn`.
The `fast` disk tag does **not** mean that both replicas use SSDs. Writes
still replicate over the network to the falcon2 HDD.
In a disposable PVC on falcon3, a 256 MiB direct write took 5.54 seconds
(46.2 MB/s). Both replicas were healthy. A disposable one-replica, strict-local
PVC on falcon3 NVMe wrote the same amount in 1.83 seconds (139.8 MB/s).
The one-replica result is **not** the durability of `longhorn-build-fast`.

After cutover, the production Builder Admin wrote 2,000 files of 4 KiB each
on each mount with `benchmark-builder-storage.sh`. The test used one shell
loop per mount, not direct I/O. Results:

| Mount | 2,000-file write | File rate | Notes |
| --- | ---: | ---: | --- |
| `/data/site` (two-replica fast Longhorn) | 8.779s | 227.8 files/s | Live build and release volume. |
| `/tmp` (container overlay) | 8.657s | 231.0 files/s | Ephemeral. |
| `/data/cache` (ZFS) | 8.092s | 247.2 files/s | Persistent Markata cache. |

The shell loop, directory creation, and `cp` overhead limit this test. These
results do not show a large difference among mounts for this small workload.

A test of 2,000 files of 4 KiB each, followed by `sync`, took 5 seconds on
the two-replica PVC. Direct host paths took 4 seconds on falcon2's IronWolf,
16 seconds on falcon3's NVMe in one run, and 4 seconds on falcon3's ZFS pool.
These tests used a shell loop and second-resolution timing. They do not
measure the full Markata build workload.

## Builder Admin evidence

The production namespace is `waylonwalker-com-prod-notes`, not the older
`waylonwalker-com` CronJob namespace. Builder Admin seeds `.build-work` from
the current release, writes the build there, and renames the work directory
into `releases`. The work directory must remain on the same filesystem as
the release directory. A separate build PVC alone cannot accelerate this
process without a change to Builder Admin's promotion logic.

The `build-1790476111698552099` record reported 3,549.5 seconds total,
including 451.4 seconds to prepare and 3,098.1 seconds to build. Its log
reported `publish_html` at 15m42s, `css_minify` at 19m12s, and `js_minify`
at 11m53s. The site PVC had 19 GiB used out of 20 GiB (96%) during the
investigation. It had two replicas: falcon2's root disk and falcon3's
`wd3tb` HDD. The log does not prove that all elapsed time was disk wait.

The first production builds after cutover were scheduled refreshes. The
record at 04:25 UTC took 304 seconds. The 12 refresh builds from 06:04 to
11:34 UTC took 98 to 256 seconds, with build phases from 46 to 96 seconds.
Earlier refresh records on the original volume include 764 and 973 seconds. A manual
full build after cutover was not measured. Differences in source changes and
cache state prevent a controlled before/after speedup claim.

The benchmark for the *different* `go-waylonwalker-com-notes` site lives in
`waylonwalker-com/go-waylonwalker-com/BUILDER_STORAGE_BENCHMARK.md`.

## Effect of markata-go PR #1341

[PR #1341](https://github.com/WaylonWalker/markata-go/pull/1341) adds an
optional node-local build workspace to Builder Admin. Without this option,
Builder Admin writes `.build-work` on the site PVC. The PR copies a completed
workspace back to the site PVC before promotion when the two paths use
different filesystems. It does not change the publisher or minifier code.

**Impact: medium before a site-volume migration, low to medium after it.**
Node-local workspace writes can speed up prepare and build I/O. The final
promotion still copies all output to the site volume. The observed plugin
durations do not isolate CPU time from I/O wait, so no speedup is guaranteed.
PR #1341 merged on 2026-09-28. The deployed `sha-6540c44` image includes
the workspace feature, but `builderAdmin.workspace.enabled` is still false.
To use the feature, configure its Helm workspace mount and work directory.
Measure a comparable full build before and after enabling it. A node-local
workspace still needs a complete promotion copy onto the site PVC.

## Migration constraints

The Helm chart mounts `waylonwalker-com-prod-notes-site-pvc` at `/data/site`
in both the site and Builder Admin Deployments. The former PVC used the
`longhorn` StorageClass. Kubernetes does not permit an in-place change of a
bound PVC's StorageClass. The chart has no value for a different site claim
name. Changing `storage.site.storageClassName` alone cannot migrate a PVC.

The cutover on 2026-09-28 copied the site into the two-replica fast volume.
The final sync completed while Builder Admin was stopped. The site claim
`waylonwalker-com-prod-notes-site-pvc` now binds
`pvc-cbc9a896-5733-4892-ab42-be4fd2946a89` (30 GiB,
`longhorn-build-fast`). Both the public site and Builder Admin mount this
claim. The old `pvc-36939c15-7ad2-42d7-a361-f7a9931a56c5` PV remains
retained for rollback. The `site-pre-fast-migration` backup completed before
the cutover; it predates later site writes. The
`site-post-fast-migration` backup of the new PV completed after cutover.
No restore test was run.

The fast class has two replicas, on falcon3's NVMe and falcon2's HDD. The
falcon3 NVMe had about 107 GiB free when measured. Longhorn reported
**insufficient storage** when asked to add another 20 GiB site replica to
that disk while the 30 GiB fast volume was already reserved there.

The chart pins the new PV with `storage.site.volumeName`. The old PV has a
`Retain` reclaim policy. Do not delete the old PV or its Longhorn volume
until the new site has a restore-tested backup and enough healthy build history.
The old PV reflects the state at cutover, not later releases.

### Rollback outline

1. Stop Builder Admin and the site Deployment. Turn off automated sync for
   the child Argo Application before you change the claims.
2. Set the fast PV reclaim policy to `Retain`. Delete the current site PVC,
   but keep both the fast PV and the Longhorn volume.
3. Remove the claim reference from the retained old PV. Create the site PVC
   with `storageClassName: longhorn`, `size: 20Gi`, and `volumeName` set to
   `pvc-36939c15-7ad2-42d7-a361-f7a9931a56c5`.
4. Update `storage.site.storageClassName`, `storage.site.size`, and
   `storage.site.volumeName` together in the Argo Application. Restore
   automated sync, the site, and Builder Admin.
5. Check the `current` symlink and the public site. The old PV does not
   contain releases or authoring history created after the cutover.

Do not use this outline as an automatic rollback script. Confirm the
replica health, backup state, and active claim names before each step.

At the post-cutover check, falcon3's NVMe had about 85 GiB free. Longhorn
reported the fast disk as **not schedulable** under the live 20% minimum-free
setting. Both replicas were healthy, but Longhorn cannot place a replacement
NVMe replica on that disk until space is freed. Keep the old PV and backup
until the NVMe has enough headroom for replica recovery. Do not lower the
minimum-free setting to hide this disk-pressure warning.

At 14:14 UTC on 2026-09-28, Longhorn reported 112.8 GB available on the
falcon3 fast NVMe disk and marked it schedulable again. Its 20% threshold is
99.9 GB, so the margin remained about 13 GB. These values can change with
other workloads; keep the retained PV and completed backup for recovery.

## Longhorn matrix — 2026-09-28

These results are from disposable 2 GiB volumes under live cluster load.
Each write trial used `fio` to write 256 MiB with direct I/O and a final
`fsync`; the tables report both trials in MiB/s. The 4 KiB
`O_SYNC` result is one 10-second test, reported as IOPS. Replica placement
was checked against Longhorn replica disk UUIDs. Results are spot checks,
not guarantees; two trials and changing cluster load leave substantial
uncertainty. The RWX read path can benefit from NFS client/server caching,
so reads that exceed raw disk rates must not be ranked as disk performance.

### Per-disk comparison

Each row is a separate one-replica volume. The write pair lists the two trials.

| Disk placement | Access | Write (MiB/s, trial 1; trial 2) | 4 KiB `O_SYNC` (IOPS) |
| --- | --- | ---: | ---: |
| falcon2 root | RWO | 52.99; 46.41 | 97 |
| falcon2 root | RWX (share-manager on falcon2) | 57.09; 61.69 | 416 |
| falcon2 vault HDD | RWO | 34.77; 34.09 | 73 |
| falcon2 vault HDD | RWX (share-manager on falcon2) | 39.36; 45.82 | 157 |
| falcon3 NVMe | RWO | 77.22; 105.73 | 157 |
| falcon3 NVMe | RWX (share-manager on falcon2) | 28.35; 26.31 | 199 |
| falcon3 wd3tb HDD | RWO | 45.55; 56.37 | 125 |
| falcon3 wd3tb HDD | RWX (share-manager on falcon2) | 23.86; 24.61 | 146 |

### StorageClass comparison

Tests ran from a falcon3 client. Every `longhorn-site` and
`longhorn-cache` volume had its replica on falcon2 vault; their RWX
share-managers also ran on falcon2. The build-fast and backup classes
placed two replicas on falcon2 vault plus the listed falcon3 disk; RWX
share-managers ran on falcon2. Write values list both trials in MiB/s.

| Class / replicas | Access | Write (MiB/s, trial 1; trial 2) | 4 KiB `O_SYNC` (IOPS) |
| --- | --- | ---: | ---: |
| `longhorn-site`, one replica: falcon2 vault | RWO | 41.53; 49.54 | 174 |
| `longhorn-site`, one replica: falcon2 vault | RWX | 22.33; 31.23 | 138 |
| `longhorn-cache`, one replica: falcon2 vault | RWO | 42.37; 47.58 | 190 |
| `longhorn-cache`, one replica: falcon2 vault | RWX | 37.33; 36.56 | 189 |
| `longhorn-build-fast`, two replicas: falcon2 vault + falcon3 NVMe | RWO | 41.53; 43.65 | 185 |
| `longhorn-build-fast`, two replicas: falcon2 vault + falcon3 NVMe | RWX | 27.02; 26.48 | 196 |
| `longhorn-backup`, two replicas: falcon2 vault + falcon3 wd3tb HDD | RWO | 41.60; 47.47 | 141 |
| `longhorn-backup`, two replicas: falcon2 vault + falcon3 wd3tb HDD | RWX | 21.86; 22.75 | 123 |

The three-replica `longhorn`, `longhorn-fast-replicated`, and
`longhorn-static` default classes were **not tested**. Falcon1 is the only
third Longhorn node, but its disk is unschedulable. The live setting
`replica-soft-anti-affinity=false` prevents a healthy three-replica placement
on two nodes. These cases are not zero-performance results.

### Cross-node access to one build-fast volume

RWO access used sequential detach and reattach on the same two-replica
volume (falcon2 vault + falcon3 NVMe). RWX used a separate two-replica
volume; both clients mounted it through a share-manager on falcon2. Write
values list both trials in MiB/s.

| Access pattern / client | Write (MiB/s, trial 1; trial 2) | 4 KiB `O_SYNC` (IOPS) |
| --- | ---: | ---: |
| RWO, falcon3 client | 33.19; 24.94 | 50 |
| RWO, falcon2 client | 48.77; 37.33 | 169 |
| RWX alone, falcon2 client | 31.34; 34.54 | 129 |
| RWX alone, falcon3 client | 26.49; 26.37 | 141 |
| RWX concurrent separate file, falcon2 client | 24.38; 25.42 | 72 |
| RWX concurrent separate file, falcon3 client | 17.44; 20.26 | 153 |

The concurrent fio phases were not barrier-synchronized. Do not add their
IOPS or treat them as a coordinated aggregate. RWX NFS caching can also
make reads appear faster than the backing disk. Do not rank RWX reads or
infer that RWX is superior from apparent IOPS differences.

The fast class pairs falcon3 NVMe with a falcon2 HDD: it offers an NVMe
replica, but writes still depend on the slower replica and network path.
These short tests do not establish a build-speed benefit or a reliable
ranking; placement, contention, caching, and trial variability all matter.
Temporary disk tags, classes, volumes, and the test namespace were removed.
The production PVC was never mounted by these tests.
