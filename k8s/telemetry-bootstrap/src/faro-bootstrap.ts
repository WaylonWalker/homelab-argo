import { setupFaro, type FaroOptions } from './client.js';

const sourceScript = document.currentScript instanceof HTMLScriptElement ? document.currentScript : null;

if (sourceScript) {
  const enabled = sourceScript.dataset.faroEnabled !== 'false';
  const appName = sourceScript.dataset.faroApp || '';
  const environmentValue = sourceScript.dataset.faroEnvironment;
  const environment = ['production', 'preview', 'development'].includes(environmentValue)
    ? environmentValue as FaroOptions['environment']
    : undefined;
  const version = sourceScript.dataset.faroVersion || 'unknown';
  const allowLocalhost = sourceScript.dataset.faroLocal === 'true';

  if (enabled && environment) setupFaro({ appName, version, environment, allowLocalhost });
}
