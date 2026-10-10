# Cluster maintenance plan — 2026-10-10

## Current state

Kubernetes `v1.36.5+k3s1` runs on three Ready nodes. Models is available. The primary uses a 40Gi PVC with about 20Gi free. Database pods are Ready, and CNPG reports the cluster Ready. Commit `3ff4aa9` changed desired PVC size from 5Gi to 40Gi.

`db2` has a 40Gi filesystem and streams from primary `db3`. Its Longhorn volume is healthy with three read-write replicas; the vault copy was removed after four copies were verified. The approved `db1` rebuild completed from `db3`. New PVC UID `84b8b296-96a3-44a2-a245-5558ff1f19be` is bound to a new Longhorn volume. Both replicas stream on timeline 3, and CNPG reports Ready. After backup checks, the old PV and detached volume were removed; backup objects remain Completed.

Validated logical archives exist for primary `db3` before rebuild and divergent `db1`. Fresh Longhorn backups of old `db1` and `db2` completed. Files are under `/home/waylon/.local/state/homelab-maintenance/2026-10-10/`: `models-primary-db3.dump`, `models-primary-db3-before-db1-rebuild.dump`, `models-divergent-db1.dump`, metadata files, and `SHA256SUMS`. Keep backup objects and archives.

Longhorn commit `9e945f6` set storage over-provisioning to 120%. Commit `9487d06` temporarily raised it to 140% for bounded recovery placement. The new Git change restores 120%; the 20% minimum-free-space setting is unchanged. Falcon1 scheduling is enabled.

