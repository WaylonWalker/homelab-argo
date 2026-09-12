# ExternalDNS rollout runbook

This runbook covers the controlled rollout of ExternalDNS. This PR does not
enable ExternalDNS writes or a broad Ingress rollout.

## Settled contract

- Cluster: K3s `v1.36.4+k3s1`.
- Traefik: chart `40.1.4+up40.1.0`, Traefik `3.7.8`.
- The current Traefik `publishedService` is `kube-system/traefik`. Its status
  contains three node IPs.
- The tunnel is `falcon`, UUID `1bdd7ce3-6476-43bc-a9e0-6e30167617e5`, with
  six `cloudflared` replicas. Do not change its existing routes.
- ExternalDNS chart `1.22.0`, application `0.22.0`.
- Zones: `aylawalker.com`, `fluffed-up.com`, `fokais.com`, `kedro.dev`,
  `markata.dev`, `rhiannonwalker.com`, `ticklemykeys.com`, `wayl.one`,
  `waylonwalker.com`, and `wyattbubbylee.com`.
- Registry policy: owner ID `falcon-homelab-external-dns`; TXT prefix
  `external-dns-%{record_type}.`; source `ingress`; class `traefik`; all
  Traefik Ingresses (canary label filter removed for full dry-run preview);
  CNAME records only; `dry-run` (still on: proposals are logged, nothing is
  written); `create-only` (additive-only: existing records are never updated
  or deleted); Cloudflare records proxied.

The generated values include all Cloudflare zones that the token can see at
secret-generation time. Zone-ID filters prevent automatic access to zones that
are added later. Rerun the recipe to add a new zone deliberately.

`wayl.one` is required because the existing tunnel has a `*.wayl.one` route to
Traefik. The observed routes also include `*.pages.wayl.one`,
`*.rhiannonwalker.com`, `rhiannonwalker.com`, and many explicit
`waylonwalker.com` and `wyattbubbylee.com` hosts. No `*.waylonwalker.com` or
`*.wyattbubbylee.com` route was observed. Therefore, require a matching existing
tunnel route before labeling any Ingress in either of those two zones.

The `falcon` tunnel also has apex and wildcard routes for `aylawalker.com` and
`fluffed-up.com`. It has explicit routes for `go.markata.dev` and
`din.markata.dev`. No active Ingress uses `kedro.dev` or `ticklemykeys.com`.

The `fokais.com` Ingress (`www-fokais` in namespace `www-fokais`, hosts
`fokais.com` and `www.fokais.com`) currently uses a separate tunnel with UUID
`bf48defd-05c0-42e2-bc3e-03828c754a74` via `fokais-cloudflared-deployment` in
namespace `fokais-cloudflared`. Both are sourced from the external repo
`fokais-com/argo.fokais`, not from this repo. Approved direction: migrate
`fokais.com` to `falcon`. Until `falcon` has verified public-hostname routes
for both hosts and the exact Cloudflare records are baselined, do not label
any `fokais.com` Ingress for this ExternalDNS instance. Labeling will require
a change in the external repo. Tunnel route changes live in Cloudflare Zero
Trust, not in git. This change records approval only and makes no live
`fokais` cutover.

## Architecture and data flow

1. Traefik writes the `falcon` tunnel hostname to the status of each Traefik
   Ingress. It does not copy the node IPs from the Traefik Service.
2. The Ingress source selects every Traefik Ingress. The canary label filter
   was removed to preview the full scope; `dry-run` keeps the preview
   write-free.
3. ExternalDNS reads the Ingress hosts and the tunnel hostname from its status.
   It proposes an explicit CNAME for each selected host.
4. ExternalDNS uses Cloudflare as the provider. It adds ownership TXT records
   with the configured owner and prefix. It also requests proxied records.
5. In dry-run mode ExternalDNS logs the proposed changes but does not call
   Cloudflare to write them. `create-only` creates missing records but never
   updates or deletes existing ones, including when an Ingress is deleted or
   retargeted.
6. A client resolves the Cloudflare record, enters the existing `falcon` tunnel,
   and is forwarded by an unchanged tunnel route to Traefik. Traefik forwards
   the request to the Kubernetes Service.

