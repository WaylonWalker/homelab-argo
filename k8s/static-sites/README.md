# Argo-managed static sites

Argo CD discovers each site from `sites/*/site-config.yaml` and creates one
Application for each config. Render a site with:

```bash
kubectl kustomize k8s/static-sites/sites/test.waylonwalker.com
```

The hostPath content stays outside this repository. The manifests only mount
the existing hostPath into nginx, so the site content remains managed by the
host and its existing publishing workflow.

The canary intentionally excludes `go.waylonwalker.com`, `waylonwalker.com`,
and `recipes.waylonwalker.com`; those sites are already or specially managed.
