# WaylonWalker NVMe A/B trial, 2026-10-20

**Status: BLOCKED pending production replica recovery and restore checksum comparison.** No A/B result exists. No candidate build or production mount change ran. Production remained on its existing PVCs.

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
| Restore evidence at first inventory | No disposable restore with a matching sentinel was found or run |
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

## Initial operator checklist (superseded by trial status below)

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

Do not deploy if any gate fails or if measurement noise hides the result. The initial inventory failed the disk headroom gate. The post-prune inventory now shows 271 GiB free (58% of the 466 GiB XFS filesystem), so the earlier capacity blocker is cleared pending a peak-build and recovery headroom calculation. The production site volume remains degraded. No A/B threshold was measured.

## Evidence limits

No production setting, source content, PVC, PV, or release changed during the first inventory. No candidate deployment or build ran during that inventory. The worktree inventory came from `origin/main` at `208794ff3a53c559ca7490d2bc358c62ab96ca80`; the operator's original checkout was left unchanged.

## Follow-up inventory, 2026-10-21

The owner ran a supported CRI image prune on Falcon3. A post-prune SSH scan measured 271 GiB free on `/var`, up from 83 GiB. The XFS mount is 466 GiB total and 195 GiB used.

| Path or measurement | Post-prune result |
|---|---:|
| `/var/lib/rancher/k3s` | 33 GiB |
| `/var/lib/rancher/k3s/agent/containerd` | 29 GiB |
| Containerd overlayfs snapshots | 21 GiB |
| Containerd content blobs | 7.3 GiB |
| CRI image filesystem | 22,501,687,296 bytes, about 21 GiB |
| Registered CRI images | 70 entries, down from 580 |
| CRI containers | 117 running; 51 exited |
| `/var/lib/longhorn/fast-nvme` | 105 GiB |
| `/var/lib/markata-go` | 4.2 GiB: cache 973 MiB; workspace directory 3.3 GiB |
| `/var/lib/containers` | 1.3 GiB |
| `/var/lib/kubelet` | 530 MiB |
| `/var/log` | 26 GiB: PCP 21 GiB; journal 4 GiB; pods 1 GiB |
| `/var/home` | 7 GiB |
| ZFS `main` | 7.69 TiB available by `df`; 7.69 TiB available by `zfs list` |

The live Builder Admin pod mounts only the source PVC, site PVC, and cache host path. It does not mount the 3.3 GiB host workspace directory. Do not treat that directory as disposable without an owner review.

The one running replica for the production site volume occupies about 105 GiB under `/var/lib/longhorn/fast-nvme/replicas`. Do not move or delete it. Falcon3's `fast-nvme` disk allows scheduling. Falcon2's other `fast` disk, `/mnt/vault/longhorn`, does not allow scheduling. The `longhorn-build-fast` StorageClass selects `fast` and requests two replicas. This explains the current scheduling failure. No Longhorn scheduling setting changed.

`du -xhd1 /var` reports about 178 GiB, while `df` reports 195 GiB used. The difference is about 17 GiB. A deleted-open file scan found 148 descriptors with 2.20 TB of logical size. Only one descriptor was on the NVMe, with zero allocated blocks. Deleted-open files do not explain the current difference.

The new site backup completed at `2026-10-21T02:29:42Z`. It covers volume `pvc-cbc9a896-5733-4892-ab42-be4fd2946a89`, size `32212254720` bytes. Longhorn uploaded `923364465` new bytes. The source backup completed at `2026-10-21T02:24:52Z`. It covers volume `pvc-dccccdba-0c59-4ba9-a759-3b268e59c8d4`, size `10737418240` bytes. Longhorn uploaded `7778764` new bytes.

Disposable restore volumes `issue-143-site-restore-20261021` and `issue-143-source-restore-20261021` were created from these backups. The source restore completed. A read-only pod mounted it and confirmed the sentinel hash `816705def28caf37623b50c987c41115a58b5f8549ebf7e54c18e782e9291aee` for `/restore/markata-go.toml`; the Git checkout is present. The site restore advanced to 100%, detached, and cleared `restoreRequired`. A read-only pod confirmed that `/restore/current/index.html` has the recorded pre-backup SHA-256 `431b7f5671582a98626829013deab3de2b8af59f4dcbd1e54f875456ed2679c6`.

At `2026-10-21T03:18Z`, Falcon3 `/var` had 274 GiB free of 466 GiB (59%) and about 242.9 million free inodes. This clears the 20% free-space floor before trial work, but peak-build and recovery headroom still need measurement. The production site PVC still has one running replica on Falcon3, while Falcon2's other `fast` disk is not schedulable. Keep production settings and serving paths unchanged. The issue permits an isolated canary; the degraded production volume remains a recovery risk and blocks any production cutover until its resilience is restored.