The permanent health canary is `external-dns-canary.wayl.one`, backed by the
stateless `whoami` Service. It must remain as an operational check. It is not
automatically deleted: `create-only` cannot clean it up.

## Discoveries and important differences

- Before this rollout, Traefik publishes three node IPs through
  `kube-system/traefik`; this is the fallback to restore only after ExternalDNS
  has been made safe.
- Tunnel coverage is not equivalent to DNS-zone ownership. In particular, the
  zones without an observed `falcon` wildcard route need an explicit route
  check for every host before labeling. A zone can use a different tunnel.
  Such an Ingress is not eligible for this ExternalDNS instance.
- The existing `whoami` Ingress has two hosts, `whoami.wayl.one` and
  `cfwhoami.wayl.one`, and is not initially labeled. Labeling it is therefore a
  two-host change, not a one-host test.
- Query exact existing Cloudflare records before adding a label. `create-only`
  never overwrites them, but the baseline is still required to confirm the new
  record will not shadow working DNS.

## Prerequisites and secret creation

Run from the repository root with a kubeconfig for the target cluster:

```bash
kubectl version
kubectl get nodes -o wide
kubectl get helmchart traefik -n kube-system \
  -o jsonpath='{.spec.chart}{"\n"}'
kubectl get deployment traefik -n kube-system \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl get svc traefik -n kube-system -o yaml
kubectl get ingress --all-namespaces -o wide
```

Stop if the Traefik chart is not `40.1.4+up40.1.0`. Stop if the image is not
`rancher/mirrored-library-traefik:3.7.8`. For a newer version, recheck the Helm
values path before rollout.

Create or refresh the ExternalDNS secret through the repository recipe. Do not
paste token values into a shell command or into this runbook:

Create the token with access to **All zones** in the account.

CAUTION: This recipe makes temporary live DNS changes. It creates and
immediately deletes one unique TXT record in each visible zone. This operation
proves the token's DNS write access.

```bash
just external-dns-secret
```

The recipe verifies Cloudflare access. It lists all visible zones and asks for
confirmation before the write checks. It writes an encrypted SealedSecret plus
the nonsecret zone names and IDs. It does not apply the Secret or commit files.

Review the generated resources without decrypting the Secret:

```bash
ls -l \
  k8s/external-dns/manifests/cloudflare-api-token-sealed-secret.yaml \
  k8s/external-dns/zone-ids.yaml
kubeseal --validate \
  --controller-name sealed-secrets-controller \
  --controller-namespace kube-system \
  < k8s/external-dns/manifests/cloudflare-api-token-sealed-secret.yaml
```

Commit both files before Argo starts the deployment. After Argo syncs, make
sure that the controller created the Secret. Do not print its data:

```bash
kubectl get sealedsecret external-dns-cloudflare -n external-dns
kubectl get secret external-dns-cloudflare -n external-dns
```

## Pre-merge and local validation

From the repository root, validate the rendered chart without contacting
Cloudflare. These commands assume the PR has added
`k8s/external-dns/values.yaml` and the ExternalDNS Application/manifests:

```bash
helm template external-dns external-dns \
  --repo https://kubernetes-sigs.github.io/external-dns/ \
  --version 1.22.0 \
  --namespace external-dns \
  --values k8s/external-dns/values.yaml \
  --values k8s/external-dns/zone-ids.yaml \
  > /tmp/external-dns-rendered.yaml
kubectl apply --dry-run=client -f /tmp/external-dns-rendered.yaml
```

Check the rendered output for the settled contract without displaying secret
values:

```bash
rg 'dry-run|create-only|traefik|external-dns-canary|waylonwalker|rhiannonwalker|wyattbubbylee|wayl.one' /tmp/external-dns-rendered.yaml
kubectl apply --dry-run=server -f argo-apps/core-apps/external-dns.yaml
kubectl apply --dry-run=server -f argo-apps/core-apps/traefik-config.yaml
kubectl apply --dry-run=server -k k8s/traefik-config
kubectl apply --dry-run=server -k whoami
```

