# Recovery of preserved repository work — 2026-10-02

The previous dirty checkout was archived privately and saved in a named Git
stash before recovery. Session exports and local databases remain private.
This report records which work was recovered and which proposals need a
separate operational decision.

## Later storage evidence

The September 20 and 21 inventories are historical snapshots. Their disk
capacity figures and failure statuses are not current operating instructions.
The September 20 architecture document is a proposal, not deployed policy.

Later evidence from the recovery sessions and live checks:

- The Longhorn backup target repair and disposable backup/restore gate passed
  on September 21. The target remains available in the October 2 live check.
- Frigate retention was changed to 14 days for continuous/motion footage.
  Alert/detection retention remains 120 days. All eight cameras record.
- Frigate now uses a pinned image, a 4 GiB memory request, and a 6 GiB limit.
  Its durability exporter is live and all 19 Prometheus rules evaluate.
- All five Longhorn disks currently permit scheduling, including Falcon2 vault.
  This differs from the old proposal to keep vault scheduling disabled.
- Daily and weekly Longhorn jobs still select the default group. The proposed
  critical/HA StorageClasses are kept under `docs/examples/`, outside Argo.
- The production site moved to fast Longhorn storage. The September 28 matrix
  records measurements under the placement and load present at that time.
- The old Frigate cache contained unprocessed footage. Preserve its quarantine
  and decide historical recovery needs before retiring the loop image.

## Recovered work

- Dated storage inventories and the historical architecture proposal.
- Production storage measurements and the disposable-filesystem benchmark.
- Copier static-site templates required by the existing creation recipe.
- Clipboard encryption helper with current manifest paths and merge behavior
  that preserves other keys in an existing sealed secret.

## Pending operational work

Recurring Frigate state backups and cache migration remain separate tasks.
Storage cleanup requires current ownership and backup/restore evidence for each
workload. Historical inventories alone do not establish safe deletion sets.

## Private preservation

The original files remain in `private/cleanup-2026-10-02/working-files.tar.gz`.
The original tracked patch and inventory are in the same directory. The named
stash is `preserved pre-cleanup work 2026-10-02`. Keep these until all remaining
work has been reviewed. Do not apply the whole stash over current manifests.
