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

## Review of the remaining preserved files

| Original work | Disposition |
| --- | --- |
| MinIO deployment conflict markers | Superseded by the repaired, pinned sidecar already on main; original patch retained privately |
| Old Prometheus manifest deletion | Completed; no repository or Argo source referenced the malformed legacy ingress |
| Traefik auth-cookie schema | Recovered; both schema groups include the field already used by Models middleware |
| Walkershare manifests | Reconciled with live Filebrowser, Samba, Syncthing and storage; credentials sealed; manual Argo adoption with no automatic pruning |
| Old Walkershare Copyparty ingress | Excluded from recovered manifests; live hostname still points to an absent service; owner decision needed for replacement or retirement |
| Cloudflare token helper and controller secret | Private proposal; there is no controller deployment or active namespace; do not create another tunnel from this unfinished experiment |
| Markata docs deployment | Private historical prototype; live deployment is scaled to zero and the build CronJob is suspended |
| Omada copy manifest | Historical commented-out migration; current deployment already uses the Longhorn claims |
| Jellyfin transcode Job | Private prototype; existing scripts/transcode.py provides inventory-driven transcoding; Job can publish partial output on failure and should not be deployed |
| CoreOS bootstrap and generated Ignition | Private host-rebase prototype with no repository references; generated configuration is not a cluster cleanup step |
| Thoughts and Longhorn sealed secrets | Retained privately; no proven need to replace current credentials |
| new-frigate.yaml and krayt.yaml | Retained privately; untracked configuration is not the live Frigate source of truth |
| status/create_status.py | Private login/status snippet, not a finished status provisioning workflow |
| listen.py | Private MQTT debugging snippet; no deployment references |
| requirements.txt | Empty placeholder; no dependency declaration to recover |
| media_inventory.db | Local runtime data; preserve privately rather than committing the database |
| Codex/OpenCode session exports | Private incident history; may contain credentials and host details |
| Local skill symlink | Machine-specific tooling; keep outside the published repository |

The reconciled Walkershare pod templates match live state in server dry-run.
Its shared hostPath PV still lacks node affinity; adding affinity to an existing
PV requires a planned storage change. Do not recreate the PV during adoption.
The proposed storage classes remain examples outside live Argo sources.

## Validation

- Every existing static site and the recipe-based generated site renders.
- Generated resources have the expected namespace and hostPath.
- Encryption helper uses the moved paths and merges both default and named keys.
- Benchmark rejects invalid limits, symlink escapes, and path traversal.
- Mock benchmark success and failure both remove their private test directory.
- Walkershare server dry-run and sealed-secret validation pass.
- Three reconciled Walkershare pod templates equal the running templates.

## Pending operational work

Recurring Frigate state backups and cache migration remain separate tasks.
Storage cleanup requires current ownership and backup/restore evidence for each
workload. Historical inventories alone do not establish safe deletion sets.

## Private preservation

The original files remain in `private/cleanup-2026-10-02/working-files.tar.gz`.
The original tracked patch and inventory are in the same directory. The named
stash is `preserved pre-cleanup work 2026-10-02`. Keep these until all remaining
work has been reviewed. Do not apply the whole stash over current manifests.