Before merge, also render the actual ArgoCD application path and inspect its
diff. Do not apply it directly if ArgoCD owns the resource.

## Exact dry-run deployment checks

After the PR is synced, verify the Traefik rollout and Ingress status first:

```bash
kubectl rollout status deployment/traefik -n kube-system --timeout=300s
kubectl get deployment traefik -n kube-system \
  -o jsonpath='{range .spec.template.spec.containers[0].args[*]}{.}{"\n"}{end}'
kubectl get ingress external-dns-canary -n whoami \
  -o jsonpath='{.status.loadBalancer.ingress}{"\n"}'
```

The Traefik arguments must contain the tunnel-hostname option. They must not
contain the `publishedservice` option. The Ingress status must contain only:

```text
1bdd7ce3-6476-43bc-a9e0-6e30167617e5.cfargotunnel.com
```

Then verify the ExternalDNS deployment and its arguments:

```bash
kubectl rollout status deployment/external-dns -n external-dns --timeout=120s
kubectl get deployment external-dns -n external-dns -o wide
kubectl get pods -n external-dns -l app.kubernetes.io/name=external-dns
kubectl get deployment external-dns -n external-dns \
  -o jsonpath='{range .spec.template.spec.containers[0].args[*]}{.}{"\n"}{end}'
```

The arguments must show dry-run, create-only, Traefik class filtering, the
settled owner/prefix, CNAME-only policy, all generated zones, and proxied
Cloudflare behavior. Secret references can appear. Secret data must not appear.

Inspect logs for a bounded interval:

```bash
kubectl logs -n external-dns deployment/external-dns --since=15m --timestamps
```

### Expected dry-run log scope

The expected proposed scope is the permanent canary only:

- `external-dns-canary.wayl.one` CNAME activity, plus its ownership TXT
  bookkeeping if the provider reports it.
- CNAME target
  `1bdd7ce3-6476-43bc-a9e0-6e30167617e5.cfargotunnel.com` with Cloudflare proxy
  mode enabled.
- No writes to Cloudflare.
- No proposed changes for unlabeled `whoami`, Excalidraw, Librespeed, or other
  Ingresses.
- No wildcard creation, zone apex replacement, or changes to existing tunnel
  routes.

Unexpected hosts, deletes, A/AAAA records, or changes outside the canary are a
stop condition. Check the label, class, source, zone filters, and exact current
Cloudflare records before proceeding.

## First live canary change

The first live step is a separate, reviewed change that removes **only**
`dry-run` from `k8s/external-dns/values.yaml`. Do not change the tunnel,
`publishedService`, zone list, host labels, or write policy in that step.

After ArgoCD syncs that one-line change:

```bash
kubectl rollout status deployment/external-dns -n external-dns --timeout=120s
kubectl logs -n external-dns deployment/external-dns --since=10m --timestamps
curl -fsS https://external-dns-canary.wayl.one/
```

Use a normal external client for this HTTP check. The response must be the
stateless whoami response, with a successful TLS and HTTP status.

### Cloudflare API and dashboard verification

Read the token without terminal output. Then query the exact record names. The
commands print record metadata and values, but they do not print the token:

```bash
read -rsp 'Cloudflare API token: ' CF_API_TOKEN
printf '\n'
cf_curl() {
  curl -fsS \
    --config <(printf 'header = "Authorization: Bearer %s"\n' "$CF_API_TOKEN") \
    "$@"
}
zone_id="$(cf_curl \
  'https://api.cloudflare.com/client/v4/zones?name=wayl.one&status=active' \
  | jq -r '.result[0].id')"
cf_curl \
  "https://api.cloudflare.com/client/v4/zones/${zone_id}/dns_records?type=CNAME&name=external-dns-canary.wayl.one" \
  | jq '.result[] | {name,type,content,proxied,ttl,comment}'
cf_curl \
  "https://api.cloudflare.com/client/v4/zones/${zone_id}/dns_records?type=TXT&name=external-dns-cname.external-dns-canary.wayl.one" \
  | jq '.result[] | {name,type,content,ttl,comment}'
unset CF_API_TOKEN zone_id
unset -f cf_curl
```

