#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NoReturn, cast

ROOT = Path(__file__).resolve().parent


def fail(message: str) -> NoReturn:
    raise SystemExit(f"native asset verification failed: {message}")


def read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        fail(f"missing {relative}")
    return path.read_text(encoding="utf-8")


def brace_block(document: str, marker: str) -> str:
    start = document.find(marker)
    if start < 0:
        fail(f"missing Caddy block: {marker}")
    opening = document.find("{", start)
    depth = 0
    for index in range(opening, len(document)):
        if document[index] == "{":
            depth += 1
        elif document[index] == "}":
            depth -= 1
            if depth == 0:
                return document[opening + 1 : index]
    fail(f"unterminated Caddy block: {marker}")


caddy = read("Caddyfile")
if "profile shortlived" not in caddy or "disable_tlsalpn_challenge" not in caddy:
    fail("Let's Encrypt shortlived HTTP-01-only policy is missing")
if re.search(r"(?m)^\s*(?:https_port\s+)?443\b|:443\s*\{", caddy):
    fail("Caddyfile may not listen on or redirect through port 443")
if "https://{$BETA_PUBLIC_IP}:18443" not in caddy or "http://{$BETA_PUBLIC_IP}:80" not in caddy:
    fail("required Caddy listeners are missing")
if "email {$BETA_ACME_EMAIL}" in caddy:
    fail("an optional empty ACME email must not render an invalid directive")
https_server = brace_block(caddy, "servers :18443")
if "protocols h1 h2" not in https_server or re.search(r"\bh3\b", https_server):
    fail("the staging TLS listener must remain TCP-only on port 18443")
for header in ("-Expect", "-Content-Length", "-Content-Type"):
    if caddy.count(f"header_up {header}") != 2:
        fail(f"forward-auth probes must strip upload header {header}")
if "@missing_upload_auth" not in caddy or "header !Authorization" not in caddy:
    fail("the upload gateway does not reject credential-free requests before body handling")
if "not header_regexp beta_access Cookie" not in caddy:
    fail("cookie-authenticated uploads are not distinguished from anonymous uploads")
if caddy.count("respond @missing_upload_auth") != 3 or caddy.count("close") != 3:
    fail("every multipart route must reject and close credential-free uploads")