The source and site restore sentinel checks passed. Their temporary PV/PVC bindings were moved from the restore-check namespace into the A canary namespace. Both restore Longhorn volumes remain detached when not mounted. The source sentinel is `markata-go.toml`; the site sentinel is `current/index.html`. The seed copy and full tree comparisons completed; results and later candidate activity are recorded in the final status section below.

### Public serving baseline, 2026-10-21

Before the canary copy started, the public endpoints below each received 20 sequential HTTPS requests. TTFB includes the external network path. A response with status 301 or 404 is expected for the redirect and missing-path rows. No 5xx response occurred.

| Path | Status counts | p50 TTFB | p95 TTFB | n |
|---|---|---:|---:|---:|
| `/` | 200: 20 | 0.289 s | 0.334 s | 20 |
| `/just-fucking-use-kubernetes/` | 200: 20 | 0.285 s | 0.324 s | 20 |
| `/archive/` | 200: 20 | 0.293 s | 0.325 s | 20 |
| `/8bitcc.png` | 200: 20 | 0.291 s | 0.311 s | 20 |
| `/reader/` | 200: 20 | 0.294 s | 0.342 s | 20 |
| `/rss.xml` | 200: 20 | 0.292 s | 0.325 s | 20 |
| `/api/search?q=markata` | 200: 20 | 0.311 s | 0.343 s | 20 |
| `/this-should-404/` | 404: 20 | 0.315 s | 0.348 s | 20 |
| `https://www.waylonwalker.com/` | 301: 20 | 0.278 s | 0.296 s | 20 |

The final `www` redirect resolves to `https://waylonwalker.com/` with status 200. TLS verification passed. The home page returned `text/html` when the request sent `Accept: application/json`. The home page cache header was `public, max-age=0, s-maxage=60`; `/8bitcc.png` returned `max-age=31536000` and `public, immutable`; `/rss.xml` returned `text/xml`. These are baseline checks only. Repeat them after and during the candidate workload. [Raw HTTPS samples](BUILDER_NVME_AB_TTFB_BEFORE_2026-10-21.jsonl).

At the initial canary checkpoint, production used image `sha-8682b60`; its later transition to `sha-99637e3` is recorded below. The production site Longhorn volume remains degraded: the replica scheduler reports `ReplicaSchedulingFailure` because the required disk tags are not fulfilled.

Two recent production builds used source commit `ce0db0c5259f72b1d879f15ce21835aae2b5168b` and builder image `sha-d37c9dd` (digest `sha256:77dd3fc12892e5952e9c7f997aa23431661cad1662459a1a78f52660b189bbbc`). Their `prepare + build + promote` times were 225.330 s (webhook) and 250.206 s (manual UI), median 237.768 s, n=2. A subsequent startup-revision build on the current `sha-8682b60` image took 271.232 s for `prepare + build + promote`; it is a cold image-revision transition, n=1. These are context only, not matched A/B results, and do not meet the 10-build gate.


## Trial status, 2026-10-21 — BLOCKED

**BLOCKED: Falcon3 pod and CPU scheduling headroom for isolated canaries after the production builder rollout.** The disk-space floor is clear: `/var` measured 291,991,027,712 bytes free (about 272 GiB, 58.5%) with about 99.5% of inodes free. Scheduling headroom is not clear. `falcon3` has a four-CPU allocatable capacity, 110-pod limit, 107 running pods, and 3,870m CPU requests (96%). During the canary run, production Builder Admin and Search replacements became Pending with `Too many pods` and `Insufficient cpu`. The A and B Builder Admins and B site server were scaled to zero to restore production scheduling. Do not restart the canaries until a capacity change or an operator-approved scheduling plan leaves production rollouts schedulable.

Production recovered to Argo `Synced Healthy`. Builder Admin, Search, and Site are Ready, with Builder Admin and Search on `ghcr.io/waylonwalker/markata-go-builder:sha-99637e3`. Startup-revision build `build-1792556114965423430` succeeded at `2026-10-21T04:18:44Z` (prepare 19 ms, build 196,408 ms, promote 12,783 ms, prune 15,589 ms, total 209,490 ms). This was an image-transition build, not a matched trial. After it completed, each public path below received 20 sequential HTTPS requests. No 5xx response occurred, all expected status codes were returned, and every p95 was below its pre-canary baseline:

