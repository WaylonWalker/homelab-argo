# Argo CD Upgrade Plan: 7.8.28 to 9.5.21

Current state:
- Chart: `7.8.28`
- App version: `v2.14.11`
- Target chart: `9.5.21`
- Target app version: `v3.4.3`

Repo-specific context:
- Argo CD is self-managed by `argo-apps/core-apps/argocd.yaml`.
- The Argo CD app currently has automated `prune` and `selfHeal` enabled.
- The current Argo CD app does not set `ServerSideApply=true`.
- The repo contains several `CronJob`-based apps whose health behavior may change on Argo CD `3.2+`.
- I did not find active `ApplicationSet` manifests, Dex/OIDC config, `redis-ha`, or CMP plugin config in the active Argo CD manifest.

## Step 1: Baseline the current install

Status: Complete (2026-06-11)

Notes:
- Cluster version confirmed: `v1.35.5+k3s1`.
- Live self-managed `argocd` application is `Synced` and `Healthy` on chart `7.8.28` / app `v2.14.11`.
- Argo CD pods in `argocd` are ready.
- Live config review found no unknown OIDC/Dex or manual workload patches.
- Known live-only settings in-cluster: repository secret `repo-3842381109` and sealed `git-creds` secret used outside the Argo CD chart values.

Instructions:

1. Confirm the cluster version is `>=1.25`.
2. Capture the current Argo CD resources and state:
   - `kubectl get application argocd -n argocd -o yaml`
   - `kubectl get cm -n argocd`
   - `kubectl get applications -A`
   - `kubectl get appprojects -A`
   - `kubectl get pods -n argocd`
3. Compare live Argo CD config against Git and identify any live-only settings:
   - RBAC config
   - repo credentials/repository config
   - OIDC/Dex config
   - resource tracking config
   - any manual patches on Argo CD workloads

Success criteria:

1. The cluster version is known.
2. You have a snapshot of the current Argo CD state.
3. There are no unknown live-only settings that would be overwritten during upgrade.

Do not continue until all success criteria are met.

## Step 2: Add self-upgrade safety before crossing into Argo CD 3.3+

Status: Complete (2026-06-11)

Notes:
- Added `ServerSideApply=true` to the self-managed `argocd` Application.
- After enabling SSA, Argo CD `v2.14.11` hit a compare error on Kubernetes `1.35` for `Deployment.status.terminatingReplicas`.
- Recovered the app by setting `resource.compareoptions: ignoreResourceStatusField: all`, then synced successfully.
- Final Step 2 state: `argocd` is `Synced` and `Healthy`, and all Argo CD pods are ready.

Why this matters:

- Argo CD `3.3+` requires server-side apply for safe self-management because the `ApplicationSet` CRD exceeds client-side apply size limits.
- This repo self-manages Argo CD, so this is the first required change.

Instructions:

1. Update `argo-apps/core-apps/argocd.yaml`.
2. Under `spec.syncPolicy.syncOptions`, add:

```yaml
- ServerSideApply=true
```

3. Do not change `targetRevision` yet.
4. Sync this change on the current Argo CD version.

Success criteria:

1. `argo-apps/core-apps/argocd.yaml` contains `ServerSideApply=true`.
2. The Argo CD app syncs successfully on the current version.
3. The `argocd` application is `Synced` and `Healthy`.
4. `kubectl get pods -n argocd` shows all Argo CD pods ready.

Do not continue until all success criteria are met.

## Step 3: Make resource tracking behavior explicit

Status: Complete (2026-06-11)

Notes:
- Added `configs.cm.application.resourceTrackingMethod: label` in Git.
- Committed the compare-options stabilization alongside this change so the SSA recovery remains declarative.
- Verified the self-managed `argocd` app returned to `Synced` and `Healthy` on chart `7.8.28` after sync.

Why this matters:

- Argo CD `3.0+` changes the default tracking method from labels to annotations.
- This repo uses automated prune/self-heal, so the transition should be deliberate.

