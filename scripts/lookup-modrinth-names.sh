#!/usr/bin/env bash
set -euo pipefail

ids=(
  LNytGWDc:n7NADxiG
  oWaK0Q19:FIeWE7UC
  gnOpd0sq:ZzZU3gZb
  8BmcQJ2H:gFmrC8Ru
  fPetb5Kh:nFniEtJV
  ordsPcFz:NrSebcsG
  T9PomCSv:ZYLSN31S
)

for ref in "${ids[@]}"; do
  project_id="${ref%%:*}"
  version_id="${ref##*:}"

  version_json="$(
    curl -fsS "https://api.modrinth.com/v2/version/${version_id}"
  )"

  project_json="$(
    curl -fsS "https://api.modrinth.com/v2/project/${project_id}"
  )"

  title="$(jq -r '.title' <<<"$project_json")"
  slug="$(jq -r '.slug' <<<"$project_json")"
  version_name="$(jq -r '.name' <<<"$version_json")"
  version_number="$(jq -r '.version_number' <<<"$version_json")"
  game_versions="$(jq -r '.game_versions | join(",")' <<<"$version_json")"
  loaders="$(jq -r '.loaders | join(",")' <<<"$version_json")"

  printf '%s\n' "----------------------------------------"
  printf 'ref:            %s\n' "$ref"
  printf 'title:          %s\n' "$title"
  printf 'slug:           %s\n' "$slug"
  printf 'version_name:   %s\n' "$version_name"
  printf 'version_number: %s\n' "$version_number"
  printf 'game_versions:  %s\n' "$game_versions"
  printf 'loaders:        %s\n' "$loaders"
done
