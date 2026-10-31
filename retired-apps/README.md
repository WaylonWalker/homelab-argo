# Retired applications

These Applications are archived outside the `argo-apps/apps` directory, so the `1-apps` Argo application does not reconcile them. Their runtime resources were removed through cascading Argo Application deletion. The original workload manifests remain in their `k8s/<app>` paths where applicable.

## Restore an application

Move its `application.yaml` back to `argo-apps/apps/<name>.yaml` and commit the change. Argo CD will recreate the Application and reconcile its source. For Headlamp, the archived Application points to the pinned upstream Helm chart. Dozzle and Installer use their retained `k8s/<app>` manifests.

## Retired

- `headlamp`: explicitly retired; no PVCs.
- `dozzle`: no PVCs; removal also removes its cluster-wide ClusterRole and ClusterRoleBinding.
- `installer`: no PVCs.
