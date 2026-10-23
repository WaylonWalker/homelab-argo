---
title: "Homelab documentation"
description: "Operational notes, architecture records, and runbooks for the WaylonWalker homelab."
slug: "/"
published: true
template: page
---

# Homelab docs

This site collects the operational notes and runbooks maintained in the
[`homelab-argo` repository](https://github.com/WaylonWalker/homelab-argo).

Choose a task to get a focused feed of runbooks and reference pages.

## Start with a task

::: md-grid {data-columns="2"}

:::: md-card
### [Operate](/operate/)

Run services, check behavior, and perform routine maintenance.

::::

:::: md-card
### [Recover](/recover/)

Restore workloads, validate backups, and handle recovery work.

::::

:::: md-card
### [Understand](/understand/)

Explore architecture, inventories, and the network map.

::::

:::: md-card
### [Change](/change/)

Plan and roll out infrastructure changes.

::::

:::

## Network map

[Explore the issue #174 dependency map](/security/issue-174-network-map/) for a
first-pass view of configured service connections. The map labels configured
edges; it does not claim to show all live traffic.

## Related references

- [Security inventory: issue 174](/security/issue-174-inventory/)
- [Storage architecture](/storage-architecture/)
- [Cluster maintenance plan](/cluster-maintenance-2026-10-10/)
