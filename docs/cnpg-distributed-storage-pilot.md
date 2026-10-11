# CNPG distributed storage pilot — no hardware changes

**Status:** proposal / test artifact only. No production volume, PostgreSQL Cluster,
ZFS mount, Longhorn global setting, or Argo source is changed by this branch.

## Why not move every PVC to Falcon3 ZFS?

The ZFS `main` mirror is excellent for bulk storage, but access mode matters:

- `hostPath`/node-local PV: the workload must run on Falcon3 (or another
  node with an equivalent local path and explicit affinity), concentrating
  compute on Falcon3. A path string alone does not replicate storage.
- NFS exported from Falcon3: compute pods can run on Falcon1/Falcon2, but reads
  and writes still terminate at Falcon3. NFS adds network latency and a single
  serving host; it is fine for bulk files, not the default for PostgreSQL WAL.
- Longhorn per-node volumes: workloads can run on all three hosts and keep
  active database I/O local. CNPG replicates the database between nodes.
  ZFS `main` remains the bulk-data tier; `tank` is intended as a *local*
  backup tier after capacity checks and restore tests, not host disaster recovery.

## Current state to preserve

- `k8s/models/cnpg.yaml`: three instances, 40Gi, `longhorn-fast-replicated`
  (three storage replicas per DB PVC).
- `k8s/models-dev/cnpg.yaml`: three instances, 5Gi, the same existing class.
- `longhorn-fast-replicated` is declared in
  `k8s/waylonwalker-com/waylonwalker-com.yaml`; do not edit its immutable
  provisioning policy to affect bound PVCs.
- StorageClass changes do not rewrite existing Longhorn Volume specs or move
  existing replicas. Inspect each bound volume's `spec.dataLocality` and
  replica node IDs directly.
- Prior 2026-10-10 recovery left `models-db` with an interrupted db2 restart,
  an earlier divergent db1 timeline, and storage pressure. **Verify all of
  these from live state** before any storage reduction.
- Argo manages live apps with self-heal/prune; a YAML edit to an existing
  database spec is not a safe migration.

## Candidate architecture

Three CNPG PostgreSQL pods, one per healthy Kubernetes node, enforced through
CNPG pod anti-affinity, each using **one** Longhorn replica for its PVC and
preferring a local replica through best-effort data locality.
The PostgreSQL instances provide cross-node replication (3 DB copies instead
of 3 DB copies × 3 Longhorn copies). This is an *application-level* availability
model, not a storage-level HA model. A node failure can destroy its individual
single-replica volume; CNPG needs a healthy surviving standby, capacity to
bootstrap a replacement, and tested logical/physical backups.

`docs/examples/longhorn-cnpg-local-pilot.yaml` defines an **unmanaged,
opt-in, not-yet-applied** `longhorn-cnpg-local` StorageClass. It is intentionally
outside all Argo source paths and is not the default class. The class has
`numberOfReplicas: "1"`, `dataLocality: best-effort`, `Retain`,
`WaitForFirstConsumer`, and no implicit Longhorn recurring jobs.

Best-effort locality prefers to keep the replica on the pod's node while
allowing the volume to attach elsewhere after a move. CNPG pod anti-affinity
provides the three-node placement rule. The pilot must confirm that each
single replica is local after bootstrap and normal restarts. Do not use
`strict-local` on the installed Longhorn v1.12.1 yet: Longhorn issue #11322
tracks a strict-local/offline-rebuild interaction for v1.15.0, and issue
#12319 tracks strict-local/auto-salvage creating duplicate replicas for
v1.14.0. The cluster has offline rebuilding disabled, but auto-salvage is
enabled. Do not change either global setting for this pilot.

Trial only on a **new disposable** CNPG cluster, not on existing `models-dev`
PVCs. In the pilot Cluster YAML, include:

```yaml
spec:
  instances: 3
  affinity:
    enablePodAntiAffinity: true
    podAntiAffinityType: required
    topologyKey: kubernetes.io/hostname
  storage:
    size: 2Gi
    storageClass: longhorn-cnpg-local
```

That `affinity` setting prevents two database instances landing on one node;
it may leave a pod Pending if one node lacks capacity. This is preferable to
mistakenly believing a three-instance DB spans three failure domains.
It is intentionally **not** applied to the live `models` Cluster yet.

## Safety gates: read-only checks first

```sh
kubectl config current-context
kubectl get nodes -o wide
kubectl -n models get cluster models-db -o yaml
kubectl -n models get pods -l cnpg.io/cluster=models-db -o wide
kubectl -n models get pvc -o wide
kubectl -n models-dev get pods,pvc -o wide
kubectl get sc longhorn-fast-replicated -o yaml
kubectl -n longhorn-system get volumes.longhorn.io
kubectl -n longhorn-system get settings.longhorn.io offline-replica-rebuilding -o yaml
kubectl get events -A --sort-by=.metadata.creationTimestamp
```

