# Automatic DNS through falcon

## Current setup

On 2026-10-02, the `falcon` tunnel configuration changed from version 92 to 93.
Its final ingress rule now sends unmatched HTTP hostnames to
`http://traefik.kube-system.svc.cluster.local:80`. The 63 earlier rules keep
their order and destinations. These include the explicit SSH and TCP routes.

ExternalDNS watches Traefik Ingresses. It creates proxied CNAME records that
point to `1bdd7ce3-6476-43bc-a9e0-6e30167617e5.cfargotunnel.com`.
Traefik publishes that tunnel hostname in Ingress status. ExternalDNS uses
`create-only`, so it does not change or delete an existing DNS record.

For a new subdomain in a zone listed in `k8s/external-dns/zone-ids.yaml`, add
an Ingress with `ingressClassName: traefik` and a host under `spec.rules`.
ExternalDNS creates the DNS record. The tunnel sends the request to Traefik.
Traefik sends the request to the Service in the Ingress.

The permanent canary is `external-dns-canary.wayl.one`. It uses the `whoami`
Service in Kubernetes.

## Limits

- `create-only` preserves existing records. An existing record that points to
  another tunnel needs a separate migration. The `fokais.com` and
  `www.fokais.com` records still point to the `fokais` tunnel.
- ExternalDNS uses the zones in `zone-ids.yaml`. Add a new Cloudflare zone to
  that file and the sealed token before you use it for an Ingress.
- The current policy manages CNAME records for Ingress hosts. A new apex host
  or a host with a conflicting record needs separate DNS work.
- Cloudflare certificates and Access policies are separate from DNS and tunnel
  routing. Check them when a new hostname needs those services.

## Check a new host

Replace `HOST` with the new hostname.

```bash
kubectl get ingress -A -o wide
kubectl logs -n external-dns deployment/external-dns --since=10m
dig +short HOST
curl -I https://HOST/
```

If the host has a proxied record, `dig` returns Cloudflare IP addresses.
Use the Cloudflare DNS API or dashboard to inspect its CNAME target.
The target must be the `falcon` tunnel UUID above.

If the tunnel configuration changes, make sure that its last ingress rule
still points to Traefik. Cloudflare stores this configuration outside Git.
The prechange configuration is saved locally at
`private/cloudflared/falcon-config-before-ingress-fallback-2026-10-02.json`.
That private file is not in the repository.

Cloudflare documents the [tunnel configuration API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/configurations/)
and [ingress rule order](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/configuration-file/).
