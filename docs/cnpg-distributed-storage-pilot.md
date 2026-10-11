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
- Prior 2026-10-10 recovery left `models-db` with an interrupted db2 restart,
  an earlier divergent db1 timeline, and storage pressure. **Verify all of
  these from live state** before any storage reduction.
- Argo manages live apps with self-heal/prune; a YAML edit to an existing
  database spec is not a safe migration.

## Candidate architecture

Three CNPG PostgreSQL pods, one per healthy Kubernetes node, enforced through
CNPG pod anti-affinity, each using **one** local Longhorn replica for its PVC.
The PostgreSQL instances provide cross-node replication (3 DB copies instead
of 3 DB copies × 3 Longhorn copies). This is an *application-level* availability
model, not a storage-level HA model. A node failure can destroy its individual
single-replica volume; CNPG needs a healthy surviving standby, capacity to
bootstrap a replacement, and tested logical/physical backups.

`docs/examples/longhorn-cnpg-local-pilot.yaml` defines an **unmanaged,
opt-in, not-yet-applied** `longhorn-cnpg-local` StorageClass. It is intentionally
outside all Argo source paths and is not the default class. The class has
`numberOfReplicas: "1"`, `dataLocality: strict-local`, `Retain`,
`WaitForFirstConsumer`, and no implicit Longhorn recurring jobs.

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

**Strict-local compatibility check:** Longhorn has reported issues with
offline replica rebuilding and auto-salvage interacting with strict-local
volumes. On the installed version, check feature settings, test bootstrap,
detach/attach, pod drain and node recovery in a disposable pilot, and inspect
volume replicas. Do not globally toggle offline rebuilding to make the pilot
pass; seek a documented per-volume workaround or defer strict-local.

## Pilot validation (non-production)

1. Create the test StorageClass through the approved GitOps path **only
   after** reviewing its cluster-wide effects; keep it opt-in.
2. Create a *new* disposable three-instance CNPG Cluster using the example
   affinity/storage snippet. Verify one pod and one Longhorn volume replica
   on each of Falcon1, Falcon2, and Falcon3.
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
