# Kubernetes storage inventory
> Historical snapshot from September 2026. Figures and pending actions describe that date.
> See [the recovery review](cleanup-recovery-2026-10-02.md) for later evidence.
> Recheck live state before using this document for an operation.

This document records a read-only storage snapshot from the `default` Kubernetes
context. The storage snapshot was collected on 2026-09-20 between 16:23Z and 16:46Z.
The hardware and performance measurements below were collected through 16:53Z.

The report uses decimal byte values unless a tool reports another unit. Longhorn
status and node filesystem status are both shown because they do not match on
all disks.

## Executive summary

- The cluster has three `Ready` nodes running K3s `v1.36.4+k3s1`.
- `falcon1` uses a 238.5G SSD for the OS and Longhorn.
- `falcon2` uses a 931.5G SSD for the OS and Longhorn, plus a 3.6T HDD at `/mnt/vault`.
- `falcon3` uses a 465.8G NVMe device for the OS, a 2.7T disk for Longhorn, and two ZFS mirrors.
- Kubernetes reports `DiskPressure=False` on every node.
- Longhorn marks `falcon1` and `falcon2/vault` as unschedulable because of `DiskPressure`.
- The `falcon2` default disk changed from unschedulable to schedulable during collection.
- The physical free space on `falcon2:/mnt/vault` is about 11.8G, but Longhorn reports about 210.7G.
- Longhorn has 65 bound PVCs and 9 released volume/PV objects.
- Longhorn reported 41 degraded and 17 unknown volumes in the final query.
- The Longhorn S3 backup target is unavailable because of `SignatureDoesNotMatch`.
- `falcon3` had a 1-minute load of `91.2` on four CPUs during the performance snapshot.
- `falcon1` spent about `37.7%` of CPU time in I/O wait during the same five-minute window.

## Hardware and performance

### CPU and memory hardware

| Node | CPU make and model | Topology and frequency | Kubernetes CPU | Memory |
| --- | --- | --- | ---: | ---: |
| `falcon1` | Intel Core i7-2600 @ 3.40GHz | 1 socket, 4 cores, 1 thread per core; 4 online and 4 offline CPUs; 1.6–3.8GHz | 4 | 16.7GB / 15.6GiB |
| `falcon2` | Intel Core i5-7500 @ 3.40GHz | 1 socket, 4 cores, 1 thread per core; 0.8–3.8GHz | 4 | 67.2GB / 62.5GiB |
| `falcon3` | AMD Ryzen 3 3200G with Radeon Vega Graphics | 1 socket, 4 cores, 1 thread per core; 1.4–3.6GHz; boost enabled | 4 | 65.2GB / 60.7GiB |

`falcon1` reports eight configured CPU IDs, but only four are online. Kubernetes
therefore advertises four CPUs on each node. All nodes report one NUMA node.

### GPU hardware and Kubernetes resources

| Node | GPU | Driver | Device/resource exposure | Observed consumers |
| --- | --- | --- | --- | --- |
| `falcon1` | AMD/ATI Juniper PRO, Radeon HD 5750, PCI `01:00.0` | `radeon` | `/dev/dri/card0`, `/dev/dri/renderD128`; no Kubernetes GPU resource | No application consumer identified |
| `falcon2` | Intel HD Graphics 630, PCI `00:02.0` | `i915` | `/dev/dri/card0`, `/dev/dri/renderD128`; `gpu.intel.com/i915=1` | `frigate` uses `/dev/dri` and `/dev/apex_0` |
| `falcon3` | AMD/ATI Picasso/Raven 2 Radeon Vega, PCI `06:00.0` | `amdgpu` | `/dev/dri/card0`, `/dev/dri/renderD128`; no Kubernetes GPU resource | `jellyfin` uses `/dev/dri` |

The Intel GPU plugin runs on all three nodes, but only `falcon2` advertises an
Intel GPU resource. Prometheus has no GPU utilization or GPU memory metrics.

### Performance snapshot

The `kubectl top` values are point-in-time metrics. The load, CPU, memory, and
I/O values use Prometheus five-minute rates from approximately 16:53Z.

