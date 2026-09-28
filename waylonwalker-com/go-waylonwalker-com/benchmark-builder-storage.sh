#!/usr/bin/env bash
set -euo pipefail

namespace="${NAMESPACE:-go-waylonwalker-com-notes}"
selector="${SELECTOR:-service=go-waylonwalker-com-notes-builder-admin}"
files="${FILES:-3500}"
bytes="${BYTES_PER_FILE:-16384}"

pod="$(kubectl -n "$namespace" get pod -l "$selector" -o jsonpath='{.items[0].metadata.name}')"
if [[ -z "$pod" ]]; then
  echo "no Builder Admin pod found for $namespace / $selector" >&2
  exit 1
fi

echo "Builder Admin pod: $pod"
echo "Synthetic workload: $files files x $bytes bytes"
echo

kubectl -n "$namespace" exec "$pod" -- sh -ceu '
  echo "== mount identity =="
  for path in /data/source /data/site /data/cache /tmp; do
    if [ -e "$path" ]; then
      echo "-- $path"
      df -T "$path" 2>/dev/null || df "$path"
      stat -f "$path" 2>/dev/null || true
    fi
  done
' sh

bench_path() {
  local path="$1"
  echo
  echo "== benchmark: $path =="
  kubectl -n "$namespace" exec "$pod" -- env BENCH_ROOT="$path" FILES="$files" BYTES_PER_FILE="$bytes" sh -ceu '
    root="$BENCH_ROOT/markata-builder-storage-bench-$$"
    mkdir -p "$root"
    trap '\''rm -rf "$root"'\'' EXIT

    payload="$root/.payload"
    dd if=/dev/zero of="$payload" bs="$BYTES_PER_FILE" count=1 status=none

    start=$(date +%s%N)
    i=0
    while [ "$i" -lt "$FILES" ]; do
      d="$root/$((i / 100))/post-$i"
      mkdir -p "$d"
      cp "$payload" "$d/index.html"
      i=$((i + 1))
    done
    end=$(date +%s%N)
    write_ns=$((end - start))

    start=$(date +%s%N)
    find "$root" -type f ! -name .payload -exec cat {} \; >/dev/null
    end=$(date +%s%N)
    read_ns=$((end - start))

    start=$(date +%s%N)
    find "$root" -mindepth 1 ! -name .payload -delete
    end=$(date +%s%N)
    delete_ns=$((end - start))

    awk -v files="$FILES" -v bytes="$BYTES_PER_FILE" -v w="$write_ns" -v r="$read_ns" -v d="$delete_ns" '\''BEGIN {
      mib=(files*bytes)/(1024*1024);
      ws=w/1000000000; rs=r/1000000000; ds=d/1000000000;
      printf "write:  %.3fs  %.1f files/s  %.1f MiB/s\\n", ws, files/ws, mib/ws;
      printf "read:   %.3fs  %.1f files/s  %.1f MiB/s\\n", rs, files/rs, mib/rs;
      printf "delete: %.3fs  %.1f files/s\\n", ds, files/ds;
    }'\''
  ' sh
}

bench_path /data/site
bench_path /tmp

if kubectl -n "$namespace" exec "$pod" -- test -d /data/cache 2>/dev/null; then
  bench_path /data/cache
fi

echo
echo "This benchmark is synthetic. Compare its ratios with Builder Admin build metrics"
echo "before changing storage or MARKATA_GO_CONCURRENCY."
