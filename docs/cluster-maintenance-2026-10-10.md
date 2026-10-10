# Cluster maintenance plan — 2026-10-10

## Current state

Kubernetes `v1.36.5+k3s1` runs on three Ready nodes. The default context is active. Models is available. The primary uses a 40Gi PVC and has about 20Gi free. All database pods are Ready, but the Cluster Ready condition remains false. Git commit `3ff4aa9` changed the desired PVC size from 5Gi to 40Gi.

The other two database replicas need attention. `db1` has a 40Gi PVC, but its timeline is 2 while the primary is on timeline 3. It cannot stream. `db2` has a full 20Gi PVC and only two of three Longhorn replicas healthy. Expansion is blocked by the Falcon2 vault disk’s 20% minimum-free-space rule. That disk reports 65Gi free but 99% used. Longhorn reports about 250Gi available there. This differs from the host filesystem measurement and needs investigation before further placement.

The user authorized a backup and rebuild of the divergent replica from the current serving primary. Rebuild remains pending. Do not fail over, delete a PVC, or delete a replica before that decision. A Longhorn backup of the primary volume completed on 2026-10-10 at 02:44 UTC.

Longhorn commit `9e945f6` raised storage over-provisioning from 100% to 120%. It kept the 20% minimum-free-space setting. Falcon1 scheduling was briefly disabled and is now restored. No replica eviction, deletion, or failover occurred. A move of db2’s Falcon2 vault replica to Falcon2’s default disk is not yet proven safe. Node-level replica anti-affinity is hard, and Falcon1 scheduling is enabled again. Longhorn rebuilds a replacement before it removes an evicted replica. Before requesting eviction, establish a valid target. Monitor the rebuild during eviction. [Eviction guide](https://longhorn.io/docs/1.12.0/nodes-and-volumes/nodes/disks-or-nodes-eviction/) · [Scheduling guide](https://longhorn.io/docs/1.12.0/nodes-and-volumes/nodes/scheduling/)

## Recovery gates

1. Decide whether to preserve the divergent `models-db-1` branch or rebuild it from `models-db-3`.
2. Establish a safe destination for the `models-db-2` Longhorn replica on the vault disk.
3. Before requesting eviction, calculate reservation and physical capacity for the replacement replicas.
4. Complete the `models-db-2` expansion to 40Gi after its Longhorn replicas permit expansion.
5. Require active PostgreSQL streaming, a true Cluster Ready condition, and healthy Longhorn volumes before CNPG maintenance.
6. Before Longhorn 1.13 maintenance, establish a tested backup restore procedure. Its downgrade restriction prevents a version rollback.

PVC expansion cannot be reversed by shrinking the volume. Preserve the current primary, divergent branch, and backups during recovery.

## Completed core updates

| Component | Change and state | Rollback or caution |
|---|---|---|
| cert-manager | Commit `3004fed` updated 1.21.1 to 1.21.2. All three rollouts completed. All 45 certificates and both ClusterIssuers are Ready. | Revert `3004fed`, push, and refresh the Argo application if rollback is needed. Keep the cert-manager CRDs aligned with the chosen controller version. [Release notes](https://github.com/cert-manager/cert-manager/releases/tag/v1.21.2) · [Upgrade guide](https://cert-manager.io/docs/installation/upgrade/) |
| Argo CD | Commit `3f2d4b7` changed chart 10.4.2 to 10.10.2 (app 3.5.2 to 3.5.4). The application is Synced and Healthy. All rollouts completed, and the ingress `/healthz` response is `ok`. | Watch the Argo application, pods, and child app sync. Revert `3f2d4b7`, push, and refresh the parent app if needed. A rendered 10.4.2 manifest is at `/tmp/maintenance-version-diffs/argocd-render-10.4.2.yaml`. The local Argo CLI had no authenticated session. [Chart](https://github.com/argoproj/argo-helm/tree/main/charts/argo-cd) · [Upgrade guide](https://argo-cd.readthedocs.io/en/stable/operator-manual/upgrading/overview/) |

## Remaining inventory and order

| Priority | Component | Installed | Upstream version checked | Action |
|---|---|---:|---:|---|
| P0 | CloudNativePG | 1.30.0 | 1.30.1 | Hold until all database replicas and storage recover. Version 1.30.1 changes the default PostgreSQL image from 18.4 to 18.6. Pin the current image or schedule that minor update separately. [Release notes](https://cloudnative-pg.io/docs/1.30/release_notes/v1.30/) · [Upgrade guide](https://cloudnative-pg.io/docs/1.30/installation_upgrade/) |
| P0 | Longhorn | 1.12.1 | 1.12.1 on 1.12; 1.13.0 current | Hold version changes during recovery. Longhorn does not support downgrade after a successful upgrade. Before restoring 100%, migrate reservations until they fit that limit. Falcon1 currently reserves about 273Gi on a 238Gi disk. [Upgrade guide](https://longhorn.io/docs/1.13.0/deploy/upgrade/) · [Releases](https://github.com/longhorn/longhorn/releases) |
| P2 | Argo Events | chart 2.4.15, app 1.9.6 | chart 2.4.27, app 1.9.11 | Review CRDs and RBAC, then patch after database recovery. [Chart](https://github.com/argoproj/argo-helm/blob/main/charts/argo-events/Chart.yaml) |
| P2 | ExternalDNS | chart 1.22.0, app 0.22.0 | chart 1.23.0, app 0.23.0 | Review policy and annotations first. Releases can change DNS record behavior. [Releases](https://github.com/kubernetes-sigs/external-dns/releases) |
| P2 | Sealed Secrets | chart 2.19.3, app 0.39.1 | chart 2.20.0, app 0.40.0 | Before update, establish a sealing-key backup and perform a decryption test. [Releases](https://github.com/bitnami/sealed-secrets/releases) |
| P2 | NFS CSI | 4.11.0 | 4.13.5 | Schedule a node plugin rollout window and inspect NFS mounts. [Releases](https://github.com/kubernetes-csi/csi-driver-nfs/releases) |
| P2 | System Upgrade Controller | 0.15.0 | 0.20.1 | Review the existing OutOfSync/Healthy state and plans before updating. Do not combine with node upgrades. [Releases](https://github.com/rancher/system-upgrade-controller/releases) |
| P3 | kube-prometheus-stack | chart 88.6.1 | chart 92.3.0 | Defer the broad operator, CRD, and monitoring stack update. [Chart index](https://prometheus-community.github.io/helm-charts/index.yaml) |
| P3 | Grafana Alloy | chart 1.13.0, app 1.20.0 | chart 1.13.1, app 1.20.1 | Low urgency patch after recovery. [Chart index](https://grafana.github.io/helm-charts/index.yaml) |
| P3 | Loki | chart 7.0.0, app 3.6.7 | chart 7.3.0, app 3.6.12 | Review schema and object-store settings before update. [Chart index](https://grafana.github.io/helm-charts/index.yaml) |
| P2 | Traefik | 3.7.13 | 3.7.13 | No image update needed. Review the existing CRD drift separately. [Releases](https://github.com/traefik/traefik/releases) |
| P3 | Tempo | chart 1.24.4, app 2.9.0 | same | No update needed. [Chart index](https://grafana.github.io/helm-charts/index.yaml) |
| P3 | OpenTelemetry Collector | chart 0.172.0, app 0.159.0 | chart 0.175.1, app 0.161.0 | Check the image pin and configuration before update. [Chart index](https://open-telemetry.github.io/opentelemetry-helm-charts/index.yaml) |
| N/A | Argo Workflows | disabled | 3.7.18 latest 3.x | No action. The manifests are commented out. [Releases](https://github.com/argoproj/argo-workflows/releases) |

## Health and validation notes

The last reported ZFS status was online with zero errors. Its last scrub was April 2025. Falcon1 SMART passed with zero bad sectors. Falcon2 drive health is unchecked because sudo was unavailable. Falcon3 drive health is unchecked because `smartctl` is missing. Existing drift includes the system-upgrade-controller and Traefik CRDs. Minecraft RBAC sync fails because the `kraft` namespace is absent. Both `kraft` and `kave` namespaces are absent. The `shots` application is Progressing.

No CI workflow ran. `gh run` returned no runs. Server-side dry runs and rendered manifest comparisons served as validation. Independent Luna review passed for each deployed change. No upgrade regression required rollback. All running pods are Ready. Argo parent applications are Synced and Healthy. The Argo API reports `v3.5.4`. A cert-manager Issuer admission dry run succeeded. Authenticated Argo CLI operations remain unverified. Do not treat missing checks as healthy. Resolve database and Longhorn state first. Then schedule the remaining core patches, followed by telemetry updates.