Confirm all running pods are Ready **and** `pg_stat_replication` shows active
streaming on the primary (or use `kubectl cnpg status` if installed). Require
all critical Longhorn volumes healthy, no unexplained node/disk pressure, and
measured reservation/physical space on each of Falcon1/2/3. In particular,
a three-instance anti-affinity rule requires three viable node storage targets.

Backups are an independent gate: demonstrate an application-consistent
database backup, successfully restore it to a disposable PostgreSQL instance,
and verify sample records. `Retain` is not a backup. Confirm the Longhorn
S3 target works end-to-end too; the historical signature/target issue is not
proof of current failure or success. Don't perform old-PVC cleanup before tests.

**Locality check:** verify each volume has one replica and that its replica is
on the same node as its CNPG pod after bootstrap and restart. Best-effort
locality may place the replica elsewhere when local scheduling is not possible.
Treat that as a failed locality check and stop the pilot; do not force locality
by changing global Longhorn settings. A separate follow-up must test
strict-local bootstrap, detach/attach, drain, node outage and recovery after
the installed Longhorn release includes fixes for issues #11322 and #12319.

## Pilot validation (non-production)

1. Create the test StorageClass through the approved GitOps path **only
   after** reviewing its cluster-wide effects; keep it opt-in.
2. Create a *new* disposable three-instance CNPG Cluster using the example
   affinity/storage snippet. Verify one pod and one Longhorn volume replica
   on each of Falcon1, Falcon2, and Falcon3. Confirm the replica is local to
   its pod after bootstrap and restart.
3. Verify no PostgreSQL instance is accidentally sharing a node, and confirm
   reads/writes and actual synchronous/asynchronous streaming behavior.
4. Benchmark INSERT throughput and p95/p99 query/commit latency against a
   similarly sized throwaway three-replica Longhorn test cluster; measure
   node CPU, network, disk I/O, and replica reserve savings.
5. Test a single standby failure, clean node drain, and recovery under
   observation. Confirm primary stays available and CNPG can rebuild the
   lost member without assuming its old single-replica PVC will migrate.
6. Test a database restore separately; **do not assume this pilot is safe
   until data recovery actually succeeds**.

Stop immediately on unsafe failover, PVC Pending, broken local placement,
unhealthy replicas, failed backups, excessive IO, or PostgreSQL timeline
divergence. Keep the existing production storage unchanged.

## Production migration is a distinct change

An existing bound PVC cannot be assigned a new storage class by editing
`Cluster.spec.storage.storageClass`. Changing live spec or scaling down
`numberOfReplicas` on a production volume is **not** a migration plan.
After the disposable pilot and backup restore pass, plan a separate,
application-aware copy/restore/cutover for one noncritical CNPG database.
Only then consider `models-dev`, and `models` after production recovery.
Retain old PVs and backups until the replacement has been verified and
operational. Preserve primary election history and avoid an unplanned failover.

Do not lower the global Longhorn 120% overprovisioning setting until actual
reservations fit the new cap, and don't raise it to 140% as a permanent
substitute for free space. Check disk and node anti-affinity before
claiming that replica savings translate into improved three-node resilience.

## References

- CloudNativePG storage:
  https://cloudnative-pg.io/docs/1.30/storage/
- CloudNativePG scheduling:
  https://cloudnative-pg.io/docs/1.30/scheduling/
- Longhorn locality:
  https://longhorn.io/docs/1.12.1/high-availability/data-locality/
- Longhorn class parameters:
  https://longhorn.io/docs/1.12.1/references/storage-class-parameters/
- Longhorn strict-local/offline rebuilding issue:
  https://github.com/longhorn/longhorn/issues/11322
- Longhorn strict-local/auto-salvage issue:
  https://github.com/longhorn/longhorn/issues/12319

## Live gate check — 2026-10-11

Read-only checks used the `default` Kubernetes context. Repeat these checks
before any deployment because the values below are a point-in-time record.

