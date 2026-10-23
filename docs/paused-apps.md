# Paused applications

This page records workloads that currently have zero replicas. A zero replica count is a pause only when the active GitOps source also declares zero. A live `kubectl scale` alone can be reversed by the next sync.

## Paused workloads

| Workload | Current source or owner | Data and resume notes |
| --- | --- | --- |
| 11 static development sites: `3d-dev`, `app-dev`, `apps-dev`, `caps-dev`, `convert-dev`, `emboss-dev`, `md-dev`, `solidstack-dev`, `stl-text-dev`, `strip-dev`, `voice-reverse-dev` | Argo CD, opt-in site Kustomizations | Declared at zero; site files, PVs, PVCs, and Ingresses remain. Restore the site's replica count when needed. |
| `aylawalker/admin`, `aylawalker/code-server` | Argo CD `aylawalker` application | Both are at zero. Restore their declared replica count to resume. |
| `dozzle/dozzle` | Argo CD `dozzle` application | At zero. Restore its declared replica count to resume. |
| `forgejo/forgejo-runner` | Argo CD `forgejo` application | At zero; Forgejo server remains active. Restore the runner replica count to resume jobs. |
| `installer/installer` | Argo CD `installer` application | At zero, with no service endpoints. Restore its declared replica count to resume. |
| `kube-system/headlamp` | Argo CD `headlamp` application | At zero. The application remains managed by Argo CD. |
| `posse-party/posse-party` and `posse-party/posse-party-db` | Argo CD `posse-party` application | App Deployment is zero; CNPG database is hibernated. PVC is retained. Remove the hibernation annotation and set `enablePDB: true` (or omit it) before resuming the database. |
| `postiz/postiz`, `postiz/postiz-redis`, and `postiz/postiz-db` | Argo CD `postiz` application | Both Deployments are zero; CNPG database is hibernated. Four PVCs remain Bound. Remove the hibernation annotation and set `enablePDB: true` (or omit it) before resuming the database. |
| `magnet-smp/magnet-smp` | Argo CD `kraft` application after this change | Deployment remains at zero. Season 2 PVC is retained and protected from Argo pruning; the separate season 3 PVC remains outside this manifest. Set replicas to one to resume the server. |

## Live zero replicas without confirmed GitOps ownership

These Deployments were observed at zero, but they were not present in the matching Argo application's resource inventory at the time of review:

- `go-waylonwalker-com-dev/search`
- `performpeoria-dev/theater-studio` and `performpeoria-prod/theater-studio`
- `solid-stack-dev/web` (distinct from `solidstack-dev/web`, which is in the static-site inventory above)
- `waylonwalker-com/web`

The local PerformPeoria source checkout at `/home/waylon/git/performpeoria` is not initialized with Git history, and its dev and prod overlays declare one application replica. The live zero count is therefore not represented by that source. Confirm the authoritative repo and desired state before relying on these pauses or syncing those overlays.

The pause sources for `go-waylonwalker-com-dev/search`, `solid-stack-dev/web`, and `waylonwalker-com/web` also need confirmation before these can be described as durable GitOps pauses.

## Resuming a hibernated CNPG database

1. Remove `cnpg.io/hibernation: "on"` from the `Cluster` metadata annotations.
2. Set `spec.enablePDB: true`, or omit the field to use the CNPG default.
3. Restore the app Deployment replica count in Git.
4. Sync the owning Argo application and confirm the database and app become ready.

Do not delete PVCs as part of a pause or resume. Paused databases do not need a primary PDB while they have no pods; the CNPG `enablePDB: false` setting suppresses the generated PDB. This avoids an `InsufficientPods` PDB warning while preserving the database storage.

## Review scope

The cluster inventory found five PDBs with zero expected pods and `InsufficientPods`: Magnet SMP, two PerformPeoria databases, Posse Party, and Postiz. This change addresses the Argo-managed Magnet SMP, Posse Party, and Postiz resources. PerformPeoria's CNPG resources are managed outside this repository and remain unmodified. PDBs for active workloads were left unchanged.
