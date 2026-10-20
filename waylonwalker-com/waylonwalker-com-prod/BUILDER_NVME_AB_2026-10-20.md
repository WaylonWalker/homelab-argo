# WaylonWalker NVMe A/B trial, 2026-10-20

**Status: BLOCKED.** No candidate build or storage change ran. Production stayed on its current PVCs.

## Decision

Do not move production site, source, or cache data to Falcon3 host paths yet. The current NVMe filesystem has less than the required 20% free space. The site Longhorn volume is degraded. No tested restore evidence exists. These conditions fail the storage migration gate.

The issue requires a candidate with site releases, retained workspace, source checkout, and cache on one Falcon3 NVMe filesystem. It also requires at least 20 matched warm builds and two cold builds per candidate. This report contains no candidate result. Do not treat the current refresh records as an A/B result.

## Live inventory

Captured on 2026-10-20 from Kubernetes context `default`.

| Item | Live observation |
|---|---|
| Argo CD application | `waylonwalker-com-prod`, Synced and Healthy |
| Argo source revisions | homelab-argo `208794ff3a53c559ca7490d2bc358c62ab96ca80`; Markata chart `aac5b49752518ab84b7541385d0d42706e79a41d` |
| Builder image | `ghcr.io/waylonwalker/markata-go-builder:sha-aac5b49`, digest `sha256:190225a825b5c4ec2631402ae6b329f5134dd0fe5ff94a2530dd5600b44d9d9d` |
| Site image | `nginx:1.27.5-alpine`, digest `sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10` |
| Site and builder | Separate deployments on `falcon3`; one ready pod each |
| Builder mode | `builderAdmin.fast=false`; `builderAdmin.workspace.enabled=false`; normal Nginx serving |
| Site storage | 30 Gi Longhorn ext4 PVC, 4.4 GiB used, 25.6 GiB free, 11% inode use |
| Site files | `releases` 2.8 GiB; `.build-work` 1.6 GiB; `.builder-admin` 28 MiB; `public` 48 KiB |
| Source storage | 10 Gi Longhorn ext4 PVC, 2.2 GiB used, 7.6 GiB free, 10% inode use |
| Cache storage | Falcon3 `/dev/nvme0n1p4`, XFS, 466 GiB total, 383 GiB used, 83 GiB free, 3% inode use |
| Cache directory size | Not measured. The recursive size scan did not finish within 30 seconds. |
| Site PVC replicas | Requested 2; attached volume is `degraded`; only one replica runs on `falcon3` |
| Replica scheduling | Longhorn reports `precheck new replica failed: tags not fulfilled` |
| Backup system | Read-only `scripts/storage-backup-check.sh` passed; latest completed backup was `2026-10-20T22:22:24Z` |
| Restore evidence | No disposable restore with a matching sentinel was found or run |
| Node load sample | `falcon3`: 1558m CPU of 4 cores, 13922 MiB memory; builder pod: 312m CPU, 1378 MiB |

The host-path cache filesystem has about 17.8% free space. A move of the measured site and source data would use about 6.6 GiB more. That leaves about 76.4 GiB free, before peak-build and recovery space. The result fails the 20% free-space gate even before those reserves.

The production Argo application has automated pruning enabled. A PVC-to-hostPath chart change removes PVC objects from rendered manifests. Do not apply that change to production without first protecting the old claims and proving the rollback path.

## Existing build records

The builder state file held 20 recent successful `scheduled-refresh` records on the current image. They provide context only. They do not form a matched warm-build baseline because all records came from scheduled refreshes, and the refresh work was not isolated.

| Phase | p50 | p95 | n |
|---|---:|---:|---:|
| Prepare | 0.007 s | 0.022 s | 20 |
| Build | 90.169 s | 140.173 s | 20 |
| Promote | 4.154 s | 6.959 s | 20 |
| Prune | 15.009 s | 16.279 s | 20 |
| Prepare + build + promote (`total_ms`) | 94.107 s | 144.482 s | 20 |

