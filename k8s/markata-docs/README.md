# Markata docs: homelab builder and public site

The documentation uses the same **separated builder / public Nginx site** pattern as waylonwalker.com, but its generator is `scripts/build_docs_site.py`, not the Markata CLI. Its builder is therefore purpose-built, not the Markata Helm builder-admin command.

- **Public (primary):** https://markata.dev
- **Public (existing alias):** https://markata.waylonwalker.com
- **Authenticated builder:** https://markata-builder.waylonwalker.com
- **Legacy nested alias:** `build.markata.waylonwalker.com` remains routed, but Cloudflare’s current `*.waylonwalker.com` edge certificate does not cover this two-level hostname. The builder also rejects POST actions from this host because its same-origin check accepts only the primary builder URL.
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

## Apex hostname: markata.dev

The separate `apex-ingress.yaml` routes **markata.dev** to the same
`markata-docs` Service and shared published release as
`markata.waylonwalker.com`. It issues its **own** cert-manager
`letsencrypt-dns` certificate (`markata-dev-tls`), so the existing
WaylonWalker-domain certificate is unchanged. No second builder, PVC, or Nginx
Deployment is created.

The zone `markata.dev` is already listed in
`k8s/external-dns/zone-ids.yaml`, and the falcon Cloudflare tunnel has an
unmatched-host catch-all route to Traefik. ExternalDNS runs in **create-only**
mode and manages proxied Cloudflare CNAMEs to
`1bdd7ce3-6476-43bc-a9e0-6e30167617e5.cfargotunnel.com`.

**The apex is special.** Before claiming the new hostname is live, inspect
the existing Cloudflare DNS records for the exact name `markata.dev`
(including A, AAAA, CNAME) and confirm the zone is active. Cloudflare can
flatten a CNAME at the root, but ExternalDNS may not create it if any record
already exists; create-only deliberately **does not overwrite** it. If an
existing apex DNS record points somewhere else, do not replace it
automatically: inspect its current traffic and explicitly migrate it to the
falcon tunnel. This repository change only adds the Ingress and requests DNS.

```bash
kubectl -n markata-docs get ingress markata-docs markata-docs-apex
kubectl -n markata-docs get certificate,certificaterequest
kubectl -n markata-docs get secret markata-dev-tls
kubectl -n external-dns logs deployment/external-dns --since=15m
dig +short markata.dev
curl -fsSI https://markata.dev/
curl -fsSI https://markata.dev/docs/quickstart/
```

Verify Cloudflare's apex CNAME target or flattened IP response resolves through
the **falcon** tunnel and its catch-all route. A valid certificate and a
successful homepage request prove the final cutover; GitHub manifest checks
alone do not.
