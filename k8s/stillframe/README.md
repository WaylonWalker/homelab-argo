# Stillframe

The app runs on `falcon3` and reads all of `/mnt/main/walkershare` at `/photos`,
mounted read-only. Hidden directories are skipped by the scanner, and
`STILLFRAME_EXCLUDED_PATHS=stillframe` keeps the app's own previews, models,
and database out of the photo catalog. The app data lives in the separate
`main/walkershare/stillframe` ZFS child dataset, mounted at
`/mnt/main/walkershare/stillframe`; it inherits Walkershare's LZ4 compression
and 128 KiB record size. The original Longhorn `stillframe-data` claim is
retained unmounted as a rollback copy and excluded from Argo pruning. Snapshot
scheduling is managed separately from this deployment.

The public home page is available on both hostnames:

- `stillframe.waylonwalker.com` (canonical URL)
- `stillframe.wayl.one`

Traefik sends `/app` and `/api` through HLab Auth. The app also verifies the
forwarded user header came from Traefik's pod CIDR, and the NetworkPolicy
allows inbound app traffic only from Traefik.

## HLab Auth registration

The active `hlab` CLI credential needs `apps:write`, `scopes:write`, and
`roles:write` to provision the app. Register the first protected path, then
add the remaining paths using the app ID returned by the first command:

```sh
hlab apps protect \
  --name stillframe \
  --host stillframe.waylonwalker.com \
  --path /app

hlab apps protect-path --app <app-id> --host stillframe.waylonwalker.com --path /api
hlab apps protect-path --app <app-id> --host stillframe.wayl.one --path /app
hlab apps protect-path --app <app-id> --host stillframe.wayl.one --path /api
```

This keeps `/` and static landing-page assets public while protecting the app
shell and every library API route. Assign the generated Stillframe access role
only to intended viewers. If a route is not registered in HLab Auth, ForwardAuth
fails closed and the app itself still rejects missing trusted identity headers.

The ingress requests a certificate for both names from the
`letsencrypt-prod` ClusterIssuer. External DNS is managed by the cluster's
existing ingress controller configuration.