In Cloudflare Dashboard, open **Websites → wayl.one → DNS → Records** and
filter for `external-dns-canary.wayl.one`. Confirm one proxied CNAME and the
ownership TXT record with the expected owner/prefix. Do not edit existing
tunnel routes. In **Zero Trust → Networks → Tunnels → falcon → Public
Hostnames**, confirm the existing wildcard route still points to Traefik.

Repeat Kubernetes and request checks:

```bash
kubectl get ingress -A -l external-dns-canary=true -o wide
kubectl get svc -n whoami whoami -o wide
curl -fsS https://external-dns-canary.wayl.one/
kubectl logs -n external-dns deployment/external-dns --since=15m --timestamps
```

## Rollback safety

If DNS, TLS, routing, or log scope is wrong, stop labeling Ingresses. Roll back
in this order:

1. Restore `dry-run` (or scale ExternalDNS down) and wait for its rollout.
2. Confirm ExternalDNS is no longer proposing or applying changes.
3. Only then restore Traefik's publishedService behavior if that was changed by
   a later, separately approved migration.

Do not rely on Ingress deletion to remove DNS: under `create-only`, deleting an
   Ingress neither deletes its DNS record nor updates a stale one. Remove or
   correct stale records with an explicit, reviewed Cloudflare operation.

## Expanding the rollout one app at a time

For every host, first confirm the exact existing record and a matching existing
`falcon` tunnel route. This check is mandatory when no `falcon` wildcard route
was observed. A route on a different Cloudflare tunnel does not qualify.
Label one app, sync, and repeat the Cloudflare, Kubernetes, HTTP, and log checks
before selecting another app.

Recommended order:

1. **Excalidraw** — one stateless host, `excalidraw.wayl.one`; it gives a small
   real-application change with low state and host-count risk.
2. **whoami** — two hosts, `whoami.wayl.one` and `cfwhoami.wayl.one`; label only
   after checking both records and routes.
3. **Librespeed** — two stateless hosts, `librespeed.wayl.one` and
   `speed.wayl.one`; verify both together.

Do not start with status or foundational apps. Their availability is needed to
observe and recover the rollout, and many have state, authentication, or
control-plane dependencies that make DNS and application failures harder to
separate.

### K9s inspection

Open K9s and inspect the `external-dns` namespace. Watch the Deployment, pods,
Secret, SealedSecret, events, and logs. Inspect the `traefik` HelmChartConfig in
`kube-system`. Then inspect each selected application namespace and its Ingress,
Service, and endpoints. Confirm that only the intended Ingress has the canary
label and that endpoints remain ready.

### Cloudflare inspection

For each selected host, query the exact CNAME and ownership TXT record through
the API or Dashboard. Confirm the target, proxied flag, TTL policy, and owner.
Compare the result with the pre-label snapshot. An unexpected update is a stop
condition, even when no record was deleted.

## Completion criteria

### Remove the canary filter

Remove the temporary `external-dns-canary=true` filter only after all of the
following are true:

- the permanent canary is healthy;
- dry-run showed only intended records;
- the canary live write and HTTP path passed;
- every selected host has a matching tunnel route and exact-record baseline;
- no unexpected ExternalDNS errors, changes, or deletes appeared; and
- rollback ownership and Cloudflare access were tested.

Removing the filter is a separate approved change. It is not part of this PR.

### Proving period

During the proving period, keep dry-run or the narrow label filter as the
rollback boundary. For at least one normal operating cycle, verify the canary
and each selected host from an external client, inspect ExternalDNS logs after
Ingress or certificate changes, and compare Cloudflare records with the
baseline. Record no unexpected creates, route changes, TLS failures, or
application errors.

### Much later: sync mode

Do not enable broad sync or change `create-only` until a later change has:

- a complete inventory of all Ingress hosts and exact Cloudflare records;
- confirmed `falcon` tunnel coverage for every host, including zones that use
  another tunnel today;
- tested ownership TXT recovery and stale-record handling;
- an approved deletion plan and maintenance window; and
- a tested rollback and post-change observation plan.

Only then may a separate review consider sync behavior. This rollout does not
perform that work.
