#!/usr/bin/env bash
set -euo pipefail

manifest="${1:-cloudflared/cloudflared.yaml}"
image="cloudflare/cloudflared"

latest="$(curl -fsSL https://api.github.com/repos/cloudflare/cloudflared/releases/latest \
  | jq -er '.tag_name | ltrimstr("")')"

if [[ ! "$latest" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  printf 'Unexpected cloudflared release tag: %s\n' "$latest" >&2
  exit 1
fi

current="$(sed -n 's/^[[:space:]]*image: cloudflare\/cloudflared:\(.*\)$/\1/p' "$manifest")"
if [[ -z "$current" ]]; then
  printf 'Could not find cloudflared image in %s\n' "$manifest" >&2
  exit 1
fi

if [[ "$current" == "$latest" ]]; then
  printf 'cloudflared is already pinned to %s\n' "$current"
  exit 0
fi

sed -i "s#\(image: $image:\).*#\1$latest#" "$manifest"
printf 'Updated cloudflared %s -> %s in %s\n' "$current" "$latest" "$manifest"
