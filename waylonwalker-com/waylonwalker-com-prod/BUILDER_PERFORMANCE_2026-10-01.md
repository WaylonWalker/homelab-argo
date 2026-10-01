# Notes production builder validation — 2026-10-01 UTC

Scope: namespace `waylonwalker-com-prod-notes`, Argo application `waylonwalker-com-prod`, public site `https://waylonwalker.com`, builder `https://build.waylonwalker.com`.

## Failure and engine corrections

The failed jobs tried writing root `index.md` over an old generated redirect directory. Engine PR [#1480](https://github.com/WaylonWalker/markata-go/pull/1480) migrates only the exact legacy generated directory, preserving user files and rejecting ambiguous contents. Its [CI](https://github.com/WaylonWalker/markata-go/actions/runs/36802843085) passed. Production subsequently published three successful releases with ordinary `index.md` and `index.txt` files; both public URLs return 200.

PR [#1481](https://github.com/WaylonWalker/markata-go/pull/1481) wires successful-release markers into retained workspace preparation. Only a workspace proven to match current can skip reseeding. Failure, rollback, or missing markers force a safe seed. Its [CI](https://github.com/WaylonWalker/markata-go/actions/runs/36804497373) passed.

PR [#1483](https://github.com/WaylonWalker/markata-go/pull/1483) detaches pruned releases under the publication lock, then deletes their trees outside it. Production previously recorded 43–75 seconds of promotion waiting while pruning held that lock. Its [CI](https://github.com/WaylonWalker/markata-go/actions/runs/36806596917) passed, as did local full tests, lint, and targeted race tests. A concurrency regression blocks deletion and verifies promotion still finishes. Interrupted deletion is retried on the next prune; internal staging/pruning directories cannot be rollback targets.

## Storage and measurement conditions

- Builder is pinned to `falcon3`, with four CPUs. Other workloads and Longhorn consume substantial CPU; a sample during seeding showed about 1% CPU idle.
- Source PVC: Longhorn, three HDD-backed replicas on falcon3.
- Release PVC: 30 GiB `longhorn-build-fast`, two replicas: falcon3 NVMe and falcon2 HDD. The class name does not mean both replicas use SSDs. Durability remains unchanged.
- Previous cache: ZFS HDD mirror at `/mnt/main/walkershare/waylon/cache/waylonwalker.com`.
- New persistent cache: `/var/lib/markata-go/waylonwalker-com-prod/cache`, mounted at `/data/cache` on falcon3 XFS NVMe `/dev/nvme0n1p4`. Existing build and plugin caches were copied, then synchronized again after baseline jobs. Source cache symlinks resolve to `/data/cache/build` and `/data/cache/plugin`.
- Trial retained workspace: `/var/lib/markata-go/waylonwalker-com-prod/workspace`, mounted at `/data/work`, output `/data/work/build`, on the same physical NVMe as the new cache. Published releases remain on replicated Longhorn.
- Output is approximately 3.4 GiB. Building on the release filesystem permits atomic rename promotion. Building on local NVMe requires a complete, validated cross-filesystem copy before switching current.
- Measurements use real scheduled `reader-update` jobs. Encryption remained enabled. Content, cache state, CPU load, and prune overlap vary; these are operational observations, not a controlled CPU benchmark.
- Reader cadence was temporarily shortened from 30 minutes to five minutes to collect completed jobs. Restore it after validation.
- Prune runs asynchronously and is separately recorded; its duration must not be added again to total job time. With the older locking implementation, a following job's promotion could wait for that prune.

## Completed production jobs

| Configuration | Build ID | Prepare s | Build s | Promote s | Total s | Result |
|---|---|---:|---:|---:|---:|---|
| Root fix, workspace on release PVC; first successful run | build-1790820601919297149 | 341.990 | 158.882 | 0.074 | 500.948 | Published |
| Same filesystem, warm | build-1790821123384860152 | 18.167 | 64.233 | 43.376 | 125.777 | Published |
| Same filesystem, warm | build-1790821269281719376 | 21.690 | 72.617 | 75.393 | 169.702 | Published |

The last two promotion times include pruning lock contention. The first run's 74 ms promotion demonstrates the cheap same-filesystem rename once that lock is available.

Further trial and final-configuration results are recorded below after successful publication.

### NVMe output trial

| Configuration | Build ID | Prepare s | Build s | Promote s | Total s | Result |
|---|---|---:|---:|---:|---:|---|
| Local NVMe output and cache; first run | build-1790822008458856144 | 282.166 | 206.630 | 552.297 | 1041.095 | Published |

This was a cold output-path transition, not a steady-state warm comparison. However, publication alone required 552 seconds to synchronously copy the entire tree to replicated storage. The selected layout therefore keeps cache on NVMe and output on the release PVC. The trial completed before its layout was replaced.

### Same-filesystem output with NVMe cache and pruning fix

| Build ID | Prepare s | Build s | Promote s | Total s | Result |
|---|---:|---:|---:|---:|---|
| build-1790857082748854305 | 204.910 | 28.748 | 0.038 | 233.699 | Published |
| build-1790856766427285442 | 189.701 | 25.686 | 0.012 | 215.400 | Published |
| build-1790856466655144096 | 114.760 | 32.926 | 0.012 | 147.700 | Published |
| build-1790856215032386446 | 200.499 | 25.801 | 0.018 | 226.319 | Published |
| build-1790855867927831535 | 250.947 | 70.209 | 0.036 | 321.193 | Published |

Measured on image `sha-21cc258`. The engine build phase is now approximately 24–33 seconds in recent warm runs, versus 64–73 seconds in the earlier warm baseline. Promotion is milliseconds. Full job time remains dominated by preparing a fresh, isolated workspace: roughly 2–3 minutes in recent runs. Cluster load and cache residency vary; there is no claim that a four-second local benchmark predicts this production workload. Issue [#1421](https://github.com/WaylonWalker/markata-go/issues/1421) tracks remaining seed-copy work.

### Serving permission correction

The cross-filesystem trial also exposed an existing publisher defect: `MkdirTemp` creates a `0700` root and the copied release kept that mode. Subsequent seeded workspaces inherited it. Successful build records did not prove nginx could traverse the release; readiness and public serving returned 403/503. Live mitigation set affected release/workspace roots to `0755`. Engine issue [#1484](https://github.com/WaylonWalker/markata-go/issues/1484) adds permanent normalization for both rename and staged-copy publication, without changing child permissions. Its regression fails on the unchanged engine in all three tested paths. Validate readiness and public endpoints after the fixed-image rollout.

Permanent permission correction: [engine PR #1485](https://github.com/WaylonWalker/markata-go/pull/1485), [passing CI](https://github.com/WaylonWalker/markata-go/actions/runs/36861643461), and [published image](https://github.com/WaylonWalker/markata-go/actions/runs/36861549636), tag `sha-1222dae`. Local full tests and lint pass. Test fixtures verify root mode `0755` for rename, fallback copy, and direct staged copy while retaining a child file mode of `0640`.

A sample of 60 retained consecutive successful jobs on `sha-21cc258` had median prepare 181.556 s, engine build 27.491 s, promote 0.020 s, and total 208.805 s. Full-job range was 98.118–321.193 s. This documents both the engine improvement and the remaining preparation bottleneck. These successful publication records predate final serving-permission validation; see that correction above.
