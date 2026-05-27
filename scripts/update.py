"""
Refresh the free-proxy-list mirror from the ProxyScrape v4 public API.

Writes:
  proxies/all/data.{txt,json,csv}
  proxies/protocols/{http,https,socks4,socks5}/data.{txt,json,csv}
  proxies/countries/{ISO}/data.{txt,json,csv}                 (ISO-3166 alpha-2, lowercased)
  proxies/countries/{ISO}/{protocol}/data.{txt,json,csv}      (only when non-empty)
  proxies/stats.json

The "all" shard is fetched in one call (with a generous limit). Protocol and
country shards are derived from that response by filtering — keeping one API
call per run and guaranteeing the shards stay internally consistent (no
inter-shard skew from upstream churn between calls).

Schema notes (upstream):
  - protocol ∈ {http, socks4, socks5}  (HTTPS is a CAPABILITY flag on HTTP,
    not its own protocol value — exposed via `ssl: true`)
  - uptime is reported as a 0–100 percentage by ProxyScrape; we round to 2dp
  - times_alive / times_dead expose the underlying check history

Published columns (CSV / JSON):
  protocol, ip, port, country, country_code, city, anonymity, ssl,
  uptime_percent, asn, isp, latency_ms, last_checked

TXT format: protocol://ip:port  (one per line)

Exits non-zero on any HTTP/parse failure so the workflow surfaces it.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any, Iterable

# The API caps each call at 2000 proxies regardless of the requested limit,
# so we paginate with skip until nextpage is false. PAGE_SIZE is the per-call
# cap; MAX_PAGES is a safety stop to avoid runaway loops if the API
# misreports nextpage.
PAGE_SIZE = 2000
MAX_PAGES = 30  # 30 * 2000 = 60k headroom over the current ~22k pool

API_BASE = (
    "https://api.proxyscrape.com/v4/free-proxy-list/get"
    "?request=get_proxies&proxy_format=protocolipport&format=json"
    f"&limit={PAGE_SIZE}"
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROXIES_ROOT = os.path.join(REPO_ROOT, "proxies")

# 'https' here means "HTTP proxies with ssl=true" — the subset that can
# tunnel HTTPS via CONNECT. Mirrored as a separate shard so consumers can pull
# HTTPS-capable proxies without parsing flags themselves.
PROTOCOL_SHARDS = ("http", "https", "socks4", "socks5")

CSV_HEADER = [
    "protocol",
    "ip",
    "port",
    "country",
    "country_code",
    "city",
    "anonymity",
    "ssl",
    "uptime_percent",
    "asn",
    "isp",
    "latency_ms",
    "last_checked",
]


REQUEST_DELAY_S = 1.5  # polite delay between pages to avoid upstream 5xx
MAX_RETRIES = 4


def fetch_page(skip: int) -> dict[str, Any]:
    url = f"{API_BASE}&skip={skip}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "proxyscrape-free-proxy-list-mirror/1.0 (+https://github.com/proxyscrape/free-proxy-list)"
        },
    )
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                if resp.status != 200:
                    raise SystemExit(f"API returned HTTP {resp.status} (skip={skip})")
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 5xx / 429 — retry with exponential backoff. 4xx other than 429
            # is a real client error, no point retrying.
            if e.code in (429, 500, 502, 503, 504):
                last_err = e
                backoff = 2 ** attempt
                print(
                    f"[update] skip={skip} got HTTP {e.code}; retry in {backoff}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})",
                    file=sys.stderr,
                )
                time.sleep(backoff)
                continue
            raise
        except urllib.error.URLError as e:
            last_err = e
            backoff = 2 ** attempt
            print(
                f"[update] skip={skip} network error: {e}; retry in {backoff}s",
                file=sys.stderr,
            )
            time.sleep(backoff)
    raise SystemExit(f"API failed after {MAX_RETRIES} retries (skip={skip}): {last_err}")


def fetch_all() -> list[dict[str, Any]]:
    """Page through the API until nextpage is false (or MAX_PAGES safety).

    The upstream API has a deep-pagination issue where requests beyond
    skip ≈ 10,000 currently return 500 due to a query-ordering bug
    (orderBy applied after skip/limit). If we hit that wall partway
    through, we keep whatever was fetched from successful pages rather
    than aborting the entire run. A snapshot of ~10k proxies is still
    useful — better than failing the workflow and shipping no update.
    First-page failures are real outages and re-raise.
    """
    out: list[dict[str, Any]] = []
    skip = 0
    for page in range(MAX_PAGES):
        try:
            payload = fetch_page(skip)
        except SystemExit as err:
            if not out:
                raise
            print(
                f"[update] Pagination ended at page {page + 1} (skip={skip}) — {err}. "
                f"Keeping {len(out)} proxies fetched so far.",
                file=sys.stderr,
            )
            break
        proxies = payload.get("proxies")
        if not isinstance(proxies, list):
            raise SystemExit("API response missing 'proxies' array")
        if not proxies:
            break
        out.extend(proxies)
        if not payload.get("nextpage"):
            break
        skip += PAGE_SIZE
        print(
            f"[update] Page {page + 1}: {len(proxies)} (running total {len(out)})",
            file=sys.stderr,
        )
        time.sleep(REQUEST_DELAY_S)
    return out


def round_uptime(uptime: Any) -> float | None:
    try:
        v = float(uptime)
    except (TypeError, ValueError):
        return None
    return round(v, 2)


def flatten(proxy: dict[str, Any]) -> dict[str, Any]:
    """Reduce upstream shape to the flat record we publish."""
    ip_data = proxy.get("ip_data") or {}
    # `ip_data.as` is a string like "AS131293 TOT Public Company Limited".
    # We split it into ASN + ASN org to match the conventions used by
    # GeoNode and ProxyDB.
    as_field = ip_data.get("as") or ""
    asn = ""
    if as_field.startswith("AS"):
        asn = as_field.split(" ", 1)[0]  # "AS131293"
    return {
        "protocol": (proxy.get("protocol") or "").lower(),
        "ip": proxy.get("ip") or "",
        "port": proxy.get("port"),
        "country": ip_data.get("country") or "",
        "country_code": (ip_data.get("countryCode") or "").upper(),
        "city": ip_data.get("city") or "",
        "anonymity": (proxy.get("anonymity") or "").lower(),
        "ssl": bool(proxy.get("ssl")),
        "uptime_percent": round_uptime(proxy.get("uptime")),
        "asn": asn,
        "isp": ip_data.get("isp") or "",
        "latency_ms": (
            round(float(proxy["timeout"]), 2)
            if isinstance(proxy.get("timeout"), (int, float))
            else None
        ),
        "last_checked": proxy.get("last_seen"),
    }


def render_txt(rows: Iterable[dict[str, Any]]) -> str:
    lines = []
    for r in rows:
        if not r["ip"] or not r["port"] or not r["protocol"]:
            continue
        lines.append(f"{r['protocol']}://{r['ip']}:{r['port']}")
    return "\n".join(lines) + ("\n" if lines else "")


def render_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, ensure_ascii=False) + "\n"


def render_csv(rows: Iterable[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_HEADER, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        # csv module renders None as empty string; convert bool to lowercase
        # for cross-language friendliness.
        out = dict(r)
        out["ssl"] = "true" if r["ssl"] else "false"
        writer.writerow(out)
    return buf.getvalue()


def write_shard(dirpath: str, rows: list[dict[str, Any]]) -> None:
    os.makedirs(dirpath, exist_ok=True)
    with open(os.path.join(dirpath, "data.txt"), "w", encoding="utf-8") as f:
        f.write(render_txt(rows))
    with open(os.path.join(dirpath, "data.json"), "w", encoding="utf-8") as f:
        f.write(render_json(rows))
    with open(os.path.join(dirpath, "data.csv"), "w", encoding="utf-8") as f:
        f.write(render_csv(rows))


def main() -> None:
    print(f"[update] Fetching from {API_BASE}", file=sys.stderr)
    raw = fetch_all()
    rows = [flatten(p) for p in raw]
    rows = [r for r in rows if r["ip"] and r["port"] and r["protocol"]]

    # Dedupe on (protocol, ip, port). Upstream pagination currently isn't
    # stable (orderBy is applied after skip/limit server-side), so the same
    # proxy can appear on multiple pages. Keeping the first occurrence is
    # fine — all duplicates carry identical identifying fields.
    seen: set[tuple[str, str, Any]] = set()
    deduped: list[dict[str, Any]] = []
    for r in rows:
        key = (r["protocol"], r["ip"], r["port"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    if len(deduped) != len(rows):
        print(
            f"[update] Deduped {len(rows) - len(deduped)} duplicate proxies",
            file=sys.stderr,
        )
    rows = deduped
    print(f"[update] Final unique proxy count: {len(rows)}", file=sys.stderr)

    # All
    write_shard(os.path.join(PROXIES_ROOT, "all"), rows)

    # Per protocol — 'https' is the HTTP-with-ssl subset, not a separate
    # upstream protocol value.
    by_proto: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_proto[r["protocol"]].append(r)
        if r["protocol"] == "http" and r["ssl"]:
            by_proto["https"].append(r)
    for proto in PROTOCOL_SHARDS:
        write_shard(
            os.path.join(PROXIES_ROOT, "protocols", proto),
            by_proto.get(proto, []),
        )

    # Per country (only emit shards for countries that actually have proxies)
    by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        cc = r["country_code"]
        if not cc or len(cc) != 2:
            continue
        by_country[cc].append(r)
    for cc, country_rows in by_country.items():
        write_shard(
            os.path.join(PROXIES_ROOT, "countries", cc.lower()),
            country_rows,
        )

    # Stats summary committed alongside the data so README badges and
    # downstream consumers can read counts without parsing data.json.
    stats = {
        "total": len(rows),
        "by_protocol": {p: len(by_proto.get(p, [])) for p in PROTOCOL_SHARDS},
        "countries": sorted(by_country.keys()),
        "country_count": len(by_country),
    }
    with open(os.path.join(PROXIES_ROOT, "stats.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(stats, indent=2) + "\n")

    print(
        f"[update] Wrote shards: 1 all, {len(PROTOCOL_SHARDS)} protocols, "
        f"{len(by_country)} countries.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
