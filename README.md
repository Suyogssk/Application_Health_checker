# Application Health Checker

A small Python 3 command-line tool that checks whether one or more web applications respond with expected HTTP status codes. It reports **UP** or **DOWN**, the HTTP status, response time, and check time. It uses only the Python standard library and works on Windows, macOS, and Linux.

## Requirements

- Python 3.9 or newer
- Network access to the application being checked

No packages to install.

## Quick start

```bash
python app_health_checker.py https://example.com
```

On Windows, `py` can be used instead of `python`:

```powershell
py app_health_checker.py https://example.com
```

HTTP responses from **200 through 399** count as healthy by default. Redirects are followed and the final response status is evaluated. DNS errors, refused connections, and timeouts count as **DOWN**. The process returns exit code `0` when all checks pass and `1` if any check is down, making it usable in scripts and CI.

## Check several applications

Create a JSON config (see [`config.example.json`](config.example.json)):

```json
{
  "applications": [
    { "name": "Website", "url": "https://example.com" },
    { "name": "API", "url": "http://localhost:8000/health" }
  ]
}
```

Run the checks concurrently:

```bash
python app_health_checker.py --config config.example.json
```

Or pass URLs directly:

```bash
python app_health_checker.py https://example.com http://localhost:8000/health
```

## Monitor continuously

Run checks every 30 seconds, until interrupted with `Ctrl+C`:

```bash
python app_health_checker.py --config config.example.json --interval 30
```

Run exactly five rounds, 10 seconds apart, and save a JSON Lines report:

```bash
python app_health_checker.py --config config.example.json --interval 10 --count 5 --json-out health-report.jsonl
```

Alerts are printed to the console. Add `--log-file health.log` to also record monitoring activity and failures in a log file.

## Options

| Option | Description |
| --- | --- |
| `urls` | One or more application URLs to check |
| `-c, --config FILE` | JSON file with an `applications` array |
| `-t, --timeout SECONDS` | Per-request timeout (default: `5`) |
| `-i, --interval SECONDS` | Delay between rounds; `0` performs one round (default: `0`) |
| `-n, --count N` | Number of rounds; `0` continues until interrupted (default: `0`) |
| `-w, --workers N` | Maximum simultaneous requests (default: `10`) |
| `-e, --expected CODES` | Expected codes or ranges, such as `200,204,301-399` (default: `200-399`) |
| `--json-out FILE` | Append each result as a JSON object on its own line |
| `--log-file FILE` | Also write monitoring activity and alerts to a log |

`--count` applies to checks when monitoring (`--interval` greater than zero). For example, expect only status 200 or 204 with `--expected 200,204`. The status code is checked even if the server returns an HTTP error response such as 503.

## Example output

```text
[UP] Example website | HTTP 200 | 128.43 ms | Expected HTTP status received
[DOWN] Local API | HTTP 503 | 42.10 ms | Unexpected HTTP status
```

## Assessment requirement

This project implements item 4, **Application Health Checker**: it checks application availability using HTTP status codes, distinguishes functioning (`UP`) from unavailable or unexpected (`DOWN`) applications, and can monitor uptime repeatedly while reporting failures.

