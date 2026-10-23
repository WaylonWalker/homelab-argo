# Security inventory: issue 174, first pass

The graph in [issue-174-dependencies.yaml](issue-174-dependencies.yaml) records
configured connections found in deployed manifests. It is a starting point for
policy design, not a complete traffic trace. The scan also covered local
repositories under `~/git`; Forgejo workflow files were found in
`forgejo-runner-smoke`, `brainrot-lighthouse-release`, and
`learn-forgejo-actions`. Jobs using `ubuntu-latest` will wait while the runner
is paused. Other Forgejo-hosted repositories and scheduled jobs remain unknown.

Live Kubernetes inventory before the first policy found 123 namespaces and 112
Ingress resources. NetworkPolicies existed in 21 namespaces; eight policies
declared egress isolation. Three Services used `LoadBalancer`: Traefik,
registry, and Samba. External reachability and firewall boundaries were not
tested. Thirty running pods included a privileged container, and 55 had a
hostPath mount. These counts are a snapshot, not an exposure verdict.

The K3s nodes use Flannel annotations. An isolated test namespace confirmed
that an egress NetworkPolicy took effect: HTTP from a client pod to a server pod
worked before the policy, failed after propagation, and worked again after
policy removal. The test namespace was deleted. This verifies enforcement for
that pod pair; it does not prove every CNI path or policy rule.

The first target is `whoami`. Its Deployment defines no outbound application
connection. Its Ingress and DNS canary route through Traefik. The policy allows
the observed Traefik selector for ingress and CoreDNS for egress. Direct routes
from other public apps to data, management, storage, and API services are still
unverified. Do not infer internet reachability from an Ingress or a LAN-facing
Service. Do not add broader egress policies until traces, logs, scheduled jobs,
and failure paths have been checked.

Next inventory work: collect traffic evidence for MinIO, PostgreSQL, Longhorn,
NAS, Kubernetes API, registry, OTel, DNS, webhooks, and backup jobs; classify
service-account token mounts and RBAC by workload; inspect privileged and
hostPath workloads individually. Avoid publishing internal addresses or secret
values. Check Cloudflare Access and application authentication separately from
cluster routing.

The second scan of `~/git` found more paths in app source repos. It confirmed
that Brainrot has scheduled RSS and Dropper HTTP clients, Shot has Redis and S3
clients, and Lantern Table uses Valkey for public-mode signaling. The public
graph now includes only connections already visible in this GitOps repository.
The detailed map for private app repositories is kept locally and is not
published here. In particular, a forward-auth URL in an Ingress chart means
Traefik calls the auth service; the protected application is not the caller.
LibreSpeed is the next isolated policy candidate: its deployed manifest has
only a timezone variable, no mounted app configuration, and no configured
database or IP information service. Verify its backend routes during rollout.
