# Markata-Go Faro feature plan

Markata-Go renders shared `<head>` content through its `HeadConfig`. The
default theme renders `config.head.text`, `config.head.meta`,
`config.head.link`, and `config.head.script`. `ScriptTag` only stores `src`, so
it cannot add the Faro app, environment, and version attributes.

Add a native `[markata-go.telemetry.faro]` config section:

```toml
[markata-go.telemetry.faro]
enabled = true
endpoint = "https://telemetry.wayl.one/collect"
bootstrap = "https://telemetry.wayl.one/assets/faro-bootstrap.js"
app_name = "waylonwalker-com"
environment = "production"
version = "unknown"
```

The feature should add one escaped script element to generated HTML head
content. It should use the shared bootstrap and stable app name. The version
must use a release value when the build provides one. Otherwise, it must use
`unknown`.

The build environment must override the configured environment for preview
builds. Preview output must use `preview`; production output must use
`production`. App names must remain the same across those environments.

The feature must preserve existing custom `head.text` and head tags. It must
not change RSS, JSON, text, or other non-HTML output. It must use the same
privacy behavior as the shared bootstrap. It must add an explicit
`enabled = false` opt-out for admin, sensitive, or unusual sites.

The implementation belongs in Markata-Go because HTML generation owns the
`<head>`. The homelab nginx filter is not the long-term Markata integration.
Markata-Go requires a tracked GitHub issue and a spec update before code
changes. No Markata-Go source was changed in this pass.

The existing Argo apps that use the Markata-Go Helm chart are
`go.waylonwalker.com`, `waylonwalker.com`, `rhiannonwalker.com`, and
`wyattbubbylee.com`. Their builder-admin and webhook hosts are not browser-site
targets. `recipes.waylonwalker.com` also uses the Markata-Go builder, but it
has a separate static deployment manifest.
