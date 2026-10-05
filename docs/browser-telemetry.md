# Browser telemetry

The shared Grafana Faro endpoint is `https://telemetry.wayl.one/collect`.
The browser SDK and shared bootstrap bundle are served from
`https://telemetry.wayl.one/assets/`.

## Static-site platform

New sites from `templates/static-site` enable telemetry by default. The
Copier template writes these keys into `site-config.yaml`:

```yaml
  TELEMETRY_ENABLED: "true"
  TELEMETRY_APP_NAME: caps
  TELEMETRY_ENVIRONMENT: production
  TELEMETRY_VERSION: unknown
```

Use the same `TELEMETRY_APP_NAME` for production and development. Set the
environment to `production`, `preview`, or `development`. Use a Git SHA or
release value when the publisher provides one. Otherwise, use `unknown`.

To disable telemetry for one site, set `TELEMETRY_ENABLED` to `"false"`.
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
Waylon-owned domains. On localhost, telemetry stays off unless the app passes
`allowLocalhost: true` to `setupFaro`.

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

The first static-site canaries are `caps-dev`, `emboss-dev`, `strip-dev`, and
`voice-reverse-dev`. Production and remaining static-site hosts stay disabled
until that canary cohort passes. See
[`browser-telemetry-inventory.md`](browser-telemetry-inventory.md) for live
host ownership, application family, and current status.
