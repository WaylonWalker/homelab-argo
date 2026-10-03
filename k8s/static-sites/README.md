# Argo-managed static sites

Argo CD discovers each site from `sites/*/site-config.yaml` and creates one
Application for each config. Render a site with:

```bash
kubectl kustomize k8s/static-sites/sites/test.waylonwalker.com
```

Create a production and development site with Copier:

```bash
just new-static-site example
```

Install `copier` and `fzf` first. The recipe checks namespace and directory
availability, asks for a domain, and creates both `example` and `example-dev`.
It writes manifests locally; review them before committing.
Run `just static-sites-validate` to render every site.

The Copier template lives in `templates/static-site`. To generate a site
without the interactive picker:

```bash
copier copy templates/static-site k8s/static-sites/sites/example.waylonwalker.com \
  --data site=example --data namespace=example \
  --data host=example.waylonwalker.com \
  --data webroot_path=/mnt/main/walkershare/waylon/sites/example.waylonwalker.com \
  --defaults
```

ExternalDNS creates DNS records. A Cloudflare Tunnel route must also accept
the hostname. Check that route before expecting the new site to be reachable.

The hostPath content stays outside this repository. The manifests only mount
the existing hostPath into nginx, so the site content remains managed by the
host and its existing publishing workflow.

The canary intentionally excludes `go.waylonwalker.com`, `waylonwalker.com`,
and `recipes.waylonwalker.com`; those sites are already or specially managed.

`recipes.waylonwalker.com` is adopted separately at `k8s/recipes-waylonwalker-com`
because it has a builder sidecar. It is not under `sites/`, so the ApplicationSet
does not discover it.