| Gate | Observed state | Result |
| --- | --- | --- |
| Nodes | Falcon1, Falcon2 and Falcon3 Ready | Pass |
| `models-db` | 3/3 Ready; primary `models-db-3`; all instances report timeline 3; both standbys stream asynchronously with zero replay lag; pods use three different nodes | Consistent recovery state at this check |
| `models-dev-db` | 3/3 Ready; primary `models-dev-db-1`; all instances report timeline 3; both standbys stream asynchronously with zero replay lag; pods use three different nodes | Pass |
| CNPG archiving | `models-db` reports continuous archiving working; no recent CNPG `Backup` resources were found for either models cluster | Restore gate remains open |
| Longhorn backup target | Read-only `just storage-backup-check` passed. `BackupTarget/default` was available and synced at 17:23Z; the script checked service readiness, backup secret references and the bucket configuration. It found 1,133 Longhorn Backup objects, 1,115 completed, and a latest completion at 04:33Z. A direct S3 request was skipped because the endpoint is cluster-internal. | Target and recent backup metadata confirmed; database restore not tested |
| Longhorn version and settings | v1.12.1; offline replica rebuilding `false`; auto-salvage `true`; over-provisioning `120%` | Do not change global settings |
| Longhorn volumes | 43 healthy, 2 degraded and 29 unknown across the cluster. All six bound models database volumes are attached and healthy with three replicas each. Five have one replica per node; the active `models-db-2` volume has two replicas on Falcon3 and one on Falcon2, and its volume locality is `disabled`. A released PV for an older `models-db-2` claim points to detached, unknown volume `pvc-749e83aa-8ee2-4dd7-9c10-7df54b737137` with three stopped replicas. | Do not clean up the released PV or volume; storage and recovery review remains open |
| Falcon2 vault disk | Host filesystem has about 22 GiB free and is 100% used; Longhorn reports about 223 GB free and marks the disk unschedulable | Do not schedule pilot data there; accounting gap remains unexplained |
| Falcon3 ZFS | `main` and `tank` are ONLINE with 7.89 TiB and 1.58 TiB free; both report zero read/write/checksum errors. Last scrub was 2025-04-15 with zero repaired bytes. | Capacity observed; both pools share Falcon3's failure domain |
| Physical disks | SMART passed for Falcon1 `/dev/sda` and Longhorn's Falcon3 `/dev/sde`. Falcon3 NVMe log reports critical warning 0, media errors 0, 50% used and 43°C. Falcon2 SMART required an unavailable sudo password; Falcon3 has no `smartctl` binary. | Incomplete; Falcon2 drives and four Falcon3 ZFS members are unchecked |
| Placement and load | Running pods: Falcon1 36, Falcon2 89, Falcon3 99. Node CPU: 16%, 62%, 66%; memory: 39%, 39%, 76%. Models pods already span all nodes. | No safe live rescheduling target identified from this snapshot |
| GitOps | Argo apps `models`, `models-dev`, `longhorn` and `minio-longhorn-backup` are Synced and Healthy | Pass |

The database timeline divergence and interrupted db2 restart in older notes
were not present in this check. Do not repeat recovery actions against the
current primary. The current six database PVCs are healthy and streaming, but
the old released `models-db-2` volume remains unknown and must be preserved
until its recovery role is understood. The cluster also has degraded and
unknown Longhorn volumes and recent probe timeout warnings. The `posse-party`
Argo app is Degraded; its database cluster is Hibernated with no pod or service
endpoints, and its migration Job fails with connection refused. This appears
consistent with the hibernated database, but confirm that hibernation is
intentional before changing either workload. These findings do not identify a
safe volume repair by themselves.

Pod counts alone do not justify moving stateful workloads. Keep Falcon3
hostPath and ZFS consumers there unless the data path changes deliberately.
For load balancing, select stateless workloads with no PVC or hostPath, then
use soft topology spread and compare CPU, memory and disk I/O before and after.
Do not move database or Longhorn replicas as a workload-balancing shortcut.

**Decision:** do not create the live pilot yet. First capture an
application-consistent backup and restore it to a disposable PostgreSQL
instance, inspect the six bound Longhorn volume states and the retained
historical volume, and check device health again. Resolve the Falcon2 vault
accounting gap. The read-only checks show current streaming recovery, but not
a tested restore path.

## Expected impact (estimate only)

A disposable pilot with three 2 GiB PVCs would reserve about 18 GiB of
replica capacity with three Longhorn replicas per PVC and 6 GiB with one
replica per PVC. That is an estimated 12 GiB, or 67%, reduction in requested
replica capacity for the pilot. Actual disk use depends on PostgreSQL data,
filesystem overhead, snapshots and WAL. No latency or throughput result is
available until the pilot runs.

The current six models database PVCs request 135 GiB total. A future approved
migration from three Longhorn replicas to one would reduce nominal replica
capacity from 405 GiB to 135 GiB, a 270 GiB estimate. This does not release
capacity from the already-bound volumes and is not a production migration
plan. Their PVCs and replica counts remain unchanged. Current replica placement
is not fully node-spread: the bound `models-db-2` volume has two replicas on
Falcon3. The old released `models-db-2` PV/volume must remain untouched until
the database recovery records explain its role.