Recommended approach:

- Temporarily preserve current behavior first, then switch later after the main upgrade is stable.

Instructions:

1. Update the embedded Helm values in `argo-apps/core-apps/argocd.yaml`.
2. Add an explicit setting under `configs.cm`:

```yaml
configs:
  cm:
    application.resourceTrackingMethod: label
```

3. Keep all other behavior unchanged.
4. Sync the app.

Success criteria:

1. The resource tracking method is explicit in Git.
2. The Argo CD app remains `Synced` and `Healthy` after sync.
3. Managed apps behave the same as before this change.

Do not continue until all success criteria are met.

## Step 4: Upgrade through checkpoints instead of one jump

Current checkpoint status (2026-06-11):
- `7.9.1` is applied in Git and the Argo CD pods rolled successfully.
- UI access and CLI login still work at this checkpoint.
- Blocked on Argo CD `v2.14.11` self-sync behavior with `ServerSideApply=true`: the `argocd-redis-secret-init` PreSync hook completes in Kubernetes but remains `Running` in Argo CD status, leaving the `argocd` app `OutOfSync`.
- This matches a known Argo CD `2.14.x` + SSA hook bug pattern; the checkpoint is not complete yet.
- Per operator instruction, continued forward to `8.0.17` instead of waiting indefinitely on the incomplete `7.9.1` gate.
- `8.0.17` completed successfully after terminating the stale `7.9.1` operation and re-running sync.
- Verified at `8.0.17`: chart `8.0.17`, app version `v3.0.6`, `argocd` app `Synced` and `Healthy`, UI access working, CLI login working, no CRD sync errors.
- `8.6.4` initially stalled on the same pre-sync hook family, this time with the `argocd-redis-secret-init` Job reported as `Pending deletion` even though the Job object was already gone from Kubernetes.
- `8.6.4` completed successfully after terminating the stale operation and re-running sync.
- Verified at `8.6.4`: chart `8.6.4`, app version `v3.1.8`, `argocd` app `Synced` and `Healthy`, UI access working, CLI login working, no CRD sync errors.
- `9.0.6` synced successfully on the first retry cycle after the parent app applied the new target revision.
- Verified at `9.0.6`: chart `9.0.6`, app version `v3.1.9`, `argocd` app `Synced` and `Healthy`, UI access working, CLI login working, no CRD sync errors.

Why this matters:

- The chart recommends a multi-step path.
- The biggest functional boundaries are at major-version transitions.

Recommended checkpoints:

1. `7.9.1`
2. `8.0.17`
3. `8.6.4`
4. `9.0.6`
5. `9.5.21`

Instructions for each checkpoint:

1. Update only `spec.source.targetRevision` in `argo-apps/core-apps/argocd.yaml`.
2. Sync the Argo CD app.
3. Wait for rollout completion.
4. Verify health before moving on.

Success criteria at each checkpoint:

1. The `argocd` app is `Synced` and `Healthy`.
2. `kubectl get pods -n argocd` shows all Argo CD pods ready.
3. There are no CRD sync errors.
4. UI access still works.
5. CLI login still works.

Do not move to the next checkpoint until all success criteria are met.

## Step 5: Validate core Argo CD workflows after each checkpoint

Instructions:

1. Test UI access through ingress.
2. Test CLI login.
3. Confirm one normal app can sync successfully.
4. Confirm automated sync still works.
5. Confirm prune still works on a safe test case.
6. Confirm self-heal still works on a safe test case.
7. Confirm repo rendering still works for:
   - plain YAML apps
   - Helm apps

Success criteria:

1. UI access works.
2. CLI login works.
3. A normal app syncs cleanly.
4. Automated sync, prune, and self-heal still work.
5. Both plain YAML and Helm-backed apps still render correctly.

Do not continue until all success criteria are met.

## Step 6: Watch for CronJob health changes on Argo CD 3.2+

Why this matters:

