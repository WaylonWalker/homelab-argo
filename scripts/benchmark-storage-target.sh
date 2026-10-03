#!/bin/sh
# Run inside a disposable pod with fio and jq. TARGET must be a mounted
# filesystem, never a raw block device. Results describe this filesystem and
# its live workload, not the maximum throughput of an individual drive.
set -eu

: "${TARGET:?set TARGET to an existing, writable mount}"
seq_size="${SEQ_SIZE:-512m}"
seq_runs="${SEQ_RUNS:-3}"
sync_seconds="${SYNC_SECONDS:-15}"
case "$seq_size" in
  *m) seq_mib=${seq_size%m} ;;
  *) printf 'SEQ_SIZE must use integer MiB (for example, 512m)\n' >&2; exit 1 ;;
esac
case "$seq_mib" in
  ''|*[!0-9]*) printf 'SEQ_SIZE must use integer MiB\n' >&2; exit 1 ;;
esac
test "$seq_mib" -ge 16 && test "$seq_mib" -le 1024 || {
  printf 'SEQ_SIZE must be between 16m and 1024m\n' >&2; exit 1;
}
seq_bytes=$((seq_mib * 1048576))
case "$seq_runs:$sync_seconds" in
  *[!0-9:]*|:*|*:) printf 'SEQ_RUNS and SYNC_SECONDS must be positive integers\n' >&2; exit 1 ;;
esac
test "$seq_runs" -ge 1 && test "$seq_runs" -le 10 || {
  printf 'SEQ_RUNS must be between 1 and 10\n' >&2; exit 1;
}
test "$sync_seconds" -ge 1 && test "$sync_seconds" -le 60 || {
  printf 'SYNC_SECONDS must be between 1 and 60\n' >&2; exit 1;
}
# Resolve symlinks and .. before enforcing the disposable-target boundary.
TARGET=$(CDPATH= cd -- "$TARGET" && pwd -P)

case "$TARGET" in
  /bench/*|/tmp) ;;
  *) printf 'refusing target outside /bench or /tmp: %s\n' "$TARGET" >&2; exit 1 ;;
esac
test -d "$TARGET" && test -w "$TARGET"
free_kib=$(df -Pk "$TARGET" | awk 'NR == 2 { print $4 }')
test "$free_kib" -gt "$((seq_mib * 1024 + 1048576))" || {
  printf 'target needs test size plus 1 GiB of free space\n' >&2; exit 1;
}
command -v fio >/dev/null
command -v jq >/dev/null
timestamp=$(date +%s%N)
test "${#timestamp}" -eq 19 || { printf 'nanosecond timestamps are required\n' >&2; exit 1; }

# mktemp creates exactly one private directory under the requested mount.
work=$(mktemp -d "$TARGET/disk-bench.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
printf 'target=%s seq_size=%s seq_runs=%s sync_seconds=%s\n' "$TARGET" "$seq_size" "$seq_runs" "$sync_seconds"
df -h "$TARGET"

run_fio() {
  start=$(date +%s%N)
  result=$(fio "$@" --output-format=json)
  stop=$(date +%s%N)
  printf '%s\n' "$result" | jq -e '.jobs | all(.error == 0)' >/dev/null
  wall_ns=$((stop - start))
  test "$wall_ns" -gt 0
  printf '%s\n' "$result" | jq -r --argjson wall_ns "$wall_ns" --argjson bytes "$seq_bytes" '
    .jobs[0] as $j |
    if $j.jobname == "seq-write" then
      "seq-write wall_s=\(($wall_ns / 1000000000) | tostring) persisted_MiB_s=\((($bytes / 1048576) * 1000000000 / $wall_ns) | tostring) fio_MiB_s=\(($j.write.bw_bytes / 1048576) | tostring)"
    elif $j.jobname == "seq-read" then
      "seq-read wall_s=\(($wall_ns / 1000000000) | tostring) fio_MiB_s=\(($j.read.bw_bytes / 1048576) | tostring)"
    else
      "sync-4k iops=\($j.write.iops) p99_ms=\((($j.write.clat_ns.percentile["99.000000"] // 0) / 1000000) | tostring)"
    end'
}

i=1
while [ "$i" -le "$seq_runs" ]; do
  printf 'trial=%s\n' "$i"
  run_fio --name=seq-write --filename="$work/seq.dat" --size="$seq_size" \
    --rw=write --bs=1m --ioengine=sync --direct=1 --fallocate=none \
    --buffer_compress_percentage=0 --end_fsync=1
  run_fio --name=seq-read --filename="$work/seq.dat" --size="$seq_size" \
    --rw=read --bs=1m --ioengine=sync --direct=1 --invalidate=1 --readonly
  rm -- "$work/seq.dat"
  i=$((i + 1))
done

run_fio --name=sync-4k --filename="$work/random.dat" --size=64m \
  --rw=randwrite --bs=4k --ioengine=sync --direct=0 --sync=1 \
  --fallocate=none --time_based=1 --runtime="$sync_seconds" --ramp_time=3