These records show that preparation was near zero in the current deployment. They do not show the effect of an NVMe-local candidate. The records do not include copy, compare, digest, CPU wait, or disk I/O counters in this summary. The p95 values use the nearest-rank method.

## Public serving sample

One HTTPS request per path ran on 2026-10-20. These are single samples, not p50 or p95 measurements.

| Path | Status | Time to first byte |
|---|---:|---:|
| `/` | 200 | 0.339 s |
| `/archive/` | 200 | 0.312 s |
| `/reader/` | 200 | 0.326 s |
| `/api/search` without a query | 400 | 0.310 s |
| `/this-should-404/` | 404 | 0.369 s |

No 5xx response occurred in this small sample. This sample does not cover the required smoke paths, preview authentication, redirects, content negotiation, cache headers, ingress TLS details, restart, failed build, or rollback.

## Required operator actions

Complete these actions before any candidate build:

1. Increase usable Falcon3 NVMe capacity or free space through an approved storage plan. Keep at least 20% free space after migration, plus measured peak-build and recovery capacity. Do not lower Longhorn reservations or remove production data to meet this gate.
2. Resolve the Longhorn replica scheduling error. Wait until the production site volume reports `healthy` with two running replicas. Keep the old PVC, PV, replicas, snapshots, and backups.
3. Create a new backup of the authoritative source and site data. Restore each backup to a disposable target. Compare a recorded sentinel. Compare checksums. Do not change mounts until both restore checks pass.
4. Record the owner and the one-command rollback procedure. The rollback must restore the original PVC mounts while Nginx keeps serving the current release.
5. Create an isolated Argo application and namespace for the candidate. Set `automated.prune: false`. Use separate host-path directories on Falcon3. Keep Nginx and `builderAdmin.fast=false`.
6. Copy candidate data while the builder is idle. Compare checksums, symlinks, ownership, and Nginx readability. Keep the production PVCs mounted and unchanged.
7. Capture the baseline again, then run at least 10 matched warm builds and 2 cold builds for each arm. Alternate A/B order. Exclude or label scheduled refresh work. Record build IDs, phase timings, copy counters, CPU, I/O wait, node load, and free space. Record public Nginx p50/p95 TTFB and 5xx counts.
8. Run the required serving, restart, failed-build, and rollback checks against the canary. Keep the production serving path unchanged until every gate passes.

Read-only inventory commands:

```sh
kubectl config current-context
kubectl -n argocd get app waylonwalker-com-prod -o jsonpath='{.status.sync.status} {.status.health.status}'
kubectl -n waylonwalker-com-prod-notes get pods,pvc -o wide
kubectl get volumes.longhorn.io pvc-cbc9a896-5733-4892-ab42-be4fd2946a89 -n longhorn-system -o jsonpath='{.status.robustness}'
kubectl -n waylonwalker-com-prod-notes exec deploy/waylonwalker-com-prod-notes-builder-admin -- df -hT /data/site /data/source /data/cache
bash scripts/storage-backup-check.sh
```

The backup diagnostic checks backup infrastructure and age. It does not create a backup or prove a restore.

## Decision threshold

Accept the candidate only when the median `prepare + build + promote` time improves by at least 20% and 15 seconds. Require public p95 TTFB to worsen by no more than 10%. Require no increase in 5xx or permission incidents. Require no unacceptable cold-build regression. Require the disk headroom gate to pass.

Do not deploy if any gate fails or if measurement noise hides the result. The present evidence fails the disk headroom and restore gates. The production site volume is also degraded. No A/B threshold was measured.

## Evidence limits

No production setting, source content, PVC, PV, backup, or release changed during this inventory. No candidate deployment or build ran. No backup restore ran. The worktree inventory came from `origin/main` at `208794ff3a53c559ca7490d2bc358c62ab96ca80`; the operator's original checkout was left unchanged.
