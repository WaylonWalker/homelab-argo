#!/usr/bin/env bash
set -euo pipefail

mc_version="${1:-1.21.1}"
loader="${2:-neoforge}"

# wanted=(
#   create
#   create-aeronautics
#   tradeworks
#   geckolib
#   natures-compass
#   kotlin-for-forge
#   sable
#
#   farmers-delight
#   waystones
#   jei
#   balm
#
#   effortless
#   waystones
#
#   useful-backpacks
# )

wanted=(
create
create-aeronautics
create-deco
create-deep-seas
create-encased
create-goggles
create-cobblestone
create-central-kitchen
create-connected
create-copycats+
create-dragons-plus
create-enchantment-industry
create-pocket-factory
create-power-grid
create-radars
create-vibrant-vaults
design-n-decor
ftb-library
ftb-ultimine
just-enough-items
sable
sophisticated-backpacks
sophisticated-core
xaeros-minimap
xaeros-world-map
aero_copycats
)


echo "            - name: MODRINTH_DOWNLOAD_DEPENDENCIES"
echo '              value: "required"'
echo "            - name: MODRINTH_PROJECTS"
echo "              value: |"

declare -A seen

for slug in "${wanted[@]}"; do
  if [[ -n "${seen[$slug]:-}" ]]; then
    continue
  fi
  seen["$slug"]=1

  json="$(
    curl -fsSG "https://api.modrinth.com/v2/project/${slug}/version" \
      --data-urlencode "game_versions=[\"${mc_version}\"]" \
      --data-urlencode "loaders=[\"${loader}\"]"
  )"

  ref="$(jq -r 'first(.[]?) | if . then "\(.project_id):\(.id)" else empty end' <<<"$json")"
  version_number="$(jq -r 'first(.[]?) | if . then .version_number else empty end' <<<"$json")"

  if [[ -z "$ref" ]]; then
    printf "                # NO MATCH: %s for Minecraft %s / %s\n" "$slug" "$mc_version" "$loader"
    continue
  fi

  project_id="${ref%%:*}"
  project_json="$(curl -fsS "https://api.modrinth.com/v2/project/${project_id}")"

  title="$(jq -r '.title' <<<"$project_json")"
  real_slug="$(jq -r '.slug' <<<"$project_json")"

  printf "                # %s (%s) - %s\n" "$title" "$real_slug" "$version_number"
  printf "                %s\n" "$ref"
done
