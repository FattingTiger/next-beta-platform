#!/usr/bin/env python3
"""Reject Compose settings that could interfere with the host VPN/network stack."""

from __future__ import annotations

import json
import re
import sys
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any

LOOPBACKS = {"127.0.0.1", "::1"}
FORBIDDEN_CAPABILITIES = {"NET_ADMIN", "SYS_ADMIN"}
FORBIDDEN_MOUNTS = ("/etc/sing-box", "/var/lib/sing-box", "/dev/net/tun")
FORBIDDEN_COMMAND_FRAGMENTS = ("iptables", "ip6tables", "nft ", "ip route", "ip rule")


def fail(message: str) -> None:
    print(f"isolation check failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def command_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(str(part) for part in value)
    return str(value)


def main() -> int:
    document: dict[str, Any] = json.load(sys.stdin)
    services = document.get("services", {})
    if not services:
        fail("no services found")

    for name, service in services.items():
        if service.get("network_mode") == "host":
            fail(f"{name} uses host networking")
        if service.get("privileged"):
            fail(f"{name} is privileged")
        user = str(service.get("user", ""))
        if not user or user in {"0", "0:0", "root"}:
            fail(f"{name} does not declare a non-root user")
        if not service.get("read_only"):
            fail(f"{name} does not use a read-only root filesystem")
        capabilities = {str(item).upper() for item in (service.get("cap_add") or [])}
        if capabilities & FORBIDDEN_CAPABILITIES:
            fail(f"{name} adds forbidden capabilities: {sorted(capabilities)}")
        dropped = {str(item).upper() for item in (service.get("cap_drop") or [])}
        if "ALL" not in dropped:
            fail(f"{name} does not drop all Linux capabilities")
        security_options = {str(item) for item in (service.get("security_opt") or [])}
        if not any(item.startswith("no-new-privileges") for item in security_options):
            fail(f"{name} does not enable no-new-privileges")
        try:
            memory_limit = int(service.get("mem_limit", 0))
            cpu_limit = float(service.get("cpus", 0))
        except (TypeError, ValueError):
            fail(f"{name} has invalid CPU or memory resource limits")
        if memory_limit <= 0 or cpu_limit <= 0:
            fail(f"{name} must declare positive CPU and memory resource limits")
        devices = json.dumps(service.get("devices", []), sort_keys=True)
        if "/dev/net/tun" in devices:
            fail(f"{name} mounts /dev/net/tun")
        mounts = json.dumps(service.get("volumes", []), sort_keys=True)
        if any(path in mounts for path in FORBIDDEN_MOUNTS):
            fail(f"{name} mounts a sing-box or TUN host path")
        command = command_text(service.get("command"))
        entrypoint = command_text(service.get("entrypoint"))
        executable_text = f"{command} {entrypoint}".lower()
        if any(fragment in executable_text for fragment in FORBIDDEN_COMMAND_FRAGMENTS):
            fail(f"{name} contains a host network mutation command")

        for port in service.get("ports") or []:
            host_ip = str(port.get("host_ip", ""))
            published = int(port.get("published", 0))
            if host_ip not in LOOPBACKS:
                fail(f"{name} publishes on non-loopback address {host_ip!r}")
            if published < 1024 or published > 65535:
                fail(f"{name} publishes non-high port {published}")

    networks = document.get("networks", {})
    if set(networks) != {"database", "edge", "ingress"}:
        fail(f"unexpected network set: {sorted(networks)}")
    for name in ("database", "edge"):
        if not networks[name].get("internal"):
            fail(f"network {name} is not internal")
    if networks["ingress"].get("internal"):
        fail("ingress network cannot publish the loopback gateway port when marked internal")

    app_environment = services.get("app", {}).get("environment", {})
    required_environment = {
        "BETA_ENVIRONMENT": "production",
        "BETA_COOKIE_SECURE": "true",
        "BETA_AUTO_CREATE_SCHEMA": "false",
        "BETA_REQUIRE_APK_TOOLS": "true",
        "BETA_USE_X_ACCEL_REDIRECT": "true",
        "BETA_RUN_MIGRATIONS": "true",
    }
    for key, expected in required_environment.items():
        if str(app_environment.get(key, "")).lower() != expected:
            fail(f"app environment {key} is not locked to {expected}")
    if "BETA_DATABASE_URL" in app_environment:
        fail("database URL must be assembled from a runtime secret, not Compose environment")
    if not str(app_environment.get("BETA_PUBLIC_BASE_URL", "")).startswith("https://"):
        fail("public base URL is not HTTPS")
    allowed_hosts = str(app_environment.get("BETA_ALLOWED_HOSTS", ""))
    if "*" in allowed_hosts or not allowed_hosts:
        fail("allowed hosts must be explicit")

    edge = document.get("networks", {}).get("edge", {})
    ipam_configs = edge.get("ipam", {}).get("config", [])
    if len(ipam_configs) != 1 or not ipam_configs[0].get("subnet"):
        fail("edge network must have one explicit subnet")
    subnet = ip_network(str(ipam_configs[0]["subnet"]), strict=True)
    bridge_gateway = ip_address(str(ipam_configs[0].get("gateway", "")))
    app_ip = ip_address(
        str(services.get("app", {}).get("networks", {}).get("edge", {}).get("ipv4_address", ""))
    )
    gateway_ip = ip_address(
        str(services.get("gateway", {}).get("networks", {}).get("edge", {}).get("ipv4_address", ""))
    )
    if any(address not in subnet for address in (bridge_gateway, app_ip, gateway_ip)):
        fail("edge static addresses are outside the configured subnet")
    if len({bridge_gateway, app_ip, gateway_ip}) != 3:
        fail("edge bridge, app, and gateway addresses must be distinct")
    edge_members = {name for name, service in services.items() if "edge" in (service.get("networks") or {})}
    if edge_members != {"app", "gateway"}:
        fail(f"edge network membership is not limited to app and gateway: {sorted(edge_members)}")
    ingress = networks["ingress"]
    ingress_configs = ingress.get("ipam", {}).get("config", [])
    if len(ingress_configs) != 1 or not ingress_configs[0].get("subnet"):
        fail("ingress network must have one explicit subnet")
    ingress_subnet = ip_network(str(ingress_configs[0]["subnet"]), strict=True)
    ingress_bridge = ip_address(str(ingress_configs[0].get("gateway", "")))
    gateway_ingress = ip_address(
        str(services.get("gateway", {}).get("networks", {}).get("ingress", {}).get("ipv4_address", ""))
    )
    if ingress_subnet.overlaps(subnet):
        fail("edge and ingress subnets overlap")
    if ingress_bridge not in ingress_subnet or gateway_ingress not in ingress_subnet:
        fail("ingress static addresses are outside the configured subnet")
    if ingress_bridge == gateway_ingress:
        fail("ingress bridge and gateway addresses must be distinct")
    ingress_members = {
        name for name, service in services.items() if "ingress" in (service.get("networks") or {})
    }
    if ingress_members != {"gateway"}:
        fail(f"ingress network membership is not limited to gateway: {sorted(ingress_members)}")

    gateway_environment = services.get("gateway", {}).get("environment", {})
    if str(gateway_environment.get("BETA_NGINX_TRUSTED_PROXY", "")) != str(ingress_bridge):
        fail("Nginx real-IP trust must equal the exact ingress bridge gateway")
    if str(gateway_environment.get("NGINX_ENVSUBST_FILTER", "")) != "^BETA_NGINX_":
        fail("Nginx envsubst filter must preserve native Nginx variables")
    if str(gateway_environment.get("NGINX_ENVSUBST_OUTPUT_DIR", "")) != "/tmp":  # noqa: S108
        fail("Nginx rendered configuration must be written under the writable tmpfs")
    gateway_command = command_text(services.get("gateway", {}).get("command"))
    if "-c /tmp/nginx.conf" not in gateway_command:
        fail("Nginx must start from the rendered real-IP configuration")

    nginx_template = Path(__file__).with_name("nginx.conf").read_text(encoding="utf-8")
    trusted_sources = re.findall(r"^\s*set_real_ip_from\s+([^;]+);", nginx_template, re.MULTILINE)
    if set(trusted_sources) != {"${BETA_NGINX_TRUSTED_PROXY}", "127.0.0.1", "::1"}:
        fail(f"Nginx real-IP source allowlist is not exact: {trusted_sources}")
    for directive in (
        "real_ip_header X-Forwarded-For;",
        "real_ip_recursive on;",
        "proxy_set_header X-Forwarded-For $remote_addr;",
        "auth_request /_upload-auth/admin;",
        "auth_request /_upload-auth/user;",
        "proxy_method GET;",
        "proxy_pass_request_body off;",
        "client_max_body_size 0;",
        "proxy_set_header X-CSRF-Token $http_x_csrf_token;",
    ):
        if directive not in nginx_template:
            fail(f"Nginx real-IP contract is missing {directive}")
    if "$proxy_add_x_forwarded_for" in nginx_template:
        fail("Nginx must overwrite rather than append the app-facing X-Forwarded-For header")
    if "client_max_body_size 540m;" in nginx_template:
        fail("Nginx must not expose a generic 540 MiB request-body allowance")
    change_password_location = re.search(
        r"location\s*=\s*/api/v1/auth/change-password\s*\{(?P<body>.*?)^\s*\}",
        nginx_template,
        re.MULTILINE | re.DOTALL,
    )
    if change_password_location is None:
        fail("Nginx must isolate the password-change endpoint")
    change_password_body = change_password_location.group("body")
    for directive in (
        "client_max_body_size 16k;",
        "limit_req zone=password_change_per_ip burst=2 nodelay;",
        "limit_conn connections_per_ip 1;",
    ):
        if directive not in change_password_body:
            fail(f"Nginx password-change hardening is missing {directive}")
    if "limit_req_zone $binary_remote_addr zone=password_change_per_ip:10m rate=6r/m;" not in nginx_template:
        fail("Nginx password-change request-rate zone is missing or too permissive")
    for body_limit in (
        "client_max_body_size 12m;",
        "client_max_body_size 520m;",
        "client_max_body_size 60m;",
    ):
        if body_limit not in nginx_template:
            fail(f"Nginx upload route is missing {body_limit}")
    try:
        trusted_networks = {
            ip_network(item, strict=False)
            for item in json.loads(str(app_environment.get("BETA_TRUSTED_PROXY_NETWORKS", "[]")))
        }
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        fail(f"trusted proxy networks are invalid: {exc}")
    expected_proxy = {ip_network(f"{gateway_ip}/32")}
    if trusted_networks != expected_proxy:
        fail("trusted proxy scope must contain only the exact gateway address")
    app_command = command_text(services.get("app", {}).get("command"))
    if "--no-proxy-headers" not in app_command or "--forwarded-allow-ips" in app_command:
        fail("uvicorn proxy-header trust must be disabled in favor of application CIDR validation")
    if "--no-access-log" not in app_command:
        fail("uvicorn access logging must be disabled so query-string download tickets stay private")

    app_user = str(services.get("app", {}).get("user", ""))
    gateway_user = str(services.get("gateway", {}).get("user", ""))
    if gateway_user != app_user:
        fail("gateway must share the app's unprivileged storage identity")
    gateway_storage_mounts = [
        mount
        for mount in services.get("gateway", {}).get("volumes", [])
        if mount.get("target") == "/var/lib/beta-center/storage"
    ]
    if len(gateway_storage_mounts) != 1 or not gateway_storage_mounts[0].get("read_only"):
        fail("gateway storage volume must be mounted exactly once and read-only")

    print("compose isolation check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
