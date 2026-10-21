# Forgejo MCP (K3s / Argo CD)

Argo CD Application: `forgejo-mcp`, deployed from `k8s/forgejo-mcp`.

- External MCP endpoint: `https://mcp.wayl.one/mcp` (Streamable HTTP).
- Forgejo API target: `http://forgejo.forgejo.svc.cluster.local:3000` (cluster-internal).
- Upstream: https://git.b4mad.industries/agentic-forges/forgejo-mcp
- Image: `git.b4mad.industries/agentic-forges/forgejo-mcp:v3.3.0` (amd64 only).
- Authentication: **passthrough**. Every MCP request requires its own
  `Authorization: Bearer <Forgejo PAT>` (or `Authorization: token <PAT>`).
  Anonymous requests are rejected by the upstream server. No global
  service-side Forgejo token is stored or configured. Do **not** turn on
  `--allow-operator-token-fallback`.
- Forgejo currently runs v17.0.0. The deployment still uses passthrough mode;
  OAuth resource-server mode is not enabled.

See [the OAuth runbook](oidc-runbook.md) for the planned ChatGPT connection,
deployment checks, rollback, and known gates.

## Isolated OAuth staging

The staged deployments use separate Argo Applications and namespaces:

- HLab Auth: `hlab-auth-oidc-stage` at
  `https://auth-oidc-stage.wayl.one`, with a new PostgreSQL database.
- Forgejo MCP: `forgejo-mcp-oidc-stage` at
  `https://mcp-oidc-stage.wayl.one/mcp`.
- The staging MCP server publishes its issuer metadata and JWKS at
  `https://mcp.wayl.one/issuer`. Its `mcp.wayl.one` Ingress serves only
  `/issuer`; the existing production `/mcp` Ingress stays on passthrough.

Staging uses sealed, separately generated keys. Its initial user, OAuth client,
Forgejo Authorized Integration, and per-user `forgejo_aud` must be configured
before an end-to-end read test. Do not grant that integration write access.
These staged resources do not change the production HLab Auth Deployment or
production database.

## Connecting a client

1. In Forgejo (`https://git.wayl.one`), create a fine-grained, revocable
   personal access token from Settings > Applications. Grant only the
   repository/issue/pull-request permissions that client needs. Avoid
   admin-level tokens.
2. Configure an MCP client capable of **remote Streamable HTTP with custom
   Authorization headers**, with server URL `https://mcp.wayl.one/mcp`
   and `Authorization: Bearer <PAT>`. Keep the PAT in the client's secret
   manager; never in Git, an MCP URL, or a prompt.
3. Check Argo CD Application `forgejo-mcp` is Healthy / Synced and that the
   ingress and DNS resolve. ExternalDNS is configured to create Cloudflare
   CNAMEs for ingress hosts in the `wayl.one` domain; verify the Cloudflare
   Tunnel routing actually reaches Traefik.

A quick unauthenticated smoke test should return **401**, not MCP data:

```sh
curl -si https://mcp.wayl.one/mcp
```

Then test the authenticated MCP initialization/tools/list with your client.
A GET alone with a token is not a complete MCP protocol health test.

## Security and operations

- This is a public HTTPS endpoint **only for clients with valid scoped Forgejo
  credentials**. There is no separate static MCP API key. Cloudflare,
  Traefik and any HTTP logs must not record Authorization headers.
- The MCP server forwards a client's PAT to Forgejo. Use separate
  least-privilege tokens for each agent and revoke compromised tokens.
- The MCP server's OAuth resource-server mode requires Forgejo 16+; the
  homelab's current Forgejo v17 meets that requirement. The current MCP
  deployment still uses token passthrough until HLab Auth OIDC and the
  resource-server configuration pass the runbook's gates.
- Not all ChatGPT plans or clients support registering a remote MCP with
  custom Authorization headers. Deploying this service alone does not
  connect ChatGPT to it.
- This service is stateless (no PVC, no Kubernetes API permissions).
  Authentication is enforced upstream on **every** HTTP request.
- The service listens on all container interfaces but explicitly allows
  the public Host header `mcp.wayl.one`; update `--allowed-hosts` if the
  hostname changes.
- `tcpSocket` probes only verify that the MCP process is listening.
  Review pod logs and run an authenticated MCP request to confirm that
  Forgejo integration works.
- For stronger access control, add a WAF/rate limit at the Cloudflare edge,
  or keep the ingress private and use a trusted tunnel.
