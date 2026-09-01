from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce the small-platform load acceptance gate")
    parser.add_argument("stats_csv", type=Path)
    parser.add_argument("--profile", choices=("mixed", "range"), default="mixed")
    parser.add_argument("--max-failure-ratio", type=float, default=0.01)
    parser.add_argument("--max-p95-ms", type=float, default=1500)
    parser.add_argument("--max-endpoint-p95-ms", type=float, default=2500)
    parser.add_argument("--max-read-p95-ms", type=float)
    parser.add_argument("--max-write-p95-ms", type=float)
    parser.add_argument("--max-download-p95-ms", type=float, default=10_000)
    parser.add_argument("--min-requests", type=int, default=600)
    parser.add_argument("--min-rps", type=float, default=10)
    parser.add_argument("--min-downloads", type=int, default=20)
    args = parser.parse_args()

    with args.stats_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    aggregate = next((row for row in rows if row.get("Name") == "Aggregated"), None)
    if aggregate is None:
        raise SystemExit("Locust aggregate row is missing")
    requests = int(aggregate["Request Count"])
    failures = int(aggregate["Failure Count"])
    p95 = float(aggregate["95%"] or 0)
    requests_per_second = float(aggregate.get("Requests/s") or 0)
    failure_ratio = failures / requests if requests else 1.0
    print(
        f"requests={requests} failures={failures} failure_ratio={failure_ratio:.4f} "
        f"rps={requests_per_second:.2f} p95_ms={p95:.1f}"
    )
    if requests < args.min_requests:
        raise SystemExit(f"request volume {requests} is below {args.min_requests}")
    if requests_per_second < args.min_rps:
        raise SystemExit(f"request rate {requests_per_second:.2f} is below {args.min_rps:.2f} rps")
    if failure_ratio > args.max_failure_ratio:
        raise SystemExit(f"failure ratio {failure_ratio:.4f} exceeds {args.max_failure_ratio:.4f}")
    if p95 > args.max_p95_ms:
        raise SystemExit(f"p95 {p95:.1f}ms exceeds {args.max_p95_ms:.1f}ms")

    data_rows = [row for row in rows if row.get("Name") != "Aggregated"]
    for row in data_rows:
        name = row.get("Name", "")
        row_requests = int(row["Request Count"])
        row_failures = int(row["Failure Count"])
        row_failure_ratio = row_failures / row_requests if row_requests else 0.0
        row_p95 = float(row["95%"] or 0)
        if "GET /api/v1/downloads/:id/file" in name:
            p95_limit = args.max_download_p95_ms
        elif name.startswith("GET ") and args.max_read_p95_ms is not None:
            p95_limit = args.max_read_p95_ms
        elif not name.startswith("GET ") and args.max_write_p95_ms is not None:
            p95_limit = args.max_write_p95_ms
        else:
            p95_limit = args.max_endpoint_p95_ms
        if row_failure_ratio > args.max_failure_ratio:
            raise SystemExit(
                f"{name} failure ratio {row_failure_ratio:.4f} exceeds {args.max_failure_ratio:.4f}"
            )
        if row_requests and row_p95 > p95_limit:
            raise SystemExit(f"{name} p95 {row_p95:.1f}ms exceeds {p95_limit:.1f}ms")

    required_names = (
        (
            "POST /api/v1/downloads",
            "GET /api/v1/downloads/:id/file",
            "POST /api/v1/downloads/:id/complete",
        )
        if args.profile == "mixed"
        else (
            "POST /api/v1/downloads [range]",
            "GET /api/v1/downloads/:id/file [range]",
            "POST /api/v1/downloads/:id/complete [range]",
        )
    )
    by_name = {row.get("Name", ""): row for row in data_rows}
    for name in required_names:
        required_row = by_name.get(name)
        if required_row is None:
            raise SystemExit(f"required load row is missing: {name}")
        count = int(required_row["Request Count"])
        if count < args.min_downloads:
            raise SystemExit(f"{name} count {count} is below {args.min_downloads}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
