# Production Builder Admin storage measurements

These measurements were taken on 2026-09-27/28 in the live cluster. They are
spot checks, not sustained throughput guarantees. The workload creates many
small files, so sequential throughput alone cannot predict build time.

| Node and path | Filesystem | 256 MiB direct sequential write | Notes |
| --- | --- | ---: | --- |
| falcon3 root (`/dev/nvme0n1p4`) | XFS on NVMe | ~1,300 MB/s | Local host path, 107 GiB free at test time. |
| falcon2 root (`/var/lib/longhorn`) | ext4 on LVM | ~341 MB/s | 85% full at test time. |
| falcon1 root (`/var/lib/longhorn`) | XFS on SSD | ~167 MB/s | ~80% full at test time. |
| falcon1 local host path (`/mnt/vault`) | XFS on SSD | ~225 MB/s | Same device as the root filesystem. |
| falcon2 `/mnt/vault` | ext4 on IronWolf HDD | ~140 MB/s | Different local disk on each node. |
| falcon3 Longhorn `wd3tb` (`/var/lib/longhorn/disks/wd3tb`) | ext4 on HDD | ~33 MB/s | The slow replica disk. |

The tests wrote 256 MiB with BusyBox `dd bs=1M count=256 oflag=direct` to
temporary files. The test removed each file afterward. Tests ran at different
times, so load and cache effects can change the results. A separate 512 MiB
direct write to falcon3's `/mnt/main` ZFS pool reported ~4,300 MB/s. This
result can include ZFS cache effects. Longhorn v1 could **not** run a replica
there: replica rebuild failed with `file extent is unsupported: operation not
supported`. Do not tag this ZFS path for Longhorn v1 replicas.

The `longhorn-build-fast` class selects two tagged disks: falcon3 NVMe at
`/var/lib/longhorn/fast-nvme`, and falcon2 HDD at `/mnt/vault/longhorn`.
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
