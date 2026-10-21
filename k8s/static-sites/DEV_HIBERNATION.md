# Hibernating static development sites

This opt-in GitOps change pauses the **11 existing `*-dev` static Nginx readers** on Falcon3. Every selected site's `kustomization.yaml` has:

```yaml
replicas:
  - name: web
    count: 0
```

The existing ApplicationSet creates one Argo CD Application per site, with automated sync and self-healing. Therefore a live `kubectl scale ... --replicas=0` is temporary and not the durable control. The per-site Kustomize replica override is the desired state, so Argo will keep it at zero after this PR **merges**.

## Scope and behavior

- This PR only affects `web` Deployments of the eleven stateless static-site development variants: `3d-dev.waylonwalker.com`, `app-dev.waylonwalker.com`, `apps-dev.waylonwalker.com`, `caps-dev.waylonwalker.com`, `convert-dev.waylonwalker.com`, `emboss-dev.waylonwalker.com`, `md-dev.waylonwalker.com`, `solidstack-dev.waylonwalker.com`, `stl-text-dev.waylonwalker.com`, `strip-dev.waylonwalker.com`, `voice-reverse-dev.waylonwalker.com`.
- Their production counterparts are **unchanged**. Builder Admin, source checkouts, `models-dev`, `shots-dev`, and `go-waylonwalker-com-dev` remain unchanged.
- The dev websites become **unavailable** while paused. Ingress and Services remain present, and requests will usually get 503 (no ready endpoints). Do not treat this as a maintenance page.
- All original Walkershare `hostPath` folders and their per-site PVs and PVCs are retained. Do not manually delete content, PVs, PVCs, or directories to implement a pause.
- Static Nginx pods have no explicit CPU requests in `k8s/static-sites/base/deployment.yaml`. Hibernating these pods recovers **11 pod slots** and running-process overhead, but it does not guarantee enough allocatable CPU requests for the blocked NVMe A/B benchmark.

## Resume just one site

1. Edit that site's `k8s/static-sites/sites/<domain>/kustomization.yaml`: set `replicas[0].count: 1` or remove this override (the base Deployment defaults to 1).
2. Commit and merge the change to `main`. Let its ApplicationSet-managed Argo Application sync; do not rely on a one-off `kubectl scale`.
3. Confirm with `kubectl -n <namespace> get deploy web,pods,pvc` (or list these separately), wait for readiness, and smoke-test the HTTPS hostname.

For a temporary session without a Git commit, Argo self-healing may reverse a manual scale change; edit the desired state instead.

## Validation and rollback

Run `just static-sites-validate` before merge; `kubectl kustomize k8s/static-sites/sites/3d-dev.waylonwalker.com` should render `Deployment/web` with `spec.replicas: 0`. For each selected site, verify its Argo Application is Synced/Healthy and its Deployment shows `0/0`. Check the hostPath PVs/PVCs remain bound and unchanged.

Rollback: revert this commit, or restore `count: 1` for whichever sites are needed. No file migration or storage deletion is part of hibernation.

**Operational gate:** do not merge this draft until the owner accepts temporary dev-site unavailability. Production should remain untouched.
