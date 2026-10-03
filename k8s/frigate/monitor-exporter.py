#!/usr/bin/env python3
"""Read-only Prometheus metrics for Frigate recording durability."""

import collections
import hashlib
import os
import re
import sqlite3
import ssl
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_CAMERAS = (
    "anns-corner",
    "driveway",
    "freezer",
    "front-door",
    "garage",
    "office",
    "utility-room-cam",
    "front-doorbell",
)
CAMERAS = tuple(
    camera.strip()
    for camera in os.environ.get("FRIGATE_MONITOR_CAMERAS", ",".join(DEFAULT_CAMERAS)).split(",")
    if camera.strip()
)
DB_PATH = "/config/frigate.db"
RECORDINGS = "/media/frigate/recordings"
CACHE = "/tmp/cache"
LOG_PATTERNS = {
    "enospc": re.compile(r"enospc|no space left on device", re.I),
    "recording_behind": re.compile(r"unable to keep up with recording segments", re.I),
    "unprocessed_segments": re.compile(r"too many unprocessed recording segments", re.I),
    "no_new_segments": re.compile(r"no new recording segments were created", re.I),
    "recording_watchdog": re.compile(r"recording watchdog", re.I),
    "database_error": re.compile(
        r"(sqlite|database).*(error|failed|exception)|(error|failed|exception).*(sqlite|database)",
        re.I,
    ),
    "front_doorbell_rtsp_404": re.compile(
        r"front-doorbell.*(describe|rtsp).*(404)|(describe|rtsp).*front-doorbell.*404",
        re.I,
    ),
}
LOG_COUNTS = collections.Counter()
SEEN_LOGS = collections.deque(maxlen=4096)
SEEN_LOG_SET = set()
LAST_LOG_POLL = 0.0
LAST_LOG_SUCCESS = 0.0
SCRAPE_ERROR = 0


def stat_filesystem(path):
    stat = os.statvfs(path)
    block_size = stat.f_frsize
    capacity = stat.f_blocks * block_size
    available = stat.f_bavail * block_size
    used = (stat.f_blocks - stat.f_bfree) * block_size
    return capacity, available, used


def scan_cache():
    """Scan Frigate's flat recording cache without recursively walking storage."""
    count = 0
    oldest = None
    now = time.time()
    with os.scandir(CACHE) as entries:
        for entry in entries:
            name = entry.name.lower()
            if not name.endswith(".mp4") or name.startswith("preview_"):
                continue
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if info.st_size <= 0:
                continue
            count += 1
            oldest = info.st_mtime if oldest is None else min(oldest, info.st_mtime)
    age = 0.0 if oldest is None else max(0.0, now - oldest)
    return count, age


def get_latest_recordings():
    """Return the latest row per camera using Frigate's camera/start_time index."""
    result = {}
    connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=3)
    try:
        connection.execute("PRAGMA query_only=ON")
        for camera in CAMERAS:
            row = connection.execute(
                "SELECT path, end_time FROM recordings "
                "WHERE camera = ? ORDER BY start_time DESC LIMIT 1",
                (camera,),
            ).fetchone()
            if row is not None:
                result[camera] = (str(row[0]), float(row[1]))
    finally:
        connection.close()
    return result


