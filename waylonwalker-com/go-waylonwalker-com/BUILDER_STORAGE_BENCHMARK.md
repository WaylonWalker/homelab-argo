# Builder Admin storage benchmark

Tracks #37.

## Baseline

The 2026-09-27 Builder Admin run took **809.56s** with these dominant phases:

- `publish_html`: 407.73s
- `publish_feeds`: 158.49s
- `fontpack`: 61.80s
- `diagnostics_artifact`: 37.38s
- estimated disk write wait: 300.49s
- estimated network wait: 1.74s

The deployment is pinned to `falcon3`. Source, site output, and the persistent Markata cache are hostPaths under `/mnt/main/walkershare/...`. The configured build concurrency is 16.

## Synthetic storage check

Run from a workstation with cluster access:

```bash
./waylonwalker-com/go-waylonwalker-com/benchmark-builder-storage.sh
```

The script runs inside the live Builder Admin container but only writes disposable benchmark directories. It compares `/data/site`, `/tmp`, and `/data/cache` when present and prints filesystem/mount identity first.

Useful overrides:

```bash
FILES=7000 BYTES_PER_FILE=32768 \
  ./waylonwalker-com/go-waylonwalker-com/benchmark-builder-storage.sh
```

Record the output in #37. A large `/tmp` versus `/data/site` difference is evidence for moving Builder Admin's transient `.build-work` to node-local storage once markata-go#1338 lands.

## Concurrency matrix

Do not change production concurrency based only on the synthetic test. After markata-go#1339 exposes cache and publish-I/O counters, run the same representative warm build at:

```text
MARKATA_GO_CONCURRENCY=1
MARKATA_GO_CONCURRENCY=2
MARKATA_GO_CONCURRENCY=4
MARKATA_GO_CONCURRENCY=8
MARKATA_GO_CONCURRENCY=16
```

For every run capture:

| concurrency | total | publish_html | publish_feeds | disk write | cache skipped/rebuilt | notes |
|---:|---:|---:|---:|---:|---:|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 4 | | | | | | |
| 8 | | | | | | |
| 16 | | | | | | |

Use the lowest repeatable total build time rather than assuming more concurrent writers are better for the `/mnt/main` small-file workload.

## Decision gates

1. Fix or explain the full-site cache miss in markata-go#1337 first. Rebuilding 3,500 pages can dominate any storage tuning.
2. If `/tmp` is materially faster than `/data/site`, validate node-local build work via markata-go#1338 while leaving durable releases on `/mnt/main`.
3. If `/data/cache` is materially slower than `/tmp`, evaluate moving the persistent Markata cache to node-local host storage with an explicit cold-cache recovery expectation.
4. Commit only the measured winning GitOps configuration.
