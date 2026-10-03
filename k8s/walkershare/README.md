# Walkershare

These manifests reconcile the previously untracked files with live state on
2026-10-02. Filebrowser, Samba, and Syncthing run on Falcon3. The obsolete
Copyparty proposal and its orphaned live ingress are omitted. The live ingress
walkershare-ingress still points at the absent copyparty Service; it needs a
hostname/owner decision before retirement or replacement.

Samba credentials are sealed from the existing Secret without rotation.
The shared PV retains `/mnt/main/walkershare`; the two Filebrowser claims keep
their existing Longhorn storage classes. No data copy or storage migration is
part of this recovery. TLS certificates remain managed by cert-manager.

Render with `kubectl kustomize k8s/walkershare`. The `walkershare` Argo Application uses manual
sync and has no automatic pruning. Server dry-run confirms all three pod
templates match live state. HostPath node affinity and backup coverage still
need operational review. Applying an old share.yaml would recreate
obsolete credentials and workloads; use these reconciled manifests instead.
