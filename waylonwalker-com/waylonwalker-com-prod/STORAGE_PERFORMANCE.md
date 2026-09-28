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
The PR is draft and is not part of the production `main` image. A rollout
needs both its new image and its opt-in Helm workspace settings.

## Migration constraints

The Helm chart mounts `waylonwalker-com-prod-notes-site-pvc` at `/data/site`
in both the site and Builder Admin Deployments. This existing PVC uses the
`longhorn` StorageClass. Kubernetes does not permit an in-place change of a
bound PVC's StorageClass. The chart has no value for a different site claim
name. Changing `storage.site.storageClassName` alone does not migrate the PVC.

The `site-pvc-fast-staging` PVC uses `longhorn-build-fast`, but it is **not**
the live site or build volume until a completed copy and a cutover. The old
site PVC and its releases remain the source of truth until that point. The
`site-pre-fast-migration` Longhorn snapshot and backup completed before the
cutover. That backup predates later site writes.

The fast class has two replicas, on falcon3's NVMe and falcon2's HDD. The
falcon3 NVMe had about 107 GiB free when measured. A 30 GiB staging volume
also reserves space on that disk. Longhorn reported **insufficient storage**
when asked to move the old 20 GiB site replica there. Do not remove a healthy
site replica until Longhorn confirms capacity and a completed backup.

The cutover needs a complete copy, a write freeze, a final copy, and a new
claim bound to the staging volume. The Helm chart always uses the claim name
`waylonwalker-com-prod-notes-site-pvc`. Keep the old Longhorn PV with the
`Retain` reclaim policy before deleting its PVC. Rebind the fast staging PV
to a new claim with the chart's name. Set the chart's site StorageClass and
size to match the new PVC. This operation interrupts the public site while
both workloads release the old volume. Do not change the site's StorageClass
value in Argo without completing this migration.
