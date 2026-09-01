#!/usr/bin/env python3
"""Fail when a proposed Docker subnet overlaps a non-project host route."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from ipaddress import IPv4Network, ip_network
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("subnet")
    parser.add_argument("docker_network_name")
    return parser.parse_args()


def route_documents(ip_binary: str) -> Any:
    # The executable is resolved through shutil.which and arguments are fixed.
    result = subprocess.run(  # noqa: S603
        [ip_binary, "-j", "route", "show", "table", "all"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def existing_bridge(docker_binary: str, network_name: str, candidate: IPv4Network) -> str | None:
    # No shell is involved; network_name is one opaque Docker CLI argument.
    result = subprocess.run(  # noqa: S603
        [docker_binary, "network", "inspect", network_name],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    documents = json.loads(result.stdout)
    if len(documents) != 1:
        raise RuntimeError(f"unexpected Docker network inspection result for {network_name}")
    document = documents[0]
    configured = {
        ip_network(item["Subnet"], strict=True)
        for item in document.get("IPAM", {}).get("Config", [])
        if item.get("Subnet")
    }
    if candidate not in configured:
        raise RuntimeError(
            f"existing Docker network {network_name} does not use requested subnet {candidate}"
        )
    network_id = str(document.get("Id", ""))
    return f"br-{network_id[:12]}" if network_id else None


def main() -> int:
    args = parse_args()
    candidate = ip_network(args.subnet, strict=True)
    if not isinstance(candidate, IPv4Network):
        raise SystemExit("only an explicit IPv4 edge subnet is supported")
    docker_binary = shutil.which("docker")
    ip_binary = shutil.which("ip")
    if docker_binary is None or ip_binary is None:
        raise SystemExit("docker and ip commands are required for the overlap check")
    own_bridge = existing_bridge(docker_binary, args.docker_network_name, candidate)
    routes = route_documents(ip_binary)
    conflicts: list[dict[str, str]] = []
    for route in routes:
        destination = str(route.get("dst", ""))
        if not destination or destination == "default":
            continue
        try:
            route_network = ip_network(destination, strict=False)
        except ValueError:
            continue
        if route_network.version != candidate.version or not route_network.overlaps(candidate):
            continue
        device = str(route.get("dev", ""))
        if own_bridge and device == own_bridge:
            continue
        conflicts.append(
            {
                "destination": str(route_network),
                "device": device,
                "protocol": str(route.get("protocol", "")),
            }
        )
    if conflicts:
        print(
            json.dumps(
                {
                    "status": "overlap",
                    "candidate": str(candidate),
                    "conflicts": conflicts,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "available",
                "candidate": str(candidate),
                "existing_project_bridge": own_bridge,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, json.JSONDecodeError, subprocess.SubprocessError, RuntimeError) as exc:
        print(f"cannot verify host route overlap: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