- Argo CD `3.2+` adds built-in CronJob health logic.
- Apps with failed or stale CronJobs may begin showing `Degraded`.

Known repo examples:

- `waylonwalker-com/waylonwalker-com.yaml`
- `reader/reader.yaml`
- other app manifests containing `kind: CronJob`

Instructions:

1. After reaching Argo CD `3.2+`, review apps that contain CronJobs.
2. Check whether any app becomes `Degraded` because of CronJob health.
3. Decide per CronJob whether that health should affect the parent app.
4. For CronJobs that should not affect overall app health, add:

```yaml
metadata:
  annotations:
    argocd.argoproj.io/ignore-healthcheck: "true"
```

Success criteria:

1. You know which apps changed behavior because of CronJob health evaluation.
2. Only meaningful CronJob failures affect application health.
3. No important app is left unexpectedly `Degraded` without explanation.

Do not continue until all success criteria are met.

## Step 7: Deliberately switch resource tracking from labels to annotations

Why this matters:

- Annotation tracking is the Argo CD `3.x` default.
- This transition can leave orphaned resources if not handled deliberately.

Instructions:

1. Update `argo-apps/core-apps/argocd.yaml` and change:

```yaml
application.resourceTrackingMethod: annotation
```

2. Sync the Argo CD app.
3. Explicitly sync managed applications, even if they do not appear out of sync.
4. Pay special attention to apps with `prune` enabled.
5. Inspect for orphaned resources after the explicit sync pass.

Success criteria:

1. Managed resources receive Argo CD tracking annotations.
2. No unexpected orphaned resources remain.
3. Prune still works correctly after the transition.

Do not continue until all success criteria are met.

## Step 8: Review new behavior and useful features

Instructions:

1. Verify CloudNativePG app health now reports correctly using Argo CD built-in health checks.
2. Review whether the new default resource exclusions and ignored updates reduce noise without hiding needed information.
3. Review app status for any behavior changes caused by the Argo CD `3.x` diffing and health defaults.

Success criteria:

1. CNPG health is useful and accurate.
2. No important drift is being hidden unintentionally.
3. Controller noise is reduced or unchanged.

Do not continue until all success criteria are met.

## Step 9: Clean up temporary compatibility settings

Instructions:

1. Remove any temporary stabilization setting that is no longer needed.
2. Keep `ServerSideApply=true` on the self-managed Argo CD app.
3. Ensure the tracking method is left in the intended steady state.

Success criteria:

1. Final config reflects the desired long-term state.
2. No temporary migration workaround remains unintentionally.

Do not continue until all success criteria are met.

## Step 10: Final steady-state verification

Instructions:

1. Verify final Argo CD status:
   - `argocd app list`
   - `kubectl get applications -A`
   - `kubectl get pods -n argocd`
2. Wait through at least one normal sync cycle.
3. Review logs from controller, server, and repo-server for upgrade warnings.
4. Confirm final versions match the target.

Success criteria:

1. Argo CD is on chart `9.5.21`.
2. Argo CD is on app version `v3.4.3`.
3. Core apps remain manageable.
4. No unresolved upgrade warnings remain.

## Working Order Summary

1. Baseline the current install.
2. Add `ServerSideApply=true`.
3. Pin resource tracking to `label` temporarily.
4. Upgrade through chart checkpoints.
5. Validate core workflows after each checkpoint.
6. Review CronJob health behavior.
7. Switch tracking to `annotation`.
8. Review new features and behavior.
9. Remove temporary migration settings.
10. Perform final verification.

## First Change To Make

Edit `argo-apps/core-apps/argocd.yaml` and add this under `spec.syncPolicy.syncOptions`:

```yaml
- ServerSideApply=true
```

## Gate Before Moving Past The First Change

Do not begin the chart upgrade until all of the following are true:

1. The Argo CD application has synced the SSA change successfully.
2. The Argo CD app is `Healthy`.
3. All Argo CD pods in `argocd` are ready.
