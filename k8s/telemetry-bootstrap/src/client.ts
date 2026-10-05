import {
  ErrorsInstrumentation,
  initializeFaro,
  InternalLoggerLevel,
  NavigationInstrumentation,
  PerformanceInstrumentation,
  SessionInstrumentation,
  type TransportItem,
  type Faro,
  ViewInstrumentation,
  WebVitalsInstrumentation,
} from '@grafana/faro-web-sdk';
import { TracingInstrumentation } from '@grafana/faro-web-tracing';

const endpoint = 'https://telemetry.wayl.one/collect';
const secretLikeValue = /\b(password|passwd|authorization|bearer|cookie|set-cookie|api[_-]?key|access[_-]?token|refresh[_-]?token|secret)\b\s*[:=]\s*[^\s&,;]+/gi;
const urlLikeValue = /https?:\/\/[^\s"'<>]+/gi;
const firstPartyOrigins = /^https?:\/\/(?:[a-z0-9-]+\.)?(?:waylonwalker\.com|wayl\.one|wyattbubbylee\.com|markata\.dev|rhiannonwalker\.com)(?::\d+)?(?:\/|$)/i;

export type FaroOptions = {
  appName: string;
  version?: string;
  environment: 'production' | 'preview' | 'development';
  allowLocalhost?: boolean;
};

declare global {
  interface Window {
    __waylonFaroInitialized?: boolean;
    __waylonFaro?: Faro;
    setupWaylonFaro?: (options: FaroOptions) => Faro | undefined;
  }
}

function scrubURL(value: string): string {
  try {
    const parsed = new URL(value, window.location.origin);
    parsed.search = '';
    parsed.hash = '';
    return /^[a-z][a-z\d+.-]*:/i.test(value) ? parsed.toString() : parsed.pathname;
  } catch {
    return value;
  }
}

function scrubValue(value: unknown, key = ''): unknown {
  if (typeof value === 'string') {
    const cleaned = key.toLowerCase().includes('url') || key.toLowerCase().includes('href') || key.toLowerCase().includes('filename')
      ? scrubURL(value)
      : value.replace(urlLikeValue, (url) => scrubURL(url));
    return cleaned.replace(secretLikeValue, '$1=[redacted]');
  }
  if (Array.isArray(value)) return value.map((item) => scrubValue(item));
  if (value && typeof value === 'object') {
    for (const [childKey, childValue] of Object.entries(value)) {
      (value as Record<string, unknown>)[childKey] = scrubValue(childValue, childKey);
    }
  }
  return value;
}

function scrubBeforeSend(item: TransportItem): TransportItem {
  scrubValue(item.meta);
  scrubValue(item.payload);
  return item;
}

export function setupFaro(options: FaroOptions): Faro | undefined {
  if (window.__waylonFaroInitialized) return window.__waylonFaro;
  if (!options.appName || !options.environment) return undefined;
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
  if (local && !options.allowLocalhost) return undefined;

  window.__waylonFaroInitialized = true;
  try {
    window.__waylonFaro = initializeFaro({
      url: endpoint,
      app: {
        name: options.appName,
        version: options.version || 'unknown',
        environment: options.environment,
      },
      instrumentations: [
        // Do not capture console arguments, automatic clicks, or CSP reports.
        // They can include form values, prompts, tokens, or page contents.
        new ErrorsInstrumentation(),
        new WebVitalsInstrumentation(),
        new PerformanceInstrumentation(),
        new SessionInstrumentation(),
        new ViewInstrumentation(),
        new NavigationInstrumentation(),
        new TracingInstrumentation({
          instrumentationOptions: {
            propagateTraceHeaderCorsUrls: [firstPartyOrigins],
          },
        }),
      ],
      beforeSend: scrubBeforeSend,
      internalLoggerLevel: InternalLoggerLevel.OFF,
    });
    return window.__waylonFaro;
  } catch {
    // Telemetry must never affect page startup. Permit another attempt if the
    // SDK itself failed during initialization.
    window.__waylonFaroInitialized = false;
    return undefined;
  }
}

window.setupWaylonFaro = setupFaro;
