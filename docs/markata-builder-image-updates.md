# Markata builder image updates (Edge canary)

Markata's update channel is an Argo CD Image Updater policy, **not** a self-modifying
binary and not a floating Markata Helm chart. Sites not listed in an ImageUpdater
CR remain pinned. The production `waylonwalker-com-prod` Application is NOT enabled
by this change.

## Rollout dependency

1. Merge [Markata publication CI gate](https://github.com/WaylonWalker/markata/pull/1698)
   and confirm the Docker workflow for a new `main` SHA has passed and published
   `ghcr.io/waylonwalker/markata-go-builder:latest`. CI checks must complete
   before the mutable tag is advanced.
2. Inspect cluster state before syncing the controller Application:
   `kubectl -n argocd get deployments | grep image-updater` and
   `kubectl get crd imageupdaters.argocd-image-updater.argoproj.io`.
   This repository previously contained a disabled controller Application, but an
   existing manually installed updater may still be running. **Do not install a
   second controller**; reconcile/adopt the existing installation first.
3. Ensure Image Updater has Git write access to
   `https://github.com/WaylonWalker/homelab-argo.git`. This configuration uses
   `method: git`, which reuses Argo CD repository credentials. The existing
   `git-creds` SealedSecret contains a `token` field; it is NOT automatically a
   suitable Image Updater Git credential (`username` + `password` are required
   for the `git:secret:` form). Do not assume the secret enables write-back.
4. Review the `go-waylonwalker-com` Helm values migration by rendering both
   versions of the chart, using the exact old/new sources (this repository
   cannot run a live Argo CD diff by itself). The chart still tracks `main`
   and only the values source moves to this repository.
5. Sync `argocd-image-updater` controller and
   `argo-image-updater-secret` applications. Inspect CR health and controller
   logs. The ImageUpdater resource targets **only** `go-waylonwalker-com`.
6. Verify Image Updater writes a change under
   `argo-apps/values/go-waylonwalker-com.yaml`, Argo syncs the new digest,
   Builder Admin starts with the new embedded commit, and the
   `startup-revision` full build succeeds before widening the rollout.
   Run `kubectl -n argocd get imageupdaters` and
   `kubectl -n argocd logs deploy/argocd-image-updater --tail=200`.
   Inspect the site, builder history, and search functionality.

## What is updated

- `go-waylonwalker-com`: the Helm key `build.builderImage.tag`, controlling
  the Builder Admin binary and scheduled build image; digest strategy follows
  `ghcr.io/waylonwalker/markata-go-builder:latest` for linux/amd64.
- `build.fetchImage.tag` and `search.image.tag` remain pinned initially,
  avoiding changes to source-fetch and search behavior during the canary.
  Evaluate search/builder compatibility before opting search into the channel.
- The Markata chart revision is unchanged. Image Updater cannot update the
  `targetRevision` of a pinned Helm chart source.
- The normal production `waylonwalker-com-prod` image remains pinned.
  Only opt in after evaluating the canary, update overlap, disk space,
  credentials, and rollback.

## Stable channel for other sites (opt-in only)

Give another site a separate ImageUpdater `applicationRef`, separate values
file and Git write-back target. Use `semver` with `allowTags` restricting
to final release versions:

```yaml
images:
  - alias: builder
    imageName: ghcr.io/waylonwalker/markata-go-builder
    commonUpdateSettings:
      updateStrategy: semver
      allowTags: 'regexp:^[0-9]+\.[0-9]+\.[0-9]+$'
    manifestTargets:
      helm:
        name: build.builderImage.name
        tag: build.builderImage.tag
```

No release candidates or `latest` are included in this policy. Leave a site
out of all `ImageUpdater` resources for `pinned`.

## Safety and rollback

This Edge canary is deliberately experimental. Image Updater **does not**
coordinate with Builder Admin to wait for an active build to finish. A Kubernetes
rollout can interrupt a build, even though Markata's atomic publication keeps
the last successfully published release live. Production rollout requires a
verified build-drain/retry policy (or maintenance window) first.

To stop updates, remove the canary ImageUpdater resource (or its application
reference) and sync. To roll back, revert the updater's commit changing
`build.builderImage.tag` in this values file to the previous SHA tag,
then sync Argo CD. Do not rely on reverting the tag while ImageUpdater remains
active, since it could immediately reapply the newest digest.