| Node | `kubectl top` CPU | `kubectl top` memory | CPU busy | Load 1 / 5 / 15 | I/O wait | Memory available | Disk read / write | Network RX / TX |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `falcon1` | 1.37 cores / 34% | 9,316Mi / 58% | 67.2% | 7.88 / 5.02 / 7.80 | 37.7% | 9.1GB / 54.3% | 1.77 / 1.50 MB/s | 9.08 / 9.90 MB/s |
| `falcon2` | 2.81 cores / 70% | 18,688Mi / 29% | 89.8% | 10.47 / 9.82 / 10.91 | 15.6% | 51.3GB / 76.4% | 13.19 / 20.48 MB/s | 38.18 / 43.18 MB/s |
| `falcon3` | 3.13 cores / 78% | 33,772Mi / 54% | 100.0% | 91.2 / 66.3 / 47.99 | 18.0% | 15.0GB / 22.8% | 29.53 / 15.67 MB/s | 38.02 / 41.00 MB/s |

The disk rates include physical block devices selected from `sda` through `sde`
and `nvme0n1`. The network rates include all non-loopback interfaces.

Reported hardware temperatures were approximately `39–46°C` on `falcon1`,
`27.8–57°C` on `falcon2`, and `39.85–64.75°C` on `falcon3`. Sensor labels are
host-specific, so these values need sensor mapping before alert thresholds are
created.

The current metrics show a performance risk on `falcon3` and high I/O wait on
`falcon1`. Container CPU metrics do not explain the complete `falcon3` load, so
process and I/O follow-up is still required.

### Metrics to retain for future inventories

- CPU model, socket count, core count, thread count, online CPU count, and frequency limits from `lscpu`.
- GPU PCI identity, driver, `/dev/dri` devices, and Kubernetes extended resources from `lspci` and node status.
- Point-in-time CPU and memory use from `kubectl top nodes`.
- Five-minute CPU busy, CPU I/O wait, load averages, memory availability, disk I/O, network I/O, and temperature from Prometheus.
- GPU utilization, GPU memory, and encoder use after a GPU exporter is installed.

## Node and physical disk inventory

### `falcon1` — `192.168.1.106`

| Device | Model and serial | Size | Filesystem or role | Consumers |
| --- | --- | ---: | --- | --- |
| `/dev/sda` | `SSD 256GB`, `AA000000000000000049` | 238.5G | XFS at `/var` | OS, K3s, container storage, Longhorn `default-disk-080400000000` at `/var/lib/longhorn/` |
| `/dev/sdb` | `Compact Flash`, `20060413092100000` | 0B | Card-reader slot | No mounted filesystem observed |
| `/dev/sdc` | `xD-Picture`, `20060413092100000` | 0B | Card-reader slot | No mounted filesystem observed |
| `/dev/sdd` | `SD/MMC`, `20060413092100000` | 0B | Card-reader slot | No mounted filesystem observed |
| `/dev/sde` | `MS/MS-Pro/HG`, `20060413092100000` | 0B | Card-reader slot | No mounted filesystem observed |
| `/dev/sdf` | `MicroSD`, `20060413092100000` | 0B | Card-reader slot | No mounted filesystem observed |

The Longhorn disk has a maximum of `255397806080` bytes, `62075699200` bytes
available, and `236537774080` bytes scheduled. Longhorn requires at least
`63849451520` bytes available, so it reports `DiskPressure`.

### `falcon2` — `192.168.1.168`

| Device | Model and serial | Size | Filesystem or role | Consumers |
| --- | --- | ---: | --- | --- |
| `/dev/sda` | `CT1000MX500SSD1`, `2410E89DE9D3` | 931.5G | LVM ext4 root filesystem | OS, K3s local-path PVCs, Longhorn `default-disk-79edc7203d5c151e` at `/var/lib/longhorn/` |
| `/dev/sdb` | `ST4000VN008-2DR1`, `ZDH9C72V` | 3.6T | ext4 at `/mnt/vault` | Longhorn `vault` at `/mnt/vault/longhorn`; hostPath PVs and direct Frigate, MinIO, site-build, and cache data |
| `/dev/loop9` | loop-backed Frigate cache | 200G | ext4 at `/var/lib/frigate-cache` | `frigate/frigate-temp-ssd` |

