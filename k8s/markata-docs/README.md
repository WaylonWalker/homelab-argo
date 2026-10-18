# Markata docs: homelab builder and public site

The documentation uses the same **separated builder / public Nginx site** pattern as waylonwalker.com, but its generator is `scripts/build_docs_site.py`, not the Markata CLI. Its builder is therefore purpose-built, not the Markata Helm builder-admin command.

- **Public:** https://markata.waylonwalker.com
- **Authenticated builder:** https://build.markata.waylonwalker.com
- **Source:** https://github.com/WaylonWalker/markata `main` branch, watched every 45 seconds
- **Image:** `ghcr.io/waylonwalker/markata-docs-builder:0.0.24` (pin the published version)
- **Persistent releases:** `markata-docs-site` Longhorn RWO 3 GiB (builder and both public replicas pinned to `falcon3`)
- **Temp source:** builder `emptyDir` for the shallow Git checkout
- **Retention:** seven versioned releases plus persisted status/history
- **Publishing:** Python Markdown renderer in the build pod, atomic release directory + `current` symlink; Nginx reads `current` without a redeploy
- **Admin:** HLab ForwardAuth with stripped identity headers and ingress NetworkPolicy restricted to Traefik. App also verifies trusted CIDR and identity header, and validates Origin for POST.

## First rollout

1. Verify upstream [docs website workflow](https://github.com/WaylonWalker/markata/actions/workflows/docs-site.yml) successfully pushed the pinned builder image and the seed site image can be pulled from GHCR.
2. Merge Argo PR. Argo CD deploys PVC, builder pod, Nginx config, and ingress. The builder seeds the existing site image if the volume is empty, then shallow clones main and builds from source.
3. Confirm Longhorn claim is bound, `builder` has run, `current` is a valid symlink, Nginx replicas are ready.
4. Verify ExternalDNS and TLS for both hosts. Check that unauthenticated requests to the builder do not expose the admin UI.
5. Visit the protected builder UI and use Build now; edit docs on main to observe a rebuild within about one minute.

## Commands

```bash
kubectl kustomize k8s/markata-docs/
kubectl -n argocd get application markata-docs
kubectl -n markata-docs get pvc,pods,svc,ingress
kubectl -n markata-docs logs deployment/markata-docs-builder -c builder --tail=100
kubectl -n markata-docs rollout status deployment/markata-docs
curl -fsSI https://markata.waylonwalker.com/
curl -fsSI https://markata.waylonwalker.com/docs/quickstart/
```

Rollback is available from the authenticated builder UI and switches the `current` symlink atomically. A further source update resumes publishing normally.

**Do not run the historical `markata/kubernetes/markata-go-docs.yaml` CronJob.** It builds the wrong site and competes with this release store. GHCR docs images remain available for the first seed and fallback, but the running site is served from the Longhorn PVC rather than the baked Nginx image.

Watch release storage growth; the configured 3Gi is intentionally small for text-heavy docs.
