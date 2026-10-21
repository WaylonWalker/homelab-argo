#!/usr/bin/env python3
"""Measure isolated issue 143 builder canaries and public site TTFB."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import time
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
ARMS = {
    "a": {
        "namespace": "waylonwalker-com-prod-nvme-ab-a-notes",
        "project": "waylonwalker-com-prod-nvme-ab-a",
    },
    "b": {
        "namespace": "waylonwalker-com-prod-nvme-ab-b-notes",
        "project": "waylonwalker-com-prod-nvme-ab-b",
    },
}
PROD_NAMESPACE = "waylonwalker-com-prod-notes"
PROD_DEPLOYMENT = "waylonwalker-com-prod-notes-builder-admin"
SOURCE_URL = "https://waylonwalker.com"


def run(command: list[str], *, timeout: int = 30) -> str:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout.strip()


def kubectl(namespace: str, *args: str, timeout: int = 30) -> str:
    return run(["kubectl", "-n", namespace, *args], timeout=timeout)


def builder_pod(arm: str) -> str:
    config = ARMS[arm]
    selector = f"service={config['project']}-notes-builder-admin"
    pods = json.loads(
        kubectl(config["namespace"], "get", "pods", "-l", selector, "-o", "json")
    )["items"]
    for pod in pods:
        if pod.get("status", {}).get("phase") == "Running":
            return pod["metadata"]["name"]
    raise RuntimeError(f"arm {arm.upper()} has no running Builder Admin pod")


def builder_exec(arm: str, *args: str, timeout: int = 30) -> str:
    pod = builder_pod(arm)
    return kubectl(
        ARMS[arm]["namespace"], "exec", pod, "--", *args, timeout=timeout
    )


def read_state(arm: str) -> dict:
    raw = builder_exec(arm, "cat", "/data/site/.builder-admin/state.json")
    return json.loads(raw)


def prod_state() -> dict:
    pod = run(
        [
            "kubectl",
            "-n",
            PROD_NAMESPACE,
            "get",
            "pods",
            "-l",
            f"service={PROD_DEPLOYMENT}",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ]
    )
    raw = kubectl(
        PROD_NAMESPACE,
        "exec",
        pod,
        "--",
        "cat",
        "/data/site/.builder-admin/state.json",
        timeout=30,
    )
    return json.loads(raw)


def trigger(arm: str, delivery: str) -> set[str]:
    prior_builds = {build.get("id") for build in read_state(arm).get("builds", [])}
    pod = builder_pod(arm)
    enqueue_code = r'''import os, sys, urllib.error, urllib.parse, urllib.request
identity = sys.argv[1]
base = "http://" + os.environ["POD_IP"] + ":8080/"
identity_headers = {"X-Hlab-User-Id": identity}
page = urllib.request.urlopen(urllib.request.Request(base, headers=identity_headers), timeout=15)
cookie = page.headers.get("Set-Cookie", "").split(";", 1)[0]
if not cookie or "=" not in cookie:
    raise SystemExit("Builder Admin did not issue a CSRF cookie")
token = cookie.split("=", 1)[1]
data = urllib.parse.urlencode({"csrf_token": token}).encode()
headers = {
    **identity_headers,
    "Origin": "https://issue-143.invalid",
    "Sec-Fetch-Site": "same-origin",
    "Cookie": cookie,
    "Content-Type": "application/x-www-form-urlencoded",
}
request = urllib.request.Request(base + "api/builds", data=data, headers=headers, method="POST")
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None
try:
    response = urllib.request.build_opener(NoRedirect).open(request, timeout=15)
    status = response.status
except urllib.error.HTTPError as error:
    status = error.code
if status != 303:
    raise SystemExit("Builder Admin returned HTTP " + str(status))
print("enqueued")
'''
    response = kubectl(
        ARMS[arm]["namespace"],
        "exec",
        pod,
        "--",
        "python3",
        "-c",
        enqueue_code,
        delivery,
        timeout=30,
    )
    if response != "enqueued":
        raise RuntimeError(f"arm {arm.upper()} manual build was not enqueued")
    return prior_builds


def wait_for_build(arm: str, delivery: str, prior_builds: set[str], timeout: int) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = read_state(arm)
        for build in state.get("builds", []):
            if build.get("actor_id") == delivery or (
                build.get("id") not in prior_builds
                and build.get("trigger_type") == "manual-ui"
            ):
                return build
        running = state.get("running") or {}
        if running.get("actor_id") == delivery or running.get("id") not in prior_builds:
            build_id = running.get("id")
            if build_id:
                for build in state.get("builds", []):
                    if build.get("id") == build_id:
                        return build
        time.sleep(5)
    raise TimeoutError(f"arm {arm.upper()} build {delivery} did not finish in {timeout}s")


def read_container_stats(arm: str) -> dict:
    pod = builder_pod(arm)
    result: dict = {"pod": pod}
    for name, path in (
        ("cpu", "/sys/fs/cgroup/cpu.stat"),
        ("io", "/sys/fs/cgroup/io.stat"),
    ):
        try:
            result[name] = kubectl(ARMS[arm]["namespace"], "exec", pod, "--", "cat", path)
        except subprocess.CalledProcessError:
            result[name] = None
    return result


def read_node_stats() -> dict:
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "falcon3",
        "sh",
        "-c",
        "printf 'STAT '; head -1 /proc/stat; printf 'LOAD '; cat /proc/loadavg; "
        "printf 'DISK '; cat /sys/block/nvme0n1/stat; printf 'SPACE '; "
        "df -B1 /var | awk 'NR==2 {print $2,$3,$4,$5}'; "
        "printf 'INODES '; df -i /var | awk 'NR==2 {print $2,$3,$4,$5}'",
    ]
    output = run(command, timeout=20)
    data: dict = {}
    for line in output.splitlines():
        key, _, value = line.partition(" ")
        data[key.lower()] = value.strip()
    return data


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def production_overlap(start: datetime, finish: datetime) -> bool:
    state = prod_state()
    for build in state.get("builds", []):
        began = parse_time(build.get("started_at"))
        ended = parse_time(build.get("finished_at"))
        if began and began <= finish and (ended is None or ended >= start):
            return True
    running = state.get("running") or {}
    began = parse_time(running.get("started_at"))
    return bool(began and began <= finish)


def wait_for_prod_idle(timeout: int = 1800) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = prod_state()
        if not state.get("running") and not state.get("queue"):
            return
        time.sleep(10)
    raise TimeoutError("production Builder Admin did not become idle")


def node_delta(before: dict, after: dict) -> dict:
    result: dict = {}
    try:
        start = [int(value) for value in before["stat"].split()[1:]]
        stop = [int(value) for value in after["stat"].split()[1:]]
        delta = [max(0, end - begin) for begin, end in zip(start, stop)]
        total = sum(delta)
        result["cpu_busy_percent"] = round(
            100 * (total - delta[3] - delta[4]) / total, 2
        ) if total else None
        result["iowait_percent"] = round(100 * delta[4] / total, 2) if total else None
    except (KeyError, ValueError, IndexError):
        result["cpu_busy_percent"] = None
        result["iowait_percent"] = None
    try:
        disk_start = [int(value) for value in before["disk"].split()]
        disk_stop = [int(value) for value in after["disk"].split()]
        result["nvme_read_bytes"] = max(0, disk_stop[2] - disk_start[2]) * 512
        result["nvme_written_bytes"] = max(0, disk_stop[6] - disk_start[6]) * 512
    except (KeyError, ValueError, IndexError):
        result["nvme_read_bytes"] = None
        result["nvme_written_bytes"] = None
    result["load_before"] = before.get("load")
    result["load_after"] = after.get("load")
    result["space_before"] = before.get("space")
    result["space_after"] = after.get("space")
    result["inodes_before"] = before.get("inodes")
    result["inodes_after"] = after.get("inodes")
    return result


def build_log(arm: str, build: dict) -> str:
    path = build.get("log_path")
    if not path:
        return ""
    try:
        return builder_exec(
            arm,
            "cat",
            f"/data/site/.builder-admin/logs/{path}",
            timeout=60,
        )
    except subprocess.CalledProcessError:
        return ""


def publication_counters(log: str) -> list[str]:
    markers = (
        "reusing build work from current release",
        "incremental publication:",
        "linked_files=",
        "copied_files=",
        "copied_bytes=",
        "compared_bytes=",
        "cached_source_hashes=",
        "cached_release_hashes=",
        "manifest_saved=",
    )
    return [
        line.strip()
        for line in log.splitlines()
        if any(marker in line for marker in markers)
    ]


def public_sample_loop(stop: threading.Event, samples: list[dict]) -> None:
    url = SOURCE_URL + "/"
    while not stop.is_set():
        started = datetime.now(timezone.utc).isoformat()
        try:
            result = run(
                [
                    "curl",
                    "--silent",
                    "--show-error",
                    "--output",
                    "/dev/null",
                    "--max-time",
                    "15",
                    "--write-out",
                    "%{http_code} %{time_starttransfer}",
                    url,
                ],
                timeout=20,
            )
            status_text, seconds_text = result.split()
            samples.append(
                {
                    "measured_at": started,
                    "status": int(status_text),
                    "ttfb_seconds": float(seconds_text),
                }
            )
        except (subprocess.CalledProcessError, ValueError):
            samples.append({"measured_at": started, "status": 0, "ttfb_seconds": None})
        stop.wait(5)


def reset_cold_state(arm: str) -> None:
    state = read_state(arm)
    if state.get("running") or state.get("queue"):
        raise RuntimeError(f"arm {arm.upper()} is busy; refusing to clear canary cache")
    builder_exec(
        arm,
        "sh",
        "-c",
        "rm -rf /data/site/.build-work /data/cache/xdg && "
        "mkdir -p /data/site/.build-work /data/cache/xdg",
        timeout=60,
    )


def build_once(arm: str, kind: str, order: int, timeout: int) -> dict:
    wait_for_prod_idle()
    state = read_state(arm)
    if state.get("running") or state.get("queue"):
        raise RuntimeError(f"arm {arm.upper()} is busy before the next build")
    delivery = f"issue-143-{kind}-{order}-{uuid.uuid4()}"
    before = read_node_stats()
    container_before = read_container_stats(arm)
    started = datetime.now(timezone.utc)
    prior_builds = trigger(arm, delivery)
    ttfb_stop = threading.Event()
    ttfb_samples: list[dict] = []
    sampler = threading.Thread(
        target=public_sample_loop, args=(ttfb_stop, ttfb_samples), daemon=True
    )
    sampler.start()
    try:
        build = wait_for_build(arm, delivery, prior_builds, timeout)
    finally:
        ttfb_stop.set()
        sampler.join(timeout=20)
    finished = datetime.now(timezone.utc)
    container_after = read_container_stats(arm)
    after = read_node_stats()
    prod_overlap = production_overlap(started, finished)
    complete_ms = sum(
        int(build.get(field) or 0)
        for field in ("prepare_ms", "build_ms", "promote_ms")
    )
    log = build_log(arm, build)
    counters = publication_counters(log)
    return {
        "arm": arm.upper(),
        "kind": kind,
        "order": order,
        "delivery": delivery,
        "build_id": build.get("id"),
        "status": build.get("status"),
        "source_commit": build.get("source_commit"),
        "trigger_type": build.get("trigger_type"),
        "started_at": build.get("started_at"),
        "finished_at": build.get("finished_at"),
        "queue_wait_ms": build.get("queue_wait_ms"),
        "prepare_ms": build.get("prepare_ms"),
        "build_ms": build.get("build_ms"),
        "promote_ms": build.get("promote_ms"),
        "prune_ms": build.get("prune_ms"),
        "total_ms": build.get("total_ms"),
        "complete_ms": complete_ms,
        "became_live": build.get("became_live"),
        "release_id": build.get("release_id"),
        "perf_summary": build.get("perf_summary"),
        "publication_counters": counters,
        "reuse_hit": any("reusing build work from current release" in line for line in counters),
        "incremental_publication": any("incremental publication:" in line for line in counters),
        "public_ttfb_samples": ttfb_samples,
        "public_ttfb": {
            "n": len([sample for sample in ttfb_samples if sample.get("ttfb_seconds") is not None]),
            "p50_seconds": statistics.median(
                [sample["ttfb_seconds"] for sample in ttfb_samples if sample.get("ttfb_seconds") is not None]
            ) if any(sample.get("ttfb_seconds") is not None for sample in ttfb_samples) else None,
            "p95_seconds": percentile(
                [sample["ttfb_seconds"] for sample in ttfb_samples if sample.get("ttfb_seconds") is not None],
                0.95,
            ) if any(sample.get("ttfb_seconds") is not None for sample in ttfb_samples) else None,
            "five_xx": sum(500 <= int(sample.get("status") or 0) <= 599 for sample in ttfb_samples),
        },
        "production_overlap": prod_overlap,
        "node_delta": node_delta(before, after),
        "node_before": before,
        "node_after": after,
        "container_before": container_before,
        "container_after": container_after,
    }


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


def run_builds(args: argparse.Namespace) -> int:
    output = Path(args.output)
    if output.exists() and not args.append:
        raise RuntimeError(f"output exists; choose another file or pass --append: {output}")

    # Prime both arms before recording warm builds.
    prime_records = []
    for index, arm in enumerate(("a", "b"), start=1):
        record = build_once(arm, "prime", index, args.build_timeout)
        append_jsonl(output, record)
        prime_records.append(record)
        print(json.dumps({"prime": record}, sort_keys=True), flush=True)

    commits = {record.get("source_commit") for record in prime_records}
    if len(commits) != 1:
        raise RuntimeError(f"prime builds used different source commits: {sorted(commits)}")
    fixed_commit = next(iter(commits))
    accepted = 0
    attempts = 0
    while accepted < args.pairs and attempts < args.max_pairs:
        attempts += 1
        order = ("a", "b") if attempts % 2 else ("b", "a")
        pair = [build_once(arm, "warm", attempts, args.build_timeout) for arm in order]
        for record in pair:
            append_jsonl(output, record)
            print(json.dumps(record, sort_keys=True), flush=True)
        valid = all(
            record.get("status") == "success"
            and record.get("source_commit") == fixed_commit
            and not record.get("production_overlap")
            and record.get("reuse_hit")
            and record.get("incremental_publication")
            for record in pair
        )
        if valid:
            accepted += 1
            print(json.dumps({"matched_pair": accepted, "attempt": attempts}), flush=True)
        else:
            print(
                json.dumps(
                    {
                        "discarded_pair": attempts,
                        "reason": "failed build, changed source commit, or production overlap",
                    }
                ),
                flush=True,
            )
        if accepted < args.pairs and attempts < args.max_pairs:
            time.sleep(args.pair_delay)
    if accepted < args.pairs:
        raise RuntimeError(
            f"only {accepted} clean matched warm pairs; requested {args.pairs}"
        )

    cold_count = 0
    while cold_count < args.cold_builds:
        cold_count += 1
        order = ("a", "b") if cold_count % 2 else ("b", "a")
        for arm in order:
            reset_cold_state(arm)
            record = build_once(arm, "cold", cold_count, args.build_timeout)
            append_jsonl(output, record)
            print(json.dumps(record, sort_keys=True), flush=True)
            if (
                record.get("status") != "success"
                or record.get("source_commit") != fixed_commit
                or record.get("production_overlap")
            ):
                raise RuntimeError(
                    f"cold build for arm {arm.upper()} failed comparability checks"
                )
    return 0


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def sample_ttfb(args: argparse.Namespace) -> int:
    output = Path(args.output)
    if output.exists() and not args.append:
        raise RuntimeError(f"output exists; choose another file or pass --append: {output}")
    paths = args.paths or [
        "/",
        "/just-fucking-use-kubernetes/",
        "/archive/",
        "/8bitcc.png",
        "/reader/",
        "/rss.xml",
        "/api/search?q=markata",
        "/this-should-404/",
        "https://www.waylonwalker.com/",
    ]
    records: list[dict] = []
    for path in paths:
        url = urljoin(args.base_url.rstrip("/") + "/", path.lstrip("/"))
        times: list[float] = []
        statuses: list[int] = []
        for index in range(args.samples):
            result = run(
                [
                    "curl",
                    "--silent",
                    "--show-error",
                    "--output",
                    "/dev/null",
                    "--max-time",
                    str(args.request_timeout),
                    "--write-out",
                    "%{http_code} %{time_starttransfer}",
                    url,
                ],
                timeout=args.request_timeout + 5,
            )
            status_text, seconds_text = result.split()
            statuses.append(int(status_text))
            times.append(float(seconds_text))
            record = {
                "sample": index + 1,
                "url": url,
                "status": statuses[-1],
                "ttfb_seconds": times[-1],
                "measured_at": datetime.now(timezone.utc).isoformat(),
            }
            records.append(record)
            append_jsonl(output, record)
            time.sleep(args.sample_delay)
        summary = {
            "url": url,
            "n": len(times),
            "p50_seconds": statistics.median(times),
            "p95_seconds": percentile(times, 0.95),
            "five_xx": sum(500 <= status <= 599 for status in statuses),
            "status_counts": {
                str(status): statuses.count(status) for status in sorted(set(statuses))
            },
        }
        print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


def summarize(values: list[float]) -> dict:
    return {
        "n": len(values),
        "p50": statistics.median(values) if values else None,
        "p95": percentile(values, 0.95) if values else None,
    }


def analyze(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    records = [
        json.loads(line)
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    build_records = [record for record in records if "arm" in record]
    if build_records:
        prime = [record for record in build_records if record.get("kind") == "prime"]
        fixed_commits = {record.get("source_commit") for record in prime}
        fixed_commit = next(iter(fixed_commits)) if len(fixed_commits) == 1 else None
        warm = [
            record
            for record in build_records
            if record.get("kind") == "warm"
            and record.get("status") == "success"
            and not record.get("production_overlap")
            and record.get("reuse_hit")
            and record.get("incremental_publication")
            and record.get("source_commit") == fixed_commit
        ]
        cold = [
            record
            for record in build_records
            if record.get("kind") == "cold"
            and record.get("status") == "success"
            and not record.get("production_overlap")
            and record.get("source_commit") == fixed_commit
        ]
        phases = ("prepare_ms", "build_ms", "promote_ms", "complete_ms", "total_ms")
        summary = {
            "source_commit": fixed_commit,
            "arms": {},
            "public_ttfb_warm": {},
            "warm_matched_pairs": 0,
            "threshold": None,
        }
        clean_attempts: dict[int, list[dict]] = {}
        for record in warm:
            clean_attempts.setdefault(int(record["order"]), []).append(record)
        summary["warm_matched_pairs"] = sum(
            1
            for pair in clean_attempts.values()
            if {record["arm"] for record in pair} == {"A", "B"}
            and len(pair) == 2
        )
        for arm in ("A", "B"):
            arm_warm = [record for record in warm if record["arm"] == arm]
            arm_cold = [record for record in cold if record["arm"] == arm]
            summary["arms"][arm] = {
                "warm": {
                    phase: summarize(
                        [float(record.get(phase) or 0) for record in arm_warm]
                    )
                    for phase in phases
                },
                "cold": {
                    phase: summarize(
                        [float(record.get(phase) or 0) for record in arm_cold]
                    )
                    for phase in phases
                },
            }
            ttfb = [
                float(sample["ttfb_seconds"])
                for record in arm_warm
                for sample in record.get("public_ttfb_samples", [])
                if sample.get("ttfb_seconds") is not None
            ]
            five_xx = sum(
                500 <= int(sample.get("status") or 0) <= 599
                for record in arm_warm
                for sample in record.get("public_ttfb_samples", [])
            )
            summary["public_ttfb_warm"][arm] = {
                **summarize(ttfb),
                "five_xx": five_xx,
            }
        a_median = summary["arms"]["A"]["warm"]["complete_ms"]["p50"]
        b_median = summary["arms"]["B"]["warm"]["complete_ms"]["p50"]
        if a_median and b_median is not None:
            reduction_ms = a_median - b_median
            reduction_percent = 100 * reduction_ms / a_median
            summary["threshold"] = {
                "control_a_median_ms": a_median,
                "treatment_b_median_ms": b_median,
                "reduction_ms": reduction_ms,
                "reduction_percent": reduction_percent,
                "passes_20_percent_and_15_seconds": reduction_percent >= 20
                and reduction_ms >= 15000,
            }
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        grouped: dict[str, list[dict]] = {}
        for record in records:
            grouped.setdefault(record.get("url", ""), []).append(record)
        summary = {
            url: {
                **summarize([float(record["ttfb_seconds"]) for record in items]),
                "five_xx": sum(500 <= int(record["status"]) <= 599 for record in items),
                "status_counts": {
                    str(status): sum(int(record["status"]) == status for record in items)
                    for status in sorted({int(record["status"]) for record in items})
                },
            }
            for url, items in grouped.items()
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
    if args.output:
        Path(args.output).write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("builds", "ttfb", "analyze"), required=True)
    parser.add_argument("--output", help="write JSON Lines results or the analysis here")
    parser.add_argument("--input", help="read JSON Lines results for analysis")
    parser.add_argument("--append", action="store_true", help="append to an existing file")
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--sample-delay", type=float, default=0.1)
    parser.add_argument("--request-timeout", type=int, default=20)
    parser.add_argument("--base-url", default=SOURCE_URL)
    parser.add_argument("--paths", nargs="*")
    parser.add_argument("--pairs", type=int, default=10)
    parser.add_argument("--max-pairs", type=int, default=15)
    parser.add_argument("--cold-builds", type=int, default=2)
    parser.add_argument("--pair-delay", type=int, default=5)
    parser.add_argument("--build-timeout", type=int, default=7200)
    args = parser.parse_args()
    try:
        if args.mode == "analyze":
            if not args.input:
                raise RuntimeError("--input is required with --mode analyze")
            return analyze(args)
        if not args.output:
            raise RuntimeError("--output is required with --mode builds or --mode ttfb")
        if args.samples < 1 or args.pairs < 1 or args.cold_builds < 0:
            raise RuntimeError("samples and pairs must be positive; cold-builds cannot be negative")
        if args.mode == "ttfb":
            return sample_ttfb(args)
        return run_builds(args)
    except (RuntimeError, TimeoutError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