| Path | Status counts | Before p95 | After p50 | After p95 | n |
|---|---:|---:|---:|---:|---:|
| `/` | 200: 20 | 0.334 s | 0.267 s | 0.293 s | 20 |
| `/just-fucking-use-kubernetes/` | 200: 20 | 0.324 s | 0.262 s | 0.285 s | 20 |
| `/archive/` | 200: 20 | 0.325 s | 0.260 s | 0.281 s | 20 |
| `/8bitcc.png` | 200: 20 | 0.311 s | 0.256 s | 0.279 s | 20 |
| `/reader/` | 200: 20 | 0.342 s | 0.260 s | 0.291 s | 20 |
| `/rss.xml` | 200: 20 | 0.325 s | 0.272 s | 0.309 s | 20 |
| `/api/search?q=markata` | 200: 20 | 0.343 s | 0.273 s | 0.289 s | 20 |
| `/this-should-404/` | 404: 20 | 0.348 s | 0.279 s | 0.292 s | 20 |
| `https://www.waylonwalker.com/` | 301: 20 | 0.296 s | 0.250 s | 0.265 s | 20 |

These are post-build production samples, not measurements during canary work. Raw requests are in [post-build HTTPS samples](BUILDER_NVME_AB_TTFB_AFTER_2026-10-21.jsonl).

### Data collected before pausing

Seed-copy comparisons passed. The restored site tree matched across 341,479 entries (SHA-256 `20aca7f9abb45bc8fef3b021651becc7f4f28f867c8b3613e2b842e34df64be2`); the source tree matched across 59,581 entries (SHA-256 `64dd2d2d6e05b0be2f3512d39a5b76cccbb98a2b807787805191e07d6275f9c7a`); A and B cache trees matched across 17,804 entries (SHA-256 `704cf0b146244d85e48d6c52cfa5a021667cee545fa15ab648734931a247bbdc`). Backup restore sentinels also passed as recorded above.

The candidates initially used identical builder image `sha-8682b60`, source commit `ce0db0c5259f72b1d879f15ce21835aae2b5168b`, and separate storage. Three clean matched warm pairs completed before production changed to `sha-99637e3`. No cold builds ran. The analyzer reports:

| Warm `prepare + build + promote` | Median | p95 | n |
|---|---:|---:|---:|
| A: restored Longhorn volumes | 96.189 s | 96.750 s | 3 |
| B: Falcon3 NVMe hostPaths | 85.052 s | 94.035 s | 3 |

The paired median improvement is 11.049 s (11.6%), with a bootstrap 95% percentile interval of 2.156–12.565 s. This misses both required thresholds (20% and 15 seconds) and is too small a sample for a decision. The candidate samples had no 5xx responses. During the three pairs, public home-page p95 TTFB was 0.303 s on A (n=57) and 0.306 s on B (n=52), with zero 5xx; these small samples do not complete the required all-path before/after p95 comparison. The JSONL retains phase records, build IDs, source commit, publication counters, CPU and I/O counters, node samples, and TTFB samples: [partial trial records](BUILDER_NVME_AB_RUNS_2026-10-21.jsonl).

Pair four was interrupted after B completed and was not recorded as a matched pair. Do not count it. The production image then changed while canaries were running, so the partial results cannot be combined with a future trial on `sha-99637e3`.

### Safe resume steps

1. Add Falcon3 allocatable CPU/pod capacity or an approved placement plan that preserves room for production rollout replacements while the two isolated builders run. Current evidence is 96% requested CPU and 107/110 pods; filesystem free space alone does not clear this blocker.
2. Restore the production site Longhorn volume to its required two healthy replicas before any production storage cutover. Do not change Longhorn disk tags, force replicas, or move the production mount as part of this experiment.
3. Confirm production is idle and healthy, select the same current builder image and source revision for both arms, then manually sync the candidate Apps. The candidate manifests now have automated sync disabled. Keep `prune:false` and retain all candidate PVs, PVCs, hostPath copies, backups, and restore volumes.
4. Re-run at least 10 clean matched warm pairs and 2 cold builds per arm, with the new image/source tuple. Record CPU, I/O wait, load, free bytes/inodes and public all-path TTFB. Stop the trial if production rollout pods become Pending or any production 5xx/availability incident occurs.
5. Compare against the acceptance gates above. Keep this PR in draft and do not cut production over until every gate passes and restore/rollback steps are rehearsed.

At pause, both candidate deployments were scaled to zero. Their PVCs remained Bound, including A's restored Longhorn site/source PVs and B's NVMe hostPath data; backups and restore volumes were retained. Production serving remained on its original production PVCs. No production mount migration or Longhorn scheduling change was made.