for auth_snippet in ("(admin_upload_auth)", "(user_upload_auth)"):
    auth_block = brace_block(caddy, auth_snippet)
    transport_block = brace_block(auth_block, "transport http")
    required_transport_lines = {
        "dial_timeout 3s",
        "response_header_timeout 5s",
        "keepalive off",
    }
    normalized_transport_lines = {
        line.strip()
        for line in transport_block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if normalized_transport_lines != required_transport_lines:
        fail(f"{auth_snippet} must use the pinned single-use HTTP transport")
if caddy.count("keepalive off") != 2:
    fail("only the two forward_auth definitions may disable HTTP keepalives")
if caddy.count("keepalive 4s") != 4:
    fail("all four application reverse proxies must use four-second keepalives")
for retry_directive in ("lb_try_duration", "lb_try_interval", "lb_retry_match"):
    if retry_directive in caddy:
        fail(f"application requests must not enable gateway retries: {retry_directive}")

caddy_without_comments = re.sub(r"(?m)^\s*#.*$", "", caddy)
upstreams = set(re.findall(r"\b(?:forward_auth|reverse_proxy)\s+([^\s{]+)", caddy_without_comments))
if upstreams != {"127.0.0.1:18089"}:
    fail(f"all forward_auth and reverse_proxy handlers must share one upstream, found {upstreams}")
dispatch_source = caddy[caddy.find("@direct_protected") :]
dispatch = brace_block(dispatch_source, "route {")
branch_markers = (
    "handle @direct_protected",
    "handle @admin_image_upload",
    "handle @admin_apk_upload",
    "handle @bug_upload",
)
branch_positions = [dispatch.find(marker) for marker in branch_markers]
fallbacks = list(re.finditer(r"(?m)^\s*handle \{$", dispatch))
if min(branch_positions) < 0 or len(fallbacks) != 1:
    fail("the literal upload dispatch route is incomplete or has multiple fallbacks")
dispatch_positions = [*branch_positions, fallbacks[0].start()]
if dispatch_positions != sorted(dispatch_positions):
    fail("upload dispatch must be direct, image, APK, bug, then fallback")
for marker, auth_import in (
    ("handle @admin_image_upload", "import admin_upload_auth"),
    ("handle @admin_apk_upload", "import admin_upload_auth"),
    ("handle @bug_upload", "import user_upload_auth"),
):
    block = brace_block(caddy, marker)
    block = re.sub(r"(?m)^\s*#.*$", "", block)
    positions = [
        block.find("respond @missing_upload_auth"),
        block.find(auth_import),
        block.find("request_body"),
        block.find("reverse_proxy"),
    ]
    if min(positions) < 0 or positions != sorted(positions):
        fail(f"{marker} must authenticate before body handling and proxying")
    if "route {" not in block:
        fail(f"{marker} must use a literal nested route to prevent directive reordering")

protected = brace_block(caddy, "handle @direct_protected")
if "respond 404" not in protected:
    fail("direct private-file requests must return 404")
client_downloads = brace_block(caddy, "handle_path /downloads/android/*")
for token in (
    "root * /var/lib/beta-center-native/client-downloads",
    'header Cache-Control "public, max-age=300"',
    "file_server",
):
    if token not in client_downloads:
        fail(f"public Android update route is missing: {token}")
accel = brace_block(caddy, "handle_response @accel")
for token in (
    "rewrite {rp.header.X-Accel-Redirect}",
    "uri strip_prefix /_protected-files",
    "root * /var/lib/beta-center-native/storage",
    "file_server",
):
    if token not in accel:
        fail(f"X-Accel equivalent is missing: {token}")

slice_unit = read("systemd/beta-center.slice")
postgres_service = read("systemd/beta-center-postgres.service")
app_service = read("systemd/beta-center-app.service")
caddy_service = read("systemd/beta-center-caddy.service")
units = "\n".join((slice_unit, postgres_service, app_service, caddy_service))
unsupported_219 = (
    "RuntimeDirectory=",
    "StateDirectory=",
    "BindReadOnlyPaths=",
    "AmbientCapabilities=",
    "MemoryMax=",
    "TasksMax=",
    "DynamicUser=",
    "ProtectKernelTunables=",
    "RestrictNamespaces=",
)
for directive in unsupported_219:
    if directive in units:
        fail(f"systemd 219-incompatible directive present: {directive}")
if "CapabilityBoundingSet=CAP_NET_BIND_SERVICE\n" not in caddy_service:
    fail("Caddy capability bounding set is not limited to low-port binding")
if "NoNewPrivileges=false" not in caddy_service:
    fail("Caddy file capability would be suppressed by NoNewPrivileges")
if "CAP_DAC_READ_SEARCH" in units or "CAP_SYS_ADMIN" in units:
    fail("Caddy has a broad filesystem or mount capability")
if "CapabilityBoundingSet=\n" not in postgres_service or "CapabilityBoundingSet=\n" not in app_service:
    fail("database and application capability bounding sets must remain empty")
if "NoNewPrivileges=true" not in postgres_service or "NoNewPrivileges=true" not in app_service:
    fail("database and application services must forbid privilege acquisition")
if "Group=beta-files" not in app_service:
    fail("application primary group must preserve beta-files on newly created files")
if "SupplementaryGroups=beta-files" not in caddy_service:
    fail("Caddy does not have read-only private-file group membership")
if "CPUQuota=75%" not in slice_unit or "MemoryLimit=700M" not in slice_unit:
    fail("aggregate resource guard for the pre-existing VPN is missing")
for service_name in (
    "beta-center-postgres.service",
    "beta-center-app.service",
    "beta-center-caddy.service",
):
    service = read(f"systemd/{service_name}")
    if "Slice=beta-center.slice" not in service or "OOMScoreAdjust=300" not in service:
        fail(f"{service_name} is not contained by the project resource guard")

install_script = read("bin/install.sh")
app_env_script = read("bin/with-app-env.sh")
start_app_script = read("bin/start-app.sh")
postgres_config = read("postgresql.conf")
host_state_script = read("bin/host-state.sh")
verify_script = read("bin/verify.sh")
preflight_script = read("bin/preflight.sh")
if ".pth" in install_script:
    fail("shared application environments must not retain a candidate-specific .pth file")
if 'PYTHONPATH="$NATIVE_PREFIX/app/current/src"' not in app_env_script:
    fail("application imports are not bound to the rollback-aware current release symlink")
for capacity_export in (
    "export BETA_DATABASE_POOL_SIZE=16",
    "export BETA_DATABASE_MAX_OVERFLOW=4",
):
    if capacity_export not in app_env_script:
        fail(f"native application capacity profile is missing: {capacity_export}")
if not re.search(r"(?m)^max_connections\s*=\s*28\s*$", postgres_config):
    fail("native PostgreSQL max_connections must retain the measured 28-connection bound")
if 'run_as beta-app env PYTHONPATH="$candidate/src"' not in install_script:
    fail("candidate imports are not verified with the service identity and source")
if 'install -d -o root -g root -m 0755 "$NATIVE_CONFIG"' not in install_script:
    fail("Caddy cannot traverse the native configuration directory")
if 'install -d -o root -g beta-app -m 0750 "$NATIVE_CONFIG/secrets"' not in install_script:
    fail("application secrets directory is not isolated from the gateway")
if "usermod -a -G beta-files" in install_script:
    fail("dedicated service accounts may retain unrelated supplementary groups")
for exclusion in ("--exclude='./.secrets'", "--exclude='*/.secrets'", "--exclude='*/.env'"):
    if exclusion not in install_script:
        fail(f"release copy may retain local credential material: {exclusion}")
if "-JXmx128m" not in install_script or "-JXX:+UseSerialGC" not in install_script:
    fail("apksigner JVM is not bounded for the one-GiB staging host")
if 'run_as beta-app "$apksigner_target" version' not in install_script:
    fail("generated apksigner wrapper is not exercised with the service identity")
if "--workers 1" not in start_app_script or "--limit-concurrency 128" not in start_app_script:
    fail("application runtime must retain one bounded worker with the 100-user concurrency headroom")

deploy_script = read("bin/deploy.sh")
if deploy_script.count('--header "Host: $BETA_PUBLIC_IP"') < 2:
    fail("loopback readiness probes do not satisfy the production trusted-host policy")
if '[[ ! -e "$destination" && ! -L "$destination" ]]' not in host_state_script:
    fail("host snapshots may reuse a caller-controlled path")
if host_state_script.count("normalize_listeners") < 3:
    fail("live listener queue counters can create false VPN invariant changes")
if host_state_script.count("hash_routes") < 3 or "<dynamic>" not in host_state_script:
    fail("live route expiry timers can create false network invariant changes")
if "systemd/*.slice" not in verify_script:
    fail("systemd slice syntax is omitted from target verification")
for ntp_contract in (
    "timedatectl show --property=NTPSynchronized",
    "NTPSynchronized=yes",
    "LC_ALL=C timedatectl status",
    "NTP synchronized:",
):
    if ntp_contract not in preflight_script:
        fail(f"preflight NTP synchronization contract is missing: {ntp_contract}")
if "NTP enabled:" in preflight_script:
    fail("preflight must not treat an enabled NTP client as proof of synchronization")

asset_files = [path for path in ROOT.rglob("*") if path.is_file()]
if any(path.name.startswith("._") for path in asset_files):
    fail("AppleDouble metadata files must not be present in the release artifact")
all_assets = "\n".join(
    path.read_text(encoding="utf-8") for path in asset_files if path.name != Path(__file__).name
)
if "2.11" + ".3" in all_assets:
    fail("retired Caddy release reference remains")
if "v2.11.4" not in all_assets:
    fail("Caddy 2.11.4 is not pinned")

for pattern in (
    r"\biptables\s+(?:-A|-I|-D|-F|-X|-P)",
    r"\bnft\s+(?:add|delete|flush|insert|replace)\b",
    r"\bfirewall-cmd\b[^\n]*(?:--add|--remove|--reload|--complete-reload|--set-default-zone|--panic)",
    r"\bip\s+(?:-4\s+|-6\s+)?route\s+(?:add|del|delete|replace|flush)\b",
    r"\bip\s+(?:-4\s+|-6\s+)?rule\s+(?:add|del|delete|flush)\b",
    r"systemctl\s+(?:start|stop|restart|reload|enable|disable|mask|unmask|kill|try-restart)\s+sing-box",
):
    if re.search(pattern, all_assets):
        fail(f"forbidden host-network or sing-box mutation matched: {pattern}")

env_example = read("env.example")
if "BETA_PUBLIC_IP=__PUBLIC_IPV4__" not in env_example:
    fail("public IP must remain a placeholder")
for assignment in re.findall(r"(?m)^([A-Z][A-Z0-9_]*)=(.*)$", env_example):
    key, value = assignment
    if re.search(r"(?:PASSWORD|SECRET|TOKEN)", key) and not key.endswith("_FILE") and value:
        fail(f"credential material appeared in env.example: {key}")
if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", all_assets):
    fail("private key material appeared in native deployment assets")


JsonObject = dict[str, Any]


def object_list(value: Any) -> list[JsonObject]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        return []
    return cast(list[JsonObject], value)


def iter_route_lists(value: Any) -> Iterator[list[JsonObject]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "routes":
                routes = object_list(child)
                if routes:
                    yield routes
            yield from iter_route_lists(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_route_lists(child)


def route_matchers(route: JsonObject) -> list[JsonObject]:
    return object_list(route.get("match", []))


def matched_methods(route: JsonObject) -> set[str]:
    methods: set[str] = set()
    for matcher in route_matchers(route):
        value = matcher.get("method", [])
        if isinstance(value, list):
            methods.update(item for item in value if isinstance(item, str))
    return methods


def classify_dispatch_route(route: JsonObject) -> str:
    matchers = route_matchers(route)
    if not matchers:
        return "fallback"
    methods = matched_methods(route)
    for matcher in matchers:
        paths = matcher.get("path", [])
        if isinstance(paths, list) and "/_protected-files/*" in paths:
            return "direct_protected"
        if isinstance(paths, list) and "/api/v1/bugs" in paths and methods == {"POST"}:
            return "bug_upload"
        regexp = matcher.get("path_regexp")
        if isinstance(regexp, dict) and methods == {"POST"}:
            if regexp.get("name") == "admin_image" and regexp.get("pattern") == (
                r"^/api/v1/admin/apps/[^/]+/(icon|screenshots)$"
            ):
                return "admin_image_upload"
            if regexp.get("name") == "admin_apk" and regexp.get("pattern") == (
                r"^/api/v1/admin/apps/[^/]+/versions$"
            ):
                return "admin_apk_upload"
    return "other"


def unwrap_single_subroutes(route: JsonObject) -> list[JsonObject]:
    routes = [route]
    while len(routes) == 1:
        handlers = object_list(routes[0].get("handle", []))
        if len(handlers) != 1 or handlers[0].get("handler") != "subroute":
            break
        nested = object_list(handlers[0].get("routes", []))
        if not nested:
            break
        routes = nested
    return routes


def route_handlers(route: JsonObject) -> list[JsonObject]:
    return object_list(route.get("handle", []))


def handler_names(handlers: list[JsonObject]) -> list[str]:
    return [str(handler.get("handler", "")) for handler in handlers]


def assert_loopback_proxy(handler: JsonObject, context: str) -> None:
    upstreams = object_list(handler.get("upstreams", []))
    dials = {item.get("dial") for item in upstreams}
    if dials != {"127.0.0.1:18089"}:
        fail(f"{context} does not use the single loopback upstream")


def assert_auth_transport(handler: JsonObject, context: str) -> None:
    expected = {
        "dial_timeout": 3_000_000_000,
        "keep_alive": {"enabled": False},
        "protocol": "http",
        "response_header_timeout": 5_000_000_000,
    }
    if handler.get("transport") != expected:
        fail(f"{context} does not use the pinned no-reuse auth transport")


def assert_application_keepalive(handler: JsonObject, context: str) -> None:
    transport = handler.get("transport")
    keep_alive = transport.get("keep_alive") if isinstance(transport, dict) else None
    if (
        not isinstance(keep_alive, dict)
        or keep_alive.get("enabled") is False
        or keep_alive.get("idle_timeout") != 4_000_000_000
    ):
        fail(f"{context} must retain the four-second application keepalive")
    if handler.get("load_balancing") not in (None, {}):
        fail(f"{context} must not enable gateway retries")


def is_missing_auth_match(route: JsonObject) -> bool:
    for matcher in route_matchers(route):
        headers = matcher.get("header")
        missing_bearer = (
            isinstance(headers, dict) and "Authorization" in headers and headers["Authorization"] is None
        )
        negative = matcher.get("not", [])
        missing_cookie = False
        if isinstance(negative, list):
            for item in negative:
                if not isinstance(item, dict):
                    continue
                regexps = item.get("header_regexp")
                if not isinstance(regexps, dict):
                    continue
                cookie = regexps.get("Cookie")
                if (
                    isinstance(cookie, dict)
                    and cookie.get("name") == "beta_access"
                    and cookie.get("pattern") == r"(?i)(^|;[[:space:]]*)beta_access="
                ):
                    missing_cookie = True
        if missing_bearer and missing_cookie:
            return True
    return False


def validate_upload_branch(
    route: JsonObject,
    *,
    name: str,
    auth_uri: str,
    max_size: int,
) -> None:
    inner_routes = unwrap_single_subroutes(route)
    if len(inner_routes) != 2:
        fail(f"adapted {name} branch must contain reject and authenticated routes")
    reject_route, authenticated_route = inner_routes
    reject_handlers = route_handlers(reject_route)
    if handler_names(reject_handlers) != ["static_response"]:
        fail(f"adapted {name} branch does not reject missing credentials first")
    rejection = reject_handlers[0]
    if (
        rejection.get("status_code") != 401
        or rejection.get("close") is not True
        or not is_missing_auth_match(reject_route)
    ):
        fail(f"adapted {name} missing-credential response is not fail-fast")
    if route_matchers(authenticated_route):
        fail(f"adapted {name} authenticated continuation gained an unexpected matcher")

    handlers = route_handlers(authenticated_route)
    if handler_names(handlers) != ["reverse_proxy", "request_body", "reverse_proxy"]:
        fail(f"adapted {name} order must be forward_auth, request_body, reverse_proxy")
    forward_auth, request_body, application_proxy = handlers
    rewrite = forward_auth.get("rewrite")
    if not isinstance(rewrite, dict) or rewrite.get("method") != "GET" or rewrite.get("uri") != auth_uri:
        fail(f"adapted {name} first proxy is not the expected forward_auth probe")
    assert_loopback_proxy(forward_auth, f"adapted {name} forward_auth")
    assert_auth_transport(forward_auth, f"adapted {name} forward_auth")
    headers = forward_auth.get("headers")
    request_headers = headers.get("request") if isinstance(headers, dict) else None
    deleted = request_headers.get("delete", []) if isinstance(request_headers, dict) else []
    if not isinstance(deleted, list) or not {
        "Expect",
        "Content-Length",
        "Content-Type",
    }.issubset(deleted):
        fail(f"adapted {name} forward_auth probe can inherit upload body headers")
    if request_body.get("max_size") != max_size:
        fail(f"adapted {name} body limit changed")
    if "rewrite" in application_proxy:
        fail(f"adapted {name} application proxy unexpectedly rewrites the request")
    assert_loopback_proxy(application_proxy, f"adapted {name} application proxy")
    assert_application_keepalive(application_proxy, f"adapted {name} application proxy")


def validate_adapted_routes(config: JsonObject) -> None:
    apps = config.get("apps")
    http = apps.get("http") if isinstance(apps, dict) else None
    servers = http.get("servers") if isinstance(http, dict) else None
    if not isinstance(servers, dict):
        fail("adapted Caddy JSON has no HTTP servers")
    tls_servers = []
    for server in servers.values():
        if not isinstance(server, dict):
            continue
        listeners = server.get("listen", [])
        if isinstance(listeners, list) and ":18443" in listeners:
            tls_servers.append(server)
    if len(tls_servers) != 1:
        fail("adapted Caddy JSON must contain exactly one :18443 server")
    tls_server = cast(JsonObject, tls_servers[0])
    if tls_server.get("protocols") != ["h1", "h2"]:
        fail("adapted :18443 server is not TCP-only h1/h2")

    expected_order = [
        "direct_protected",
        "admin_image_upload",
        "admin_apk_upload",
        "bug_upload",
        "fallback",
    ]
    dispatches = [
        routes
        for routes in iter_route_lists(tls_server)
        if [classify_dispatch_route(route) for route in routes] == expected_order
    ]
    if len(dispatches) != 1:
        fail("adapted routes are not ordered direct, image, APK, bug, fallback")
    dispatch_routes = dispatches[0]
    groups = [route.get("group") for route in dispatch_routes]
    if not all(isinstance(group, str) and group for group in groups) or len(set(groups)) != 1:
        fail("adapted upload branches are not one mutually exclusive handle group")

    direct_routes = unwrap_single_subroutes(dispatch_routes[0])
    if len(direct_routes) != 1:
        fail("adapted direct protected route has an unexpected structure")
    direct_handlers = route_handlers(direct_routes[0])
    if handler_names(direct_handlers) != ["static_response"] or direct_handlers[0].get("status_code") != 404:
        fail("adapted direct protected route does not terminate with 404")

    validate_upload_branch(
        dispatch_routes[1],
        name="admin image upload",
        auth_uri="/api/v1/auth/upload-permission/admin",
        max_size=13_000_000,
    )
    validate_upload_branch(
        dispatch_routes[2],
        name="admin APK upload",
        auth_uri="/api/v1/auth/upload-permission/admin",
        max_size=545_000_000,
    )
    validate_upload_branch(
        dispatch_routes[3],
        name="bug upload",
        auth_uri="/api/v1/auth/upload-permission/user",
        max_size=64_000_000,
    )

    fallback_routes = unwrap_single_subroutes(dispatch_routes[4])
    if len(fallback_routes) != 1:
        fail("adapted fallback has an unexpected structure")
    fallback_handlers = route_handlers(fallback_routes[0])
    if handler_names(fallback_handlers) != ["request_body", "reverse_proxy"]:
        fail("adapted fallback must remain last and proxy only after its body limit")
    if fallback_handlers[0].get("max_size") != 2_000_000:
        fail("adapted fallback body limit changed")
    assert_loopback_proxy(fallback_handlers[1], "adapted fallback")
    assert_application_keepalive(fallback_handlers[1], "adapted fallback")
    proxy_fallbacks = [
        route
        for routes in iter_route_lists(tls_server)
        for route in routes
        if not route_matchers(route)
        and handler_names(route_handlers(route)) == ["request_body", "reverse_proxy"]
    ]
    if len(proxy_fallbacks) != 1 or proxy_fallbacks[0] is not fallback_routes[0]:
        fail("an adapted catch-all proxy can run outside or before the dispatch fallback")


parser = argparse.ArgumentParser(description="Verify native staging deployment assets")
parser.add_argument("--adapted-json", type=Path)
arguments = parser.parse_args()
if arguments.adapted_json is not None:
    adapted_path = cast(Path, arguments.adapted_json)
    if not adapted_path.is_file():
        fail(f"adapted Caddy JSON is missing: {adapted_path}")
    try:
        adapted = json.loads(adapted_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read adapted Caddy JSON: {error}")
    if not isinstance(adapted, dict):
        fail("adapted Caddy JSON root must be an object")
    validate_adapted_routes(cast(JsonObject, adapted))

print("native deployment asset contracts: ok")
