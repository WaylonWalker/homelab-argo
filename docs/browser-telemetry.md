# Browser telemetry

The shared Grafana Faro endpoint is:

```text
https://telemetry.wayl.one/collect
```

The Alloy Faro receiver sends browser logs and errors to Loki and frontend
traces to Tempo. Use a stable application name and include the release version
and environment so the receiver can apply per-application rate limits.

For a Vite application, install the Faro Web SDK and its tracing package:

```sh
npm install @grafana/faro-web-sdk @grafana/faro-web-tracing
```

Initialize Faro once in the browser entry point:

```ts
import { getWebInstrumentations, initializeFaro } from '@grafana/faro-web-sdk';
import { TracingInstrumentation } from '@grafana/faro-web-tracing';

initializeFaro({
  url: 'https://telemetry.wayl.one/collect',
  app: {
    name: 'lantern-table',
    version: import.meta.env.VITE_GIT_SHA,
    environment: import.meta.env.VITE_APP_ENV,
  },
  instrumentations: [
    ...getWebInstrumentations({ captureConsole: true }),
    new TracingInstrumentation(),
  ],
});
```

`getWebInstrumentations` captures JavaScript errors, unhandled promise
rejections, web vitals, and browser metadata. Set `VITE_APP_ENV` to
`production`, `preview`, or `development` for each build.
`TracingInstrumentation` is provided by
`@grafana/faro-web-tracing` and instruments browser network requests.

The receiver uses public `.map` files during this first phase. Avoid publishing
source maps if the source must remain private. A later deployment can upload
maps to MinIO under `/sourcemaps/<app>/<git-sha>/` and configure Alloy to read
them privately.

Do not add credentials or sensitive form, query, header, cookie, chat, or prompt
data to Faro events. Anything included in browser JavaScript is public.