The Longhorn default disk reports a maximum of `980666998784` bytes,
`425721856000` bytes available, and `615358922752` bytes scheduled in the final
query. The node filesystem reports about `187.4G` available on `/`.

The Longhorn `vault` disk has a maximum of `3936789286912` bytes and reports
`210658918400` bytes available. It has no scheduled replicas and has
`allowScheduling=false`. The node filesystem reports about `11.8G` available
on `/mnt/vault`. Do not enable scheduling on this disk until this difference is
explained.

### `falcon3` — `192.168.1.234`

| Device | Model and serial | Size | Filesystem or role | Consumers |
| --- | --- | ---: | --- | --- |
| `/dev/nvme0n1` | `CT500P5PSSD8`, `213231369F6A` | 465.8G | XFS root filesystem | OS, K3s, direct hostPath data under `/var` |
| `/dev/sda` | `ST4000VN008-2DR1`, `ZDHBZV3N` | 3.6T | ZFS member `/dev/sda1` | `tank` mirror |
| `/dev/sdb` | `ST4000VN008-2DR1`, `ZDHBZSWZ` | 3.6T | ZFS member `/dev/sdb1` | `tank` mirror |
| `/dev/sdc` | `ST14000NM005G-2K`, `ZTM09R9N` | 12.7T | ZFS member `/dev/sdc1` | `main` mirror |
| `/dev/sdd` | `ST14000NM005G-2K`, `ZTM0AALS` | 12.7T | ZFS member `/dev/sdd1` | `main` mirror |
| `/dev/sde` | `WDC WD30EFRX-68E`, `WD-WMC4N0D3J9R7` | 2.7T | ext4 at `/var/lib/longhorn/disks/wd3tb` | Longhorn disk `wd3tb` / status name `wd-3tb` |

The Longhorn disk reports a maximum of `2952326160384` bytes,
`2416128819200` bytes available, and `1101973684224` bytes scheduled. The node
filesystem reports about `2.27T` available.

### ZFS pools on `falcon3`

| Pool | Vdev | Size | Allocated | Free | Health | Main consumers |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `main` | Mirror of `/dev/sdc1` and `/dev/sdd1` | 13.984T | 5.067T | 8.918T | `ONLINE` | `/mnt/main`, static sites, walkershare, Jellyfin media, Nextcloud paths, backup MinIO |
| `tank` | Mirror of `/dev/sda1` and `/dev/sdb1` | 3.986T | 2.188T | 1.798T | `ONLINE` | `/mnt/tank`, 3D, Git, Jellyfin, ROMs, Steam, VM, and other personal data |

ZFS datasets include `main/longhorn-backup`, `main/media`,
`main/nextcloud`, `main/walkershare`, `tank/3d`, `tank/git`,
`tank/jellyfin`, `tank/roms`, `tank/steam`, `tank/vm`, and
`tank/waylonwalker-gaming`.

Both pools report zero read, write, and checksum errors. The last recorded scrub
completed on 2025-04-15 with zero repaired bytes.

## Longhorn inventory

Longhorn uses the following disk UUIDs for replicas:

| Node | Disk name | Disk UUID | Path | Scheduling | Reserved | Maximum | Available | Scheduled |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| `falcon1` | `default-disk-080400000000` | `22cfc49b-fd6f-49ea-be75-c2ba299110b5` | `/var/lib/longhorn/` | No, `DiskPressure` | 0 | 255397806080 | 62075699200 | 236537774080 |
| `falcon2` | `default-disk-79edc7203d5c151e` | `812a359d-a109-47c1-910e-316970149448` | `/var/lib/longhorn/` | Yes in final query; changed during collection | 322122547200 | 980666998784 | 425721856000 | 615358922752 |
| `falcon2` | `vault` | `f76db599-6536-45ab-beee-ba36e7bb4726` | `/mnt/vault/longhorn` | No, disabled and `DiskPressure` | 1099511627776 | 3936789286912 | 210658918400 | 0 |
| `falcon3` | `wd3tb` | `ccc831a4-295c-476e-8a7e-aaee5f6a219c` | `/var/lib/longhorn/disks/wd3tb` | Yes | 536870912000 | 2952326160384 | 2416128819200 | 1101973684224 |

