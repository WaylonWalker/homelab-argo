# minecraft-admin

Create the auth secret before syncing this app:

```bash
kubectl create secret generic minecraft-admin-secret \
  --namespace minecraft-admin \
  --from-literal=APP_SECRET='replace-with-a-long-random-secret' \
  --from-literal=ADMIN_USERNAME='admin' \
  --from-literal=ADMIN_PASSWORD='replace-with-a-strong-password' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Both hosts route to the `minecraft-admin` service:

- `kraft-admin.wayl.one`
- `kraft.wayl.one`

The app currently manages:

- `magnet-smp`

Kraft is paused, so the admin app does not list or manage it. The two hosts
remain available for the admin UI.
