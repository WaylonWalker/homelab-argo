# Workload cleanup

This change removes obsolete runtime resources and retains their stored data.
Private rollback inventories are in `private/deprecation-2026-10-02`.

- Keep servers for `old.waylonwalker.com`, `goaccess.waylonwalker.com`, and `dev.waylonwalker.com`. Remove their legacy build and cache-cleaning CronJobs.
- Keep the current notes sites, their builders, and `searchgo.waylonwalker.com`. Remove the unused Go development web deployment and maintenance builder.
- Remove the orphan `image-updater-secret-*` Argo CD installation. Keep the current Argo CD installation, image updater, shared accounts, and Git credentials.
- Remove the stopped Markata documentation workload and `go.markata.dev` route. Keep its site volume.
- Remove PhotoPrism runtime definitions and its stale route. Keep its bound claim and photos.
- Remove the broken Copyparty route, `walkershare.wayl.one`. Keep Filebrowser, Syncthing, Samba, and their storage.
- Keep six Cloudflared replicas. Remove the broad toleration that permits scheduling onto nodes under disk pressure. Keep two old ReplicaSets and twenty terminal tunnel pods. A namespace-scoped cleanup job runs every thirty minutes; it checks pod ownership and uses UID deletion preconditions.

## Temporarily disabled applications

Postiz application and Redis deployments have zero replicas. Its database uses `cnpg.io/hibernation: "on"`. Claims and secrets remain intact.
To resume, remove that annotation and restore both deployments to one replica.

Perform Peoria has no Argo Application in this repository. Its production and development deployments are scaled to zero. Migration CronJobs and database backup schedules are suspended. Both databases have the hibernation annotation. A database must be healthy before the operator can finish hibernation.
To resume, remove the hibernation annotations, restore deployments to one replica, and restore each schedule's original suspension state from the private inventory. Migration jobs were already suspended before this change.

CloudNativePG hibernation retains claims. See the [operator documentation](https://cloudnative-pg.io/docs/1.25/declarative_hibernation/).
