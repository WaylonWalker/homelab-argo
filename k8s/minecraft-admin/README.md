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

The deployment uses:

- `kraft-admin.wayl.one`
- `kraft.wayl.one`

Managed namespaces for this PoC:

- `kraft`
- `magnet-smp`