The cluster has 74 Longhorn Volume objects:

- 65 are bound to current PVCs.
- 9 are released from their PVCs: `terraria-data`, `kraft-data-backup`,
  `funk-season2-data`, `rhiannonwalker-config-longhorn`, three historical
  `funk-data-backup` volumes, `dungeon-data-backup`, and `kraft-season2-data`.
- 178 Replica objects exist, including one unassigned replica for
  `observability/prometheus-observability-kube-prometh-prometheus-db-prometheus-observability-kube-prometh-prometheus-0`.
- 106 replicas report `running`; 72 report `stopped`.
- Replica placement is 25 on `falcon1`, 55 on `falcon2`, and 97 on `falcon3`.
- No replica is scheduled on the `falcon2/vault` disk.

The final query reports 41 volumes as `degraded`, 16 as `healthy`, and 17 as
`unknown`. These counts changed during collection as Longhorn replica states
changed. Most degraded volumes report `ReplicaSchedulingFailure` with `disks
are unavailable`. This indicates a scheduling problem, not proof of data loss.

Examples of affected current PVCs include:

- `minio/minio-storage-longhorn` — 50Gi, two replicas, degraded.
- `observability/prometheus-observability-kube-prometh-prometheus-db-prometheus-observability-kube-prometh-prometheus-0` — 50Gi, three replicas, degraded, with one unassigned replica.
- `waylonwalker-com/site-pvc-longhorn-fast` — 5Gi, three replicas, degraded.
- `rhiannonwalker-com-prod-notes/rhiannonwalker-com-prod-notes-search-pvc` — 5Gi, three replicas, detached, unknown, and without a last backup.

### Bound Longhorn PVCs by namespace

| Namespace | StorageClass and count |
| --- | --- |
| `aylawalker` | `longhorn-backup` × 1 |
| `dev-waylonwalker-com` | `longhorn-backup` × 1; `longhorn-fast-replicated` × 1 |
| `diun` | `longhorn-backup` × 1 |
| `dropper` | `longhorn-backup` × 2 |
| `dropper-dev` | `longhorn-backup` × 2 |
| `forgejo` | `longhorn` × 1; `longhorn-backup` × 2 |
| `go-waylonwalker-com-notes` | `longhorn` × 1 |
| `hlab-auth` | `longhorn` × 1 |
| `hyzar-wyattbubbylee-com` | `longhorn` × 1 |
| `magnet-smp` | `longhorn-backup` × 2 |
| `markata-go-docs` | `longhorn-fast-replicated` × 1 |
| `minio` | `longhorn-backup` × 1 |
| `models` | `longhorn-fast-replicated` × 3 |
| `models-dev` | `longhorn-fast-replicated` × 3 |
| `notify-bridge` | `longhorn-backup` × 1 |
| `observability` | `longhorn` × 5 |
| `omada` | `longhorn-backup` × 2 |
| `performpeoria-dev` | `longhorn-backup` × 3 |
| `performpeoria-prod` | `longhorn-backup` × 5 |
| `posse-party` | `longhorn-backup` × 1 |
| `postiz` | `longhorn` × 1; `longhorn-backup` × 3 |
| `rhiannonwalker-com-prod-notes` | `longhorn` × 4 |
| `thoughts` | `longhorn-backup` × 1 |
| `tigerfs-cnpg` | `longhorn` × 1 |
| `walkershare` | `longhorn` × 2 |
| `waylonwalker-com` | `longhorn` × 2; `longhorn-fast-replicated` × 1 |
| `waylonwalker-com-prod-notes` | `longhorn` × 4 |
| `wyattbubbylee-com-prod-notes` | `longhorn` × 4 |
| `zigbee2mqtt` | `longhorn` × 1 |

