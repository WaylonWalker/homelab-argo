# Builder publication performance, 2026-10-03

The production builder copied its entire output tree before every build. The last
20 successful jobs had median preparation of 169.465 seconds and total time of
205.878 seconds. Single-post jobs spent 180–215 seconds preparing, although their
engine builds took only 39–40 seconds.

## Changes

The fix belongs in markata-go. Argo selects the published builder image; deployment
values alone cannot remove the unconditional output copy.

- [PR #1516](https://github.com/WaylonWalker/markata-go/pull/1516) retains an independent mutable workspace and stages immutable releases using hard links for unchanged files.
- [PR #1517](https://github.com/WaylonWalker/markata-go/pull/1517) bounds publication concurrency to eight workers.
- [PR #1518](https://github.com/WaylonWalker/markata-go/pull/1518) adds a private SHA-256 publication manifest to avoid reading unchanged output.

All PRs passed local repository tests, lint, builder-admin race tests, and GitHub
Linux, macOS, and Windows checks before merge. The final image is `sha-9c80f15`,
from commit `9c80f15c9019ddfb40de0cbde01fc6229df563d9`. Its registry digest is
`sha256:e6e5c120304457a966ead8ea6894e3fe2325574f6987ab622ad63e3db70cadce`.

Production keeps the workspace on the release PVC and the build cache on local
NVMe. Full builds, encryption, reader updates, rollback history, and per-file
copy synchronization remain enabled. The deployment runs one builder leader.

The private manifest binds a checksum, workspace path, and baseline release.
Linux source digest reuse requires matching device, inode, size, mode, modification
time, and change time. Timestamps must precede the cache commit by more than one
second. A backwards clock disables reuse. Other platforms hash source content.
Corrupt, missing, or mismatched records fall back to content hashing. Immutable
baseline file metadata validates cached release digests; hard-link change times
are excluded because adding or pruning links changes them. Retained releases must
remain immutable. Manifest write failure does not prevent publication.

## Earlier measurements

Workspace retention reduced preparation to milliseconds. It did not initially
improve total time: byte comparison read about 6.3 GB from replicated storage.
The parallel publisher's no-op job `build-1791051846328130918` took 360.240 seconds:
0.031 seconds preparing, 39.012 seconds building, and 321.196 seconds publishing.
It linked 34,031 files but copied 228,370,805 bytes across 13 changed files.
This regression motivated the digest cache; concurrency alone was insufficient.

Before the final rollout, a full historical SHA-256 snapshot verification passed
for release `20261003T175617Z-waylonwalker-com-prod-notes-builder-admin-6dbbdcfd5d-n76p8`:
54,817 entries and 3,397,439,560 bytes unchanged, with 33,543 files linked to current
and zero files shared between current and the mutable workspace.

## Final production verification

All jobs used full builds. No fast-build flags were enabled. Times are seconds
from the Builder Admin API. Background pruning runs separately and is excluded
from time to live publication.

| Job | Prepare | Engine | Publish | Total to live | Background prune |
| --- | ---: | ---: | ---: | ---: | ---: |
| Manifest prime | 0.030 | 46.854 | 400.085 | 446.970 | 83.945 |
| Warm unchanged | 0.028 | 36.103 | 7.552 | 43.684 | 91.723 |
| One-post edit | 0.075 | 49.841 | 20.135 | 70.053 | 82.256 |
| Restore original | 0.007 | 45.003 | 17.037 | 62.049 | 64.581 |

Job IDs, in table order:

- `build-1791054467306830397`
- `build-1791055191154062859`
- `build-1791055280190122174`
- `build-1791055397226271965`

Warm publication linked 34,031 files and copied 228,370,805 bytes across 13 files.
It reused 30,848 source digests and 34,044 release digests, reading 276,140,586
content bytes. Publication fell from 321.196 seconds in the earlier no-op test to
7.552 seconds, about 42.5 times faster. Total time fell from 360.240 to 43.684
seconds, about 8.2 times faster. Compared with the original 20-job median of
205.878 seconds, the warm result is about 4.7 times faster.

These are operational measurements on the live node, with varying background
load, rather than a controlled benchmark. The fresh snapshot scan completed before
the warm measurement. The file counts and actual read-byte reduction explain why
the result improves. Initial manifest priming remains expensive and must not be
reported as a warm build.

The single-post test appended a temporary HTML comment to `pages/blog/d3-day5.md`.
The engine invalidated one post and zero dependents, rendered one template,
skipped 413 feeds, and rebuilt seven feeds. The marker appeared in the published
`/d3-day-5/` page. Publication linked 34,017 files and copied 326,198,470 bytes across
27 files. Its 70.053-second total is about 3.1–3.6 times faster than the original
220.094- and 254.713-second single-post jobs.

The source was restored byte for byte. Its SHA-256 before and after restoration is
`526c7cd680f8d6e491203e5d9d9d2db5f79722f3b2edf8af38597c325c5be1a5`.
The restoration release removed the marker. Git status contains only the existing
untracked `.markata-notes-source-ready` marker.

Both running binaries report commit `9c80f15c9019ddfb40de0cbde01fc6229df563d9`.
Argo reports Synced and Healthy. Production has one ready builder pod and one
ready search pod. Public requests to `/`, `/reader/`, `/blogroll/`, `/d3-day-5/`,
and `/api/search?q=python` return HTTP 200. Reader and blogroll CSS and JavaScript
assets also return HTTP 200. The temporary comment is absent from public HTML.

The prime release snapshot records 54,817 entries and 3,396,464,787 bytes.
After all three verification builds, the entire prime release still matches its
SHA-256 snapshot, including file sizes, permissions, directories, and symlink
targets. It shares 34,017 regular-file inodes with current. Every current regular
file was checked against the mutable workspace: zero shared inodes. The private
manifest has mode 0600. The successful-workspace marker matches the live release.

Structured verification evidence is available in
[BUILDER_DELTA_PUBLICATION_2026-10-03.json](BUILDER_DELTA_PUBLICATION_2026-10-03.json).

## Remaining costs

The warm engine still takes 36 seconds on this node. CSS minification/cache work
used 13 seconds in the measured warm build. Single-post feed generation used
19.6 seconds to rebuild seven feeds. Diagnostics rewrite an approximately 227 MB
artifact each build. This explains most copied bytes even when site content does
not change. Background retention cleanup still takes 65–92 seconds and can
compete for storage, although it does not block switching the live release.
These remain separate optimization opportunities.
