---
title: 'Homelab docs'
description: 'Runbooks and maps for the homelab, from routine operations to recovery.'
slug: '/'
published: true
template: page
---

<section class="docs-home-hero" aria-labelledby="docs-home-title">
  <div class="docs-home-copy">
    <p class="docs-home-eyebrow">WAYLON WALKER'S HOMELAB</p>
    <h1 id="docs-home-title">A small homelab,<br><span>built by <del>hand</del> <em>agents.</em></span></h1>
    <p class="docs-home-deck">A working map of the services, storage, and recovery paths that keep this homelab running.</p>
    <p class="docs-home-note">Runbooks, diagrams, and notes from a raccoon cloud in the basement.</p>
  </div>
  <figure class="docs-home-art">
    <img src="/raccoon.svg" alt="A friendly raccoon wearing a glowing Kubernetes visor above homelab server hardware." width="1200" height="875" fetchpriority="high">
    <figcaption>rescued hardware, surprisingly still running.</figcaption>
  </figure>
</section>

## Things that live here.

Pick a task to browse the notes and runbooks.

::: md-grid {data-columns="2" data-gap="lg"}

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

Explore architecture, inventories, and the [network map](/security/issue-174-network-map/).

::::

:::: md-card
### [Change](/change/)

Plan and roll out infrastructure changes.

::::

:::