## Other Kubernetes storage

There are 114 bound PVCs in total:

| Backend | Bound PVCs | Main location or role |
| --- | ---: | --- |
| Longhorn | 65 | Longhorn disks listed above |
| `local-path` | 7 | `falcon2` root filesystem at `/var/lib/rancher/k3s/storage` |
| `hostpath` | 8 | Mostly `/mnt/vault/nfs/general/...` and direct node paths |
| `manual` | 4 | `/mnt/main/media/...` for Jellyfin |
| `walkershare` | 1 | `/mnt/main/walkershare` |
| No StorageClass | 29 | Static-site, model, MinIO, and other hostPath PVs |

Important non-Longhorn consumers include:

- `minio-longhorn-backup/minio-storage-longhorn-backup` uses the hostPath
  `/mnt/main/minio-longhorn-backup` on `falcon3`. The application name does not
  mean that this PVC uses Longhorn.
- Static-site PVs use `/mnt/main/walkershare/waylon/sites/...`.
- Models use `/mnt/main/walkershare/waylon/3d` and
  `/mnt/main/walkershare/waylon/3d-dev`.
- Jellyfin uses `/mnt/main/media/cache`, `/mnt/main/media/config`,
  `/mnt/main/media/media`, and `/mnt/main/media/transcoded`.
- Photoprism uses `/mnt/main/nextcloud/photoprism/storage`.
- Several `falcon2` workloads use `/mnt/vault/nfs/general/...`, including the
  MinIO, Frigate, site-build, reader-cache, and shot-cache paths.
- Several site applications mount `/mnt/main/walkershare/waylon/vaults/...`,
  `/mnt/main/walkershare/waylon/cache/...`, and site paths directly.

The live default StorageClass is `local-path`. Longhorn classes use these
policies:

| StorageClass | Replicas | Reclaim policy | Recurring jobs |
| --- | ---: | --- | --- |
| `longhorn` | 3 | Delete | None |
| `longhorn-backup` | 2 | Retain | `snapshot-hourly`, `backup-daily`, `backup-weekly` |
| `longhorn-cache` | 1 | Delete | None |
| `longhorn-fast-replicated` | 3 | Retain | None |
| `longhorn-site` | 1 | Retain | None |
| `longhorn-static` | Not set | Delete | None |

## Backup inventory

The Longhorn default backup target is `s3://longhorn-system@us-east-1/`. It uses
the credential Secret `longhorn-system/minio-longhorn-backup-secret`.

The target is currently unavailable. The last condition at 16:41Z reports:

```text
AWS Error: SignatureDoesNotMatch The request signature we calculated does not match the signature you provided. Check your key and signing method.
```

Observed backup objects:

- 926 Backup objects: 914 completed, 3 failed, and 9 without a completed state.
- 114 BackupVolume objects exist.
- Of the 65 bound Longhorn volumes, one has no last backup:
  `rhiannonwalker-com-prod-notes/rhiannonwalker-com-prod-notes-search-pvc`.
- 8 other bound volumes have a last backup from 2026-08-23.
- Three orphan BackupVolume objects have no last backup:
  `pvc-2633fa0e-ea77-4b9a-a0fc-ee8c9f8503df-3f7000de`,
  `pvc-51cca088-777c-40cc-a938-d201721d338b-2dac6070`, and
  `pvc-62637836-d3f2-404c-ac8c-6d6b22123cc2-c7a9d12b`.
- The three failed backups report lock-acquisition errors for
  `minio/minio-storage-longhorn`, `forgejo/forgejo-data-v2`, and
  `dropper/dropper-data`.
- The daily, weekly, and media backup jobs succeeded on 2026-09-20 before the
  target became unavailable. `backup-daily-retry-20260916` failed four times.

Longhorn backup objects do not provide backup coverage evidence for the
49 bound non-Longhorn PVCs or for direct hostPath mounts.

## Current usage update — 2026-09-20T18:02Z

This section is newer than the original 16:23Z–16:46Z inventory. Longhorn
replica repair changed the health counts during the day. The values below are
the current usage values collected at 18:02Z.

