# Markata documentation, served by the homelab

The public documentation is served at <https://markata.waylonwalker.com>.

- **Source**: `WaylonWalker/markata` repository, `docs/` and `docs-site/`.
- **Build**: [Documentation website](https://github.com/WaylonWalker/markata/actions/workflows/docs-site.yml) GitHub Actions publishes `ghcr.io/waylonwalker/markata-docs:0.0.<run-number>` to GHCR after validation.
- **Delivery**: Argo CD Application `markata-docs` in `argo-apps/apps/markata-docs.yaml` deploys immutable versioned Nginx images from this folder.
- **Networking**: Traefik Ingress, cert-manager `letsencrypt-dns`, ExternalDNS, and the homelab Cloudflare tunnel.
- **Storage**: none; generated HTML is embedded in the image. No Longhorn volume or builder required.

## Validate

```bash
kubectl kustomize k8s/markata-docs/
kubectl -n argocd get application markata-docs
kubectl -n markata-docs rollout status deployment/markata-docs
curl -fsSI https://markata.waylonwalker.com/
curl -fsSI https://markata.waylonwalker.com/docs/quickstart/
```

After a new docs image is published, update the version in `deployment.yaml`. Renovate's Kubernetes manager can propose new versioned GHCR tags; `automerge` is currently disabled in the repository, so review and merge the update PR to roll out newer documentation. A published GHCR image alone **does not update Argo or restart pods**.

GitHub Pages is not used. Don't deploy the historical `markata/kubernetes/markata-go-docs.yaml` — it is a separate obsolete setup.

### First deployment requirements

1. Confirm the GitHub Actions [docs image publish](https://github.com/WaylonWalker/markata/actions/workflows/docs-site.yml) succeeded for the tag in the Deployment.
2. Ensure the GHCR `markata-docs` package allows public pulls; otherwise add a pull secret to this namespace and Deployment.
3. Argo CD syncs the application when this repository PR merges.
4. Check ExternalDNS record creation, the Cloudflare tunnel route, and cert-manager certificate readiness. These depend on cluster runtime access; GitHub checks cannot prove public reachability.
