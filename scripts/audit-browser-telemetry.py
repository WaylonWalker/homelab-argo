#!/usr/bin/env python3
"""Warn when live ingress routes have no browser telemetry inventory policy."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def read_json(path: str | None, resource: str) -> dict:
    if path:
        return json.loads(Path(path).read_text())
    result = subprocess.run(
        ["kubectl", "get", resource, "-A", "-o", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def inventory_rows(path: Path) -> dict[tuple[str, str, str], tuple[str, str]]:
    rows: dict[tuple[str, str, str], tuple[str, str]] = {}
    for line in path.read_text().splitlines():
        if not line.startswith("| ") or line.startswith("| Public host") or line.startswith("|---"):
            continue
        cols = [part.strip().replace("\\|", "|") for part in line.strip("|").split("|")]
        if len(cols) != 8:
            continue
        host, owner_route, _app, _source, classification, _family, _environment, status = cols
        if "/" not in owner_route:
            continue
        namespace, ingress = owner_route.split("/", 1)
        rows[(namespace, ingress, host)] = (classification, status)
    return rows


def live_rows(*documents: dict) -> set[tuple[str, str, str]]:
    rows: set[tuple[str, str, str]] = set()
    for document in documents:
        for item in document.get("items", []):
            metadata = item.get("metadata", {})
            namespace = metadata.get("namespace", "default")
            name = metadata.get("name", "unknown")
            for rule in item.get("spec", {}).get("rules", []):
                host = rule.get("host")
                if host:
                    rows.add((namespace, name, host))
            for route in item.get("spec", {}).get("routes", []):
                match = route.get("match", "")
                for host in re.findall(r"Host\(`([^`]+)`\)", match):
                    rows.add((namespace, f"{name} (IngressRoute)", host))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        default="docs/browser-telemetry-inventory.md",
        help="Markdown inventory path",
    )
    parser.add_argument("--ingresses-file", help="Use saved kubectl ingress JSON")
    parser.add_argument("--ingressroutes-file", help="Use saved Traefik IngressRoute JSON")
    args = parser.parse_args()

    inventory = inventory_rows(Path(args.inventory))
    ingress_doc = read_json(args.ingresses_file, "ingresses.networking.k8s.io")
    docs = [ingress_doc]
    if args.ingressroutes_file:
        docs.append(json.loads(Path(args.ingressroutes_file).read_text()))
    else:
        try:
            docs.append(read_json(None, "ingressroutes.traefik.io"))
        except subprocess.CalledProcessError:
            pass
    live = live_rows(*docs)
    known = set(inventory)

    new_routes = sorted(live - known)
    stale_routes = sorted(known - live)
    unresolved = sorted(
        (key, value)
        for key, value in inventory.items()
        if "unknown" in value[0].lower()
        or "needs validation" in value[0].lower()
        or "pending review" in value[1].lower()
        or "pending host-level mapping" in value[1].lower()
        or "source mapping pending" in value[1].lower()
        or "unlocated" in value[0].lower()
    )

    for namespace, name, host in new_routes:
        print(f"WARN new public route needs telemetry policy: {namespace}/{name} {host}")
    for namespace, name, host in stale_routes:
        print(f"WARN inventory route is not live: {namespace}/{name} {host}")
    for (namespace, name, host), (classification, status) in unresolved:
        print(f"WARN classify route: {namespace}/{name} {host} [{classification}; {status}]")
    if not new_routes and not stale_routes and not unresolved:
        print(f"OK: {len(live)} live route entries match the classified inventory")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