### Longhorn totals and disk usage

The 65 bound Longhorn volumes request `677GiB` in total. Their reported
logical `actualSize` totals `393GiB`. Longhorn `actualSize` is not the total
physical size of all replicas. Use `storageScheduled` for the replica
allocation on each Longhorn disk.

| Node and disk | Maximum | Scheduled | Scheduled | Available | Available | Current consumers |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `falcon1/default-disk-080400000000` | 255.4GB | 236.5GB | 92.6% | 61.1GB | 23.9% | Longhorn replicas on the Fedora CoreOS root disk |
| `falcon2/default-disk-79edc7203d5c151e` | 980.7GB | 615.4GB | 62.7% | 304.4GB | 31.0% | Longhorn replicas and the OS root filesystem |
| `falcon2/vault` | 3.9TB | 0B | 0% | 208.9GB | 5.3% | No Longhorn replicas; hostPath data uses the same disk |
| `falcon3/wd3tb` | 3.0TB | 994.6GB | 33.7% | 2.5TB | 86.2% | Longhorn replicas on the WDC disk |

The node filesystem reports only `8.7GB` available on `falcon2:/mnt/vault`, not
the `208.9GB` reported by Longhorn. Treat the Longhorn value as unreliable until
the accounting difference is explained.

### Longhorn usage by application

This table lists the largest current Longhorn volumes by reported logical
usage. The workload column comes from Longhorn Kubernetes workload status.

| Namespace | PVC | Workload | Replica nodes | Requested | Actual | Replicas | Health | State |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| `observability` | `prometheus-observability-kube-prometh-prometheus-db-prometheus-observability-kube-prometh-prometheus-0` | `prometheus-observability-kube-prometh-prometheus` | `falcon2`, `falcon1`, unassigned | 50GiB | 113GiB | 3 | Degraded | Attached |
| `minio` | `minio-storage-longhorn` | `minio2-6f8ffc875` | `falcon3`, `falcon2` | 50GiB | 57GiB | 2 | Degraded | Attached |
| `forgejo` | `forgejo-data-v2` | `forgejo-78c4876579` | `falcon3`, `falcon3` | 50GiB | 42GiB | 2 | Healthy | Attached |
| `dropper` | `dropper-data` | `dropper-wayl-one-5fcfdbcf74` | `falcon3`, `falcon2` | 50GiB | 33GiB | 2 | Healthy | Attached |
| `waylonwalker-com-prod-notes` | `waylonwalker-com-prod-notes-site-pvc` | Builder and site pods | `falcon3`, `falcon2`, unassigned | 20GiB | 32GiB | 3 | Degraded | Attached |
| `wyattbubbylee-com-prod-notes` | `wyattbubbylee-com-prod-notes-site-pvc` | Builder and site pods | `falcon3`, `falcon2`, unassigned | 10GiB | 28GiB | 3 | Degraded | Attached |
| `waylonwalker-com-prod-notes` | `waylonwalker-com-prod-notes-cache-pvc` | Builder admin | `falcon3` | 10GiB | 8GiB | 3 | Unknown | Detached |
| `posse-party` | `posse-party-db-1` | `posse-party-db` | `falcon2`, `falcon3` | 5GiB | 8GiB | 2 | Healthy | Attached |
| `forgejo` | `forgejo-db-1` | `forgejo-db` | `falcon2`, `falcon3` | 10GiB | 7GiB | 2 | Healthy | Attached |
| `dev-waylonwalker-com` | `dev-waylonwalker-com-site` | Site and cronjob pods | `falcon2`, `falcon3` | 5GiB | 5GiB | 2 | Healthy | Attached |
| `rhiannonwalker-com-prod-notes` | `rhiannonwalker-com-prod-notes-site-pvc` | Builder and site pods | `falcon2`, `falcon1`, `falcon3` | 10GiB | 4GiB | 3 | Healthy | Attached |
| `magnet-smp` | `magnet-smp-season2-data` | `magnet-smp-85cc4fcfc7` | `falcon3`, `falcon3` | 10GiB | 4GiB | 2 | Healthy | Attached |

