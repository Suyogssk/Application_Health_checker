#!/usr/bin/env python3
"""Check HTTP application health and optionally monitor it over time."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOGGER = logging.getLogger("app_health_checker")


@dataclass
class CheckResult:
    name: str
    url: str
    checked_at: str
    status: str
    http_status: int | None
    response_time_ms: float | None
    message: str


def check_url(target: dict[str, Any], timeout: float, expected: set[int]) -> CheckResult:
    """Make one GET request and classify its HTTP response."""
    name, url = target["name"], target["url"]
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    started = time.perf_counter()
    status_code: int | None = None
    try:
        request = Request(url, headers={"User-Agent": "ApplicationHealthChecker/1.0"})
        # Redirects are followed by urllib; the final response code is checked.
        with urlopen(request, timeout=timeout) as response:
            status_code = response.status
            response.read(1)  # Ensure the response body can be read.
        healthy = status_code in expected
        message = "Expected HTTP status received" if healthy else "Unexpected HTTP status"
    except HTTPError as error:
        # HTTPError is also a response: preserve its code for an accurate report.
        status_code = error.code
        healthy = status_code in expected
        message = "Expected HTTP status received" if healthy else f"Unexpected HTTP status: {error.reason}"
    except (URLError, TimeoutError, OSError, ValueError) as error:
        healthy = False
        message = str(getattr(error, "reason", error)) or error.__class__.__name__
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    return CheckResult(name, url, checked_at, "UP" if healthy else "DOWN", status_code, elapsed, message)


def load_targets(args: argparse.Namespace) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    if args.config:
        try:
            data = json.loads(Path(args.config).read_text(encoding="utf-8"))
            entries = data.get("applications") if isinstance(data, dict) else data
            if not isinstance(entries, list):
                raise ValueError("config must be a list or an object with an 'applications' list")
            for index, entry in enumerate(entries, 1):
                if not isinstance(entry, dict) or not isinstance(entry.get("url"), str):
                    raise ValueError(f"application #{index} must be an object with a URL")
                url = entry["url"].strip()
                if not url.startswith(("http://", "https://")):
                    raise ValueError(f"application #{index} URL must start with http:// or https://")
                targets.append({"name": str(entry.get("name") or url), "url": url})
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"cannot read config: {error}") from error
    for raw_url in args.urls:
        url = raw_url.strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"URL must start with http:// or https://: {url}")
        targets.append({"name": url, "url": url})
    if not targets:
        raise ValueError("provide at least one URL or a config file with applications")
    return targets


def display(result: CheckResult) -> None:
    color = "\033[32m" if result.status == "UP" else "\033[31m"
    reset = "\033[0m" if sys.stdout.isatty() else ""
    if not sys.stdout.isatty():
        color = ""
    code = str(result.http_status) if result.http_status is not None else "no response"
    elapsed = f"{result.response_time_ms:.2f} ms" if result.response_time_ms is not None else "n/a"
    print(f"{color}[{result.status}]{reset} {result.name} | HTTP {code} | {elapsed} | {result.message}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether web applications are responding with expected HTTP status codes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("urls", nargs="*", help="application URLs (HTTP or HTTPS)")
    parser.add_argument("-c", "--config", help="JSON file containing applications to monitor")
    parser.add_argument("-t", "--timeout", type=float, default=5.0, help="request timeout in seconds")
    parser.add_argument("-i", "--interval", type=float, default=0, help="repeat checks every N seconds (0 runs once)")
    parser.add_argument("-n", "--count", type=int, default=0, help="number of monitoring rounds (0 runs until interrupted)")
    parser.add_argument("-w", "--workers", type=int, default=10, help="maximum parallel requests")
    parser.add_argument("-e", "--expected", default="200-399", help="expected HTTP codes, e.g. 200,204,301-399")
    parser.add_argument("--json-out", help="append each monitoring round as JSON Lines to this file")
    parser.add_argument("--log-file", help="also write alerts and monitoring activity to this log file")
    args = parser.parse_args()

    if args.timeout <= 0 or args.interval < 0 or args.count < 0 or args.workers < 1:
        parser.error("timeout and workers must be positive; interval and count cannot be negative")
    try:
        targets = load_targets(args)
        expected: set[int] = set()
        for part in args.expected.split(","):
            values = part.strip().split("-", 1)
            low, high = (int(values[0]), int(values[-1]))
            if low < 100 or high > 599 or low > high:
                raise ValueError
            expected.update(range(low, high + 1))
        if not expected:
            raise ValueError
    except ValueError as error:
        parser.error(str(error) if str(error) else "invalid expected HTTP status codes")

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)

    round_number = 0
    failed = False
    try:
        while args.interval > 0 and (args.count == 0 or round_number < args.count) or round_number == 0:
            round_number += 1
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.workers, len(targets))) as pool:
                results = list(pool.map(lambda target: check_url(target, args.timeout, expected), targets))
            for result in results:
                display(result)
                if result.status == "DOWN":
                    failed = True
                    LOGGER.warning("Application DOWN: %s (%s): %s", result.name, result.url, result.message)
            if args.json_out:
                with Path(args.json_out).open("a", encoding="utf-8") as output:
                    for result in results:
                        output.write(json.dumps(asdict(result)) + "\n")
            if args.interval > 0 and (args.count == 0 or round_number < args.count):
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

