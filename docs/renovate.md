# Renovate for homelab-argo

This repository uses [Renovate](https://docs.renovatebot.com/) to propose version updates in Git. Renovate does **not** deploy directly to the cluster; merging Git changes may trigger Argo CD automated reconciliation.

## Enable the hosted bot

1. Install the [Mend Renovate GitHub App](https://github.com/apps/renovate) under the WaylonWalker account.
2. Choose **Only select repositories**, then select **homelab-argo**.
3. Review the requested GitHub App permissions and install.
4. After the first Renovate run, review the Dependency Dashboard issue and open PRs.

The app installation must be approved by a repository owner; adding `renovate.json` alone does not start Renovate.

## Policy

- Renovate opens normal update PRs, but never auto-merges them.
- Major-version updates must be approved via the Dependency Dashboard before a PR is created.
- Updates to critical infrastructure and stateful components require dashboard approval even for minor/patch changes.
- Keep only a small backlog of active PRs (`prConcurrentLimit: 5`).
- Images from `registry.wayl.one` stay under the existing application build/deployment pipeline.
- Disabled resources, historical backup manifests, upgrade plans, and the vendored cert-manager release manifest are excluded.
- Native Argo CD, Kubernetes, Helm, Docker, and other supported managers discover version references. Some custom manifests may require additional extractors.

## Deployment safety

An approved or merged PR is **not** a guarantee of compatibility. Argo CD can auto-sync merged changes immediately.

For Longhorn, CNPG, cert-manager, Argo CD, DNS, networking, and other stateful components: read upstream upgrade notes, ensure current tested backups, check CRD/API compatibility, and coordinate a maintenance window as needed. A config validator workflow checks Renovate JSON configuration only; it does not test cluster health or ensure Helm charts are deployable.

Node/OS upgrades, k3s runtime upgrades, and whole vendored upstream manifest bundles require separate procedures.