Four bound volumes were degraded, 52 were healthy, and 9 were unknown at the
time of this update. The largest current logical consumers are Prometheus,
backup MinIO, Forgejo, Dropper, and the production site volumes.

Repeated node names mean that both replicas currently reside on the same node.
This reduces protection from a node failure even when the volume is healthy.

### Longhorn usage by namespace

`Actual` is the sum of Longhorn `status.actualSize` for the namespace. It is a
logical usage value and does not include the physical multiplier from replicas.

| Namespace | Volumes | Requested | Actual | Health counts |
| --- | ---: | ---: | ---: | --- |
| `aylawalker` | 1 | 10GiB | 0GiB | healthy=1 |
| `dev-waylonwalker-com` | 2 | 10GiB | 6GiB | healthy=1, unknown=1 |
| `diun` | 1 | 1GiB | 0GiB | healthy=1 |
| `dropper` | 2 | 60GiB | 35GiB | healthy=2 |
| `dropper-dev` | 2 | 10GiB | 7GiB | healthy=2 |
| `forgejo` | 3 | 65GiB | 53GiB | healthy=3 |
| `go-waylonwalker-com-notes` | 1 | 10GiB | 0GiB | unknown=1 |
| `hlab-auth` | 1 | 8GiB | 2GiB | healthy=1 |
| `hyzar-wyattbubbylee-com` | 1 | 5GiB | 0GiB | healthy=1 |
| `magnet-smp` | 2 | 20GiB | 4GiB | healthy=1, unknown=1 |
| `markata-go-docs` | 1 | 5GiB | 0GiB | unknown=1 |
| `minio` | 1 | 50GiB | 57GiB | degraded=1 |
| `models` | 3 | 15GiB | 7GiB | healthy=3 |
| `models-dev` | 3 | 15GiB | 1GiB | healthy=3 |
| `notify-bridge` | 1 | 5GiB | 0GiB | healthy=1 |
| `observability` | 5 | 120GiB | 118GiB | degraded=1, healthy=4 |
| `omada` | 2 | 3GiB | 5GiB | healthy=2 |
| `performpeoria-dev` | 3 | 40GiB | 2GiB | healthy=3 |
| `performpeoria-prod` | 5 | 70GiB | 4GiB | healthy=5 |
| `posse-party` | 1 | 5GiB | 7GiB | healthy=1 |
| `postiz` | 4 | 10GiB | 1GiB | healthy=4 |
| `rhiannonwalker-com-prod-notes` | 4 | 35GiB | 5GiB | healthy=3, unknown=1 |
| `thoughts` | 1 | 10GiB | 0GiB | healthy=1 |
| `tigerfs-cnpg` | 1 | 1GiB | 1GiB | healthy=1 |
| `walkershare` | 2 | 2GiB | 0GiB | healthy=2 |
| `waylonwalker-com` | 3 | 10GiB | 3GiB | healthy=3 |
| `waylonwalker-com-prod-notes` | 4 | 45GiB | 43GiB | degraded=1, healthy=1, unknown=2 |
| `wyattbubbylee-com-prod-notes` | 4 | 35GiB | 29GiB | degraded=1, healthy=1, unknown=2 |
| `zigbee2mqtt` | 1 | 1GiB | 0GiB | healthy=1 |

### Filesystem usage for storage roots

These values come from node-exporter filesystem metrics. The `used` column is
the size minus available space.

| Node | Mount | Total | Available | Used | Main consumers |
| --- | --- | ---: | ---: | ---: | --- |
| `falcon1` | `/var` | 255.4GB | 61.2GB | 194.2GB / 76.0% | OS, K3s, container storage, Longhorn |
| `falcon2` | `/` | 980.7GB | 261.2GB | 719.5GB / 73.4% | OS, K3s local-path PVCs, Longhorn |
| `falcon2` | `/mnt/vault` | 3.9TB | 8.7GB | 3.9TB / 99.8% | HostPath data and disabled Longhorn disk |
| `falcon3` | `/var` | 499.3GB | 112.4GB | 386.9GB / 77.5% | OS and K3s |
| `falcon3` | `/var/lib/longhorn/disks/wd3tb` | 3.0TB | 2.4TB | 556.7GB / 18.9% | Longhorn |