def poll_logs(now):
    """Read only the current Frigate container logs through the pod log API."""
    global LAST_LOG_POLL, LAST_LOG_SUCCESS
    if now - LAST_LOG_POLL < 30:
        return
    LAST_LOG_POLL = now
    namespace = os.environ.get("POD_NAMESPACE", "frigate")
    pod = os.environ.get("POD_NAME", "")
    if not pod:
        return
    query = urlencode(
        {
            "container": "frigate",
            "sinceSeconds": "120",
            "timestamps": "true",
            "tailLines": "1500",
        }
    )
    url = f"https://kubernetes.default.svc/api/v1/namespaces/{namespace}/pods/{pod}/log?{query}"
    try:
        with open(
            "/var/run/secrets/kubernetes.io/serviceaccount/token", encoding="utf-8"
        ) as token_file:
            token = token_file.read().strip()
        context = ssl.create_default_context(
            cafile="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        )
        request = Request(url, headers={"Authorization": f"Bearer {token}"})
        with urlopen(request, timeout=5, context=context) as response:
            lines = response.read().decode("utf-8", errors="replace").splitlines()
        for line in lines:
            for name, pattern in LOG_PATTERNS.items():
                if not pattern.search(line):
                    continue
                signature = hashlib.sha256((name + line).encode()).digest()
                if signature in SEEN_LOG_SET:
                    continue
                if len(SEEN_LOGS) == SEEN_LOGS.maxlen:
                    SEEN_LOG_SET.discard(SEEN_LOGS[0])
                SEEN_LOGS.append(signature)
                SEEN_LOG_SET.add(signature)
                LOG_COUNTS[name] += 1
        LAST_LOG_SUCCESS = now
    except Exception:
        # A separate freshness metric alerts if log collection stops advancing.
        return


def collect():
    global SCRAPE_ERROR
    now = time.time()
    poll_logs(now)
    values = [
        "# HELP frigate_monitor_scrape_error 1 when the exporter cannot read required recording state.",
        "# TYPE frigate_monitor_scrape_error gauge",
    ]
    try:
        cache_count, cache_age = scan_cache()
        cache_total, cache_available, cache_used = stat_filesystem(CACHE)
        media_total, media_available, _ = stat_filesystem("/media/frigate")
        latest = get_latest_recordings()
        SCRAPE_ERROR = 0
        values.extend(
            [
                "# HELP frigate_cache_capacity_bytes Cache filesystem capacity in bytes.",
                "# TYPE frigate_cache_capacity_bytes gauge",
                f"frigate_cache_capacity_bytes {cache_total}",
                "# HELP frigate_cache_available_bytes Cache filesystem available bytes.",
                "# TYPE frigate_cache_available_bytes gauge",
                f"frigate_cache_available_bytes {cache_available}",
                "# HELP frigate_cache_used_bytes Cache filesystem used bytes.",
                "# TYPE frigate_cache_used_bytes gauge",
                f"frigate_cache_used_bytes {cache_used}",
                "# HELP frigate_cache_recording_mp4_count Nonzero camera recording MP4 files in cache, excluding previews.",
                "# TYPE frigate_cache_recording_mp4_count gauge",
                f"frigate_cache_recording_mp4_count {cache_count}",
                "# HELP frigate_cache_oldest_segment_age_seconds Age of the oldest nonzero camera MP4 in cache; previews excluded.",
                "# TYPE frigate_cache_oldest_segment_age_seconds gauge",
                f"frigate_cache_oldest_segment_age_seconds {cache_age:.3f}",
                "# HELP frigate_recording_filesystem_available_bytes Available bytes on /media/frigate.",
                "# TYPE frigate_recording_filesystem_available_bytes gauge",
                f"frigate_recording_filesystem_available_bytes {media_available}",
                "# HELP frigate_recording_filesystem_capacity_bytes Capacity of /media/frigate in bytes.",
                "# TYPE frigate_recording_filesystem_capacity_bytes gauge",
                f"frigate_recording_filesystem_capacity_bytes {media_total}",
                "# HELP frigate_recording_estimated_hours_remaining Estimated remaining recording hours at 9 GB/hour.",
                "# TYPE frigate_recording_estimated_hours_remaining gauge",
                f"frigate_recording_estimated_hours_remaining {media_available / 9_000_000_000:.3f}",
                "# HELP frigate_recording_latest_timestamp_seconds End timestamp for the latest DB recording row.",
                "# TYPE frigate_recording_latest_timestamp_seconds gauge",
                "# HELP frigate_recording_age_seconds Age of the latest DB recording row per camera.",
                "# TYPE frigate_recording_age_seconds gauge",
                "# HELP frigate_recording_file_exists 1 if the latest DB row references a nonempty persistent recording file.",
                "# TYPE frigate_recording_file_exists gauge",
            ]
        )
        for camera in CAMERAS:
            entry = latest.get(camera)
            if entry is None:
                timestamp = 0.0
                age = now
                exists = 0
            else:
                path, timestamp = entry
                filepath = path if os.path.isabs(path) else os.path.join(RECORDINGS, path)
                try:
                    exists = int(os.path.isfile(filepath) and os.path.getsize(filepath) > 0)
                except OSError:
                    exists = 0
                age = max(0.0, now - timestamp)
            label = f'{{camera="{camera}"}}'
            values.extend(
                [
                    f"frigate_recording_latest_timestamp_seconds{label} {timestamp:.3f}",
                    f"frigate_recording_age_seconds{label} {age:.3f}",
                    f"frigate_recording_file_exists{label} {exists}",
                ]
            )
    except Exception:
        SCRAPE_ERROR = 1

    values.append(f"frigate_monitor_scrape_error {SCRAPE_ERROR}")
    values.extend(
        [
            "# HELP frigate_log_events_total Matching Frigate recording/database log lines seen since exporter start.",
            "# TYPE frigate_log_events_total counter",
        ]
    )
    for pattern in LOG_PATTERNS:
        values.append(
            f'frigate_log_events_total{{pattern="{pattern}"}} {LOG_COUNTS[pattern]}'
        )
    values.extend(
        [
            "# HELP frigate_log_collector_last_success_timestamp_seconds Time of the last successful Frigate pod log read.",
            "# TYPE frigate_log_collector_last_success_timestamp_seconds gauge",
            f"frigate_log_collector_last_success_timestamp_seconds {LAST_LOG_SUCCESS:.3f}",
        ]
    )
    return "\n".join(values) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_error(404)
            return
        body = collect().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


HTTPServer(("0.0.0.0", 9101), Handler).serve_forever()
