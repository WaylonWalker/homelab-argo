"""Keep the newest terminal tunnel pods; leave active and unrelated pods alone."""
import argparse
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

NAMESPACE = "cloudflared"


def eligible(pod):
    metadata = pod.get("metadata", {})
    return (
        metadata.get("namespace") == NAMESPACE
        and metadata.get("labels", {}).get("pod") == "cloudflared"
        and pod.get("status", {}).get("phase") in {"Failed", "Succeeded"}
        and any(
            owner.get("kind") == "ReplicaSet"
            and owner.get("controller") is True
            and owner.get("name", "").startswith("cloudflared-deployment-")
            for owner in metadata.get("ownerReferences", [])
        )
    )


def candidates(pods, keep):
    return sorted(
        (pod for pod in pods if eligible(pod)),
        key=lambda pod: (pod["metadata"].get("creationTimestamp", ""), pod["metadata"]["name"]),
        reverse=True,
    )[keep:]


class API:
    def __init__(self):
        directory = Path("/var/run/secrets/kubernetes.io/serviceaccount")
        self.token = (directory / "token").read_text().strip()
        self.context = ssl.create_default_context(cafile=str(directory / "ca.crt"))
        self.base = "https://{}:{}/api/v1/namespaces/{}/pods".format(
            os.environ["KUBERNETES_SERVICE_HOST"],
            os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443"),
            NAMESPACE,
        )

    def request(self, suffix="", method="GET", body=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.base + suffix, data=data, method=method,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, context=self.context, timeout=30) as response:
            return json.load(response)

    def pods(self):
        result = []
        for phase in ["Failed", "Succeeded"]:
            continuation = ""
            while True:
                query = urllib.parse.urlencode({
                    "labelSelector": "pod=cloudflared", "fieldSelector": "status.phase=" + phase,
                    "limit": 500, "continue": continuation,
                })
                page = self.request("?" + query)
                result.extend(page["items"])
                continuation = page.get("metadata", {}).get("continue", "")
                if not continuation:
                    break
        return result


def cleanup(api, keep=20, dry_run=False):
    selected = candidates(api.pods(), keep)
    deleted = 0
    for pod in selected:
        metadata = pod["metadata"]
        suffix = "/" + urllib.parse.quote(metadata["name"], safe="")
        try:
            current = api.request(suffix)
            if not eligible(current) or current["metadata"]["uid"] != metadata["uid"]:
                continue
            if not dry_run:
                api.request(suffix, "DELETE", {
                    "apiVersion": "v1", "kind": "DeleteOptions",
                    "preconditions": {"uid": metadata["uid"]},
                })
            deleted += 1
        except urllib.error.HTTPError as error:
            if error.code not in {404, 409}:
                raise
    print(json.dumps({"keep": keep, "candidates": len(selected), "deleted": deleted, "dry_run": dry_run}))
    return deleted


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.keep <= 1000:
        parser.error("keep must be between 1 and 1000")
    cleanup(API(), args.keep, args.dry_run)