### ZFS dataset usage

The pool values are current. Child dataset usage ties filesystem usage to the
paths used by applications. The available value belongs to the pool because
these datasets do not have separate quotas.

| Pool or dataset | Used | Pool available | Application or path |
| --- | ---: | ---: | --- |
| `main` | 5.112TB | 8.918TB | Parent for `/mnt/main` and unlisted child paths |
| `main/google-takeout` | 457.4GB | 8.918TB | Google Takeout data |
| `main/longhorn-backup` | 98KiB | 8.918TB | Separate dataset; not the MinIO hostPath |
| `main/media` | 2.586TB | 8.918TB | Jellyfin media and media PVs |
| `main/nextcloud` | 224.4GB | 8.918TB | Nextcloud and Photoprism paths |
| `main/sync` | 98KiB | 8.918TB | Sync data |
| `main/walkershare` | 1.290TB | 8.918TB | Walkershare, static sites, and model paths |
| `tank` | 2.188TB | 1.798TB | Parent for `/mnt/tank` |
| `tank/3d` | 3.9GB | 1.798TB | 3D data |
| `tank/brushes` | 2.7GB | 1.798TB | Brush library |
| `tank/git` | 95.3GB | 1.798TB | Git data |
| `tank/jellyfin` | 180.2GB | 1.798TB | Jellyfin-related data outside the PV paths |
| `tank/rhiannon-spectre` | 887.4GB | 1.798TB | Rhiannon Spectre data |
| `tank/roms` | 4.5GB | 1.798TB | ROM data |
| `tank/steam` | 927.2GB | 1.798TB | Steam data |
| `tank/tax` | 8.8MB | 1.798TB | Tax data |
| `tank/vm` | 78.7GB | 1.798TB | Virtual machine data |
| `tank/waylonwalker-gaming` | 6.8GB | 1.798TB | Gaming data |
| `tank/work` | 473.1MB | 1.798TB | Work data |

The backup MinIO PVC uses `/mnt/main/minio-longhorn-backup`, which is under the
`main` parent dataset. It does not use the nearly empty `main/longhorn-backup`
child dataset.

Kubernetes does not report used bytes for hostPath PVCs or direct hostPath
mounts. Use the filesystem and ZFS rows above for those applications, or run a
targeted directory usage scan before making cleanup decisions.

## Recommended order of work

1. Correct the S3 signature failure. Compare the live MinIO endpoint, bucket,
   region, and credential Secret without printing secret values.
2. Run a small test backup and confirm that Longhorn can list the backup store.
3. Reconcile Longhorn disk status with node filesystem status, starting with
   `falcon2:/mnt/vault` and `falcon1:/var/lib/longhorn`.
4. Do not enable the `falcon2/vault` disk until its free-space discrepancy is
   understood.
5. After backup access works, repair or rebalance degraded volumes.
6. Review the 9 released Longhorn volumes and the non-Longhorn data roots for
   retention, backup, and cleanup decisions.
7. Add a repeatable inventory command that records node devices, Longhorn disk
   status, PVC consumers, and backup age.

Do not delete released volumes, remove snapshots, rotate credentials, or change
replica counts as part of this inventory.

## Repository declarations used

- `argo-apps/core-apps/longhorn.yaml`
- `argo-apps/core-apps/minio-longhorn-backup.yaml`
- `k8s/minio-longhorn-backup/deployment.yaml`
- `k8s/minio-longhorn-backup/storageclass.yaml`
- `k8s/minio-longhorn-backup/RecurringJob.yaml`
- `waylonwalker-com/waylonwalker-com.yaml`
- `terraria/deployment.yaml`
- `terraria-challenge/deployment.yaml`

The live cluster and repository are not fully aligned. In particular,
`k8s/minio-longhorn-backup/backup-target.yaml` is deleted in the current
worktree, while the live Longhorn backup target still exists. The worktree also
contains unrelated pre-existing modifications and untracked files.