After removing the old `db1` volume, Falcon1 books 285.2Gi on a 237.9Gi disk. The 120% cap is 285.4Gi, leaving 0.2Gi scheduler headroom. Physical free is about 128Gi; the 20% minimum is 47.6Gi. Keep reservations below the cap and monitor all disks. [Scheduling guide](https://longhorn.io/docs/1.12.0/nodes-and-volumes/nodes/scheduling/)

## Recovery gates

1. Database recovery is complete: both replicas stream on timeline 3, and CNPG reports Ready. The old branch backup and logical archives remain available.
2. The CNPG operator is 1.30.1. Verify all clusters and pinned PostgreSQL images after future changes.
3. Keep Longhorn at 1.12.1 until its 1.13 restore path is tested; downgrade after upgrade is unsupported.

Do not use CNPG `--keep-pvc`: it detaches but keeps the claim name, which CNPG can reuse. Default destroy removes the claim; Retain preserves its PV and storage. [CNPG plugin](https://cloudnative-pg.io/documentation/current/kubectl-plugin/) · [CNPG 1.30 release notes](https://cloudnative-pg.io/docs/1.30/release_notes/v1.30/) · [Kubernetes PV reclaim policy](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#reclaiming)

PVC expansion cannot be reversed by shrinking the volume. Keep the current primary and recovery backups intact.

## Completed core updates

| Component | Change and state | Rollback or caution |
|---|---|---|
| cert-manager | `3004fed`: 1.21.1 to 1.21.2; all rollouts and issuers Ready. | Revert commit if needed; keep CRDs aligned. [Release notes](https://github.com/cert-manager/cert-manager/releases/tag/v1.21.2) · [Upgrade guide](https://cert-manager.io/docs/installation/upgrade/) |
| Argo CD | `3f2d4b7`: chart 10.4.2 to 10.10.2 (app 3.5.2 to 3.5.4); healthy, rollouts complete, `/healthz` ok. | Revert if needed. Old render: `/tmp/maintenance-version-diffs/argocd-render-10.4.2.yaml`; CLI auth unverified. [Chart](https://github.com/argoproj/argo-helm/tree/main/charts/argo-cd) · [Upgrade guide](https://argo-cd.readthedocs.io/en/stable/operator-manual/upgrading/overview/) |

## Remaining inventory

| Priority | Component | Installed | Upstream version checked | Action |
|---|---|---:|---:|---|
| P0 | CloudNativePG | 1.30.1 | 1.30.1 | Upgraded and healthy. Operator update rolled active instances. Smart shutdown allowed 180 seconds for idle sessions, causing brief app reconnects. All restarted instances recovered and image pins stayed unchanged. The existing `performpeoria-dev` plugin error remains. Rollback `ea41302` triggers another rolling update. [Release notes](https://cloudnative-pg.io/docs/1.30/release_notes/v1.30/) · [Upgrade guide](https://cloudnative-pg.io/docs/1.30/installation_upgrade/) |
| P0 | Longhorn | 1.12.1 | 1.12.1 on 1.12; 1.13.0 current | Recovery is complete. The reservation is restored to 120% after Argo sync. Hold the version upgrade until the 1.13 restore path is tested. Longhorn does not support downgrade after upgrade. [Upgrade guide](https://longhorn.io/docs/1.13.0/deploy/upgrade/) · [Releases](https://github.com/longhorn/longhorn/releases) |
| P1 | PostgreSQL images | 8 clusters on 17.2; one on 17 | 17.11 | Hold for health and backups. Legacy `17.2` is deprecated Bullseye system; check OS/extensions. 17.11 may need decoder allowlist changes and `btree_gist`/`ltree` reindex. Only performpeoria dev/prod have schedules (last success Oct 3); Postiz has no schedule. [Images](https://github.com/cloudnative-pg/postgres-containers/blob/main/README.md) · [17.11 notes](https://www.postgresql.org/docs/17/release-17-11.html) |
| P2 | Argo Events | chart 2.4.27, app 1.9.11 | same | Upgraded and healthy. Revert `f36696c` to roll back. CRD schemas and RBAC are unchanged. One replica uses Recreate; client-side dry run passes, SSA dry run rejects retained `rollingUpdate`. Keep Argo client-side apply. [Chart](https://github.com/argoproj/argo-helm/blob/main/charts/argo-events/Chart.yaml) |
| P2 | ExternalDNS | chart 1.22.0, app 0.22.0 | chart 1.23.0, app 0.23.0 | Review DNS policy first. [Releases](https://github.com/kubernetes-sigs/external-dns/releases) |
| P2 | Sealed Secrets | chart 2.19.3, app 0.39.1 | chart 2.20.0, app 0.40.0 | Back up sealing keys and test decryption first. [Releases](https://github.com/bitnami/sealed-secrets/releases) |
| P2 | NFS CSI | 4.11.0 | 4.13.5 | Schedule rollout; inspect NFS mounts. [Releases](https://github.com/kubernetes-csi/csi-driver-nfs/releases) |
| P2 | System Upgrade Controller | 0.15.0 | 0.20.1 | Review drift and plans; separate from node upgrades. [Releases](https://github.com/rancher/system-upgrade-controller/releases) |
| P3 | kube-prometheus-stack | chart 88.6.1 | chart 92.3.0 | Defer broad operator and CRD update. [Chart index](https://prometheus-community.github.io/helm-charts/index.yaml) |
| P3 | Grafana Alloy | chart 1.13.0, app 1.20.0 | chart 1.13.1, app 1.20.1 | Low urgency patch after recovery. [Chart index](https://grafana.github.io/helm-charts/index.yaml) |
| P3 | Loki | chart 7.0.0, app 3.6.7 | chart 7.3.0, app 3.6.12 | Review schema and object store. [Chart index](https://grafana.github.io/helm-charts/index.yaml) |
| P2 | Traefik | 3.7.13 | 3.7.13 | No image update needed. Review the existing CRD drift separately. [Releases](https://github.com/traefik/traefik/releases) |
| P3 | Tempo | chart 1.24.4, app 2.9.0 | same | No update needed. [Chart index](https://grafana.github.io/helm-charts/index.yaml) |
| P3 | OpenTelemetry Collector | chart 0.172.0, app 0.159.0 | chart 0.175.1, app 0.161.0 | Check image pin and configuration. [Chart index](https://open-telemetry.github.io/opentelemetry-helm-charts/index.yaml) |
| N/A | Argo Workflows | disabled | 3.7.18 latest 3.x | No action. The manifests are commented out. [Releases](https://github.com/argoproj/argo-workflows/releases) |

## Health and validation notes

ZFS had zero errors; scrub April 2025. Falcon1 SMART passed; other drives unchecked. Drift: system-upgrade-controller/Traefik CRDs, missing `kraft`/`kave`, and `shots` Progressing.

No CI ran; server-side dry runs and render comparisons passed. The CNPG rollout caused brief PostgreSQL restarts; all instances recovered. Argo CD reports `v3.5.4`; cert-manager issuers are Ready; Argo Events, Longhorn, and CNPG operator are Synced and Healthy. Argo CLI authentication is unverified.
