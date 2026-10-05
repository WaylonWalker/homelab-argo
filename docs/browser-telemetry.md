# Browser telemetry

The shared Grafana Faro endpoint is `https://telemetry.wayl.one/collect`.
The browser SDK and shared bootstrap bundle are served from
`https://telemetry.wayl.one/assets/`.

## Static-site platform

New sites from `templates/static-site` enable telemetry by default. The
Copier template writes these keys into `site-config.yaml`:

```yaml
  TELEMETRY_ENABLED: "enabled"
  TELEMETRY_APP_NAME: caps
  TELEMETRY_ENVIRONMENT: production
  TELEMETRY_VERSION: unknown
```

Use the same `TELEMETRY_APP_NAME` for production and development. Set the
environment to `production`, `preview`, or `development`. Use a Git SHA or
release value when the publisher provides one. Otherwise, use `unknown`.

To disable telemetry for one site, set `TELEMETRY_ENABLED` to `"disabled"`.
The Nginx template injects the bootstrap only into `text/html` responses that
contain `</head>`. Nginx scans the response before it applies gzip. The filter
runs once for each response. It does not change JavaScript, CSS, images, or
downloads.

The bootstrap URL includes no query string or per-release path. It uses a
short shared cache lifetime. It reads the site name, environment, and version
from the injected script tag. It does not capture console arguments, click
text, form values, cookies, storage, or arbitrary request headers.

## Vite and JavaScript applications

For an app that serves `index.html`, add this to its `<head>`:

```html
<script
  defer
  referrerpolicy="no-referrer"
  src="https://telemetry.wayl.one/assets/faro-bootstrap.js"
  data-faro-app="lantern-table"
  data-faro-version="%VITE_GIT_SHA%"
  data-faro-environment="%VITE_APP_ENV%"
></script>
```

Vite replaces the `%VITE_*%` values during its build. Set `VITE_APP_ENV` to
`production`, `preview`, or `development`. Set `VITE_GIT_SHA` to the release
SHA, or `unknown` if the build has no release value.

For app code that needs access to the Faro API, load the self-hosted ESM helper.
This pattern keeps application startup independent of telemetry availability:

```ts
void import(/* @vite-ignore */ 'https://telemetry.wayl.one/assets/faro-client.js')
  .then(({ setupFaro }) => {
    const faro = setupFaro({
      appName: 'lantern-table',
      version: import.meta.env.VITE_GIT_SHA || 'unknown',
      environment: import.meta.env.VITE_APP_ENV,
    });
    faro?.api.pushLog(['websocket reconnect failed']);
  })
  .catch(() => {});
```

Use logs for technical events only. Do not include user text or input. The
shared helper captures errors, unhandled rejections, performance, Web Vitals,
page views, and browser traces. It removes query strings and fragments from
URLs. It redacts common credential patterns. It adds trace headers only to
Waylon-owned domains. On localhost, telemetry stays off unless a caller passes
`allowLocalhost: true` to `setupFaro` or adds `data-faro-local="true"` to the
bootstrap script tag.

## FastAPI HTML applications

Add the same script tag to the shared base Jinja template for browser pages.
Set the app metadata in deployment configuration or template variables. Do not
add the script to JSON responses, API docs, authentication pages, or admin
surfaces. Keep server telemetry separate and send it to the internal OTel
collector.

## Markata-Go sites

Markata-Go already has shared head configuration, but its script-tag model does
not include the metadata attributes that this bootstrap needs. See
[`markata-go-telemetry-plan.md`](markata-go-telemetry-plan.md) for the native
feature design and preview rules.

## Rollout and inventory

The `caps-dev`, `emboss-dev`, `strip-dev`, and `voice-reverse-dev` canaries passed in Chromium on 2026-10-05. Their production counterparts passed a Chromium exception check in Loki. The shared static-site platform is enabled for its other first-party browser sites, and the shared `k8s-pages` chart now enables its first-party utility sites. Both paths keep a per-site opt-out. See
[`browser-telemetry-inventory.md`](browser-telemetry-inventory.md) for live
host ownership, application family, and current status.


## Validation and Grafana queries

The development cohort passed in Chromium on 2026-10-05. Each host loaded with HTTP 200, received one synthetic exception, and reported its stable app name with `environment=development` and `version=unknown`. A production exception from Caps arrived with `environment=production`. The separate `k8s-pages` dev site `dev.rhiannonwalker.com` also reported an exception as `rhiannonwalker-com` with `environment=development`. The event and related browser spans are available in Loki and Tempo. The ESM helper imported from `/assets/faro-client.js` in Chromium and exposed `setupFaro` as a function. The Chromium trace `583825302997bf05df6359d2aa888ace` was retrieved from Tempo with `service.name=caps`, `deployment.environment.name=development`, and `service.version=unknown`. Blocking `telemetry.wayl.one` still left Strip loaded with HTTP 200.

Use these queries in Grafana Explore:

```logql
{source="browser"} | json | kind="exception"
{source="browser"} | json | app_name="caps" | app_environment="development" | kind="exception"
{source="browser"} | json | page_url=~".*caps-dev\.waylonwalker\.com.*"
```

In Tempo, filter spans by `service.name="caps"`,
`deployment.environment.name="development"`, and `service.version="unknown"`.
The Loki record includes `app_name`, `app_environment`, `app_version`, and
`page_url` as JSON fields. These stay out of Loki stream labels to avoid
high-cardinality label growth.

Use this Loki query to compare the canary applications by app and environment:

```logql
sum by (app_name, app_environment) (count_over_time({source="browser"} | json | kind="exception" [1h]))
```

Useful Prometheus queries:

```promql
rate(faro_receiver_events_total[5m])
faro_receiver_exceptions_total
faro_receiver_logs_total
faro_receiver_rate_limiter_requests_total{allowed="false"}
faro_receiver_sourcemap_downloads_total{http_status!="200"}
loki_write_dropped_entries_total
loki_write_batch_retries_total
otelcol_exporter_send_failed_spans_total
```

On 2026-10-05, `up{service="alloy"}` was `1`; Faro receiver metrics were
visible through the Alloy ServiceMonitor. The public receiver returned 405 for `GET /collect`; `/metrics` returned 404. The observability namespace exposed only the Alloy and Grafana ingresses, with Loki and Tempo remaining cluster-internal. The receiver recorded synthetic
exceptions from all four shared static-site development sites, production Caps,
and `dev.rhiannonwalker.com` through the `k8s-pages` family. Loki dropped
entries and batch retries were zero. Source-map downloads from all four dev
hosts returned HTTP 200. The Nginx checks confirmed one injection for a repeated `</head>`, no injection when `<head>` is absent, no changes to JavaScript or text assets, and working gzip. Live `k8s-pages` responses were `text/html` without a CSP header; disabled sites remained unchanged. Tempo contained browser spans with matching app,
environment, and version attributes.
