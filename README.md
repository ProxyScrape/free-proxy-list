# ProxyScrape Free Proxy List

> Free HTTP, HTTPS, SOCKS4 and SOCKS5 proxies — auto-refreshed every 5 minutes from the [ProxyScrape v4 API](https://docs.proxyscrape.com/api-reference/public-api/get-proxy-list).

[![Update Status](https://img.shields.io/github/actions/workflow/status/proxyscrape/free-proxy-list/update.yml?branch=main&label=auto-update)](https://github.com/proxyscrape/free-proxy-list/actions/workflows/update.yml)
[![Last Commit](https://img.shields.io/github/last-commit/proxyscrape/free-proxy-list?label=last%20update)](https://github.com/proxyscrape/free-proxy-list/commits/main)
[![Updated Every](https://img.shields.io/badge/refresh-every%205%20min-blue)](https://github.com/proxyscrape/free-proxy-list/blob/main/.github/workflows/update.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![ProxyScrape](https://img.shields.io/badge/by-ProxyScrape-1f6feb)](https://proxyscrape.com)

This is the official, machine-readable mirror of the [ProxyScrape free proxy list](https://proxyscrape.com/free-proxy-list). The same dataset is also available as a live JSON/CSV/TXT API at [`api.proxyscrape.com`](https://docs.proxyscrape.com/api-reference/public-api/get-proxy-list). Use whichever fits your workflow — the API is updated every minute; this repo refreshes every 5 minutes.

## Quick start

Pull the latest plain-text list from the jsDelivr CDN (always serves `main`):

```bash
curl https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/all/data.txt
```

Or just HTTP/HTTPS proxies:

```bash
curl https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/http/data.txt
```

Or JSON, with metadata per proxy (country, anonymity, latency, uptime, ASN…):

```bash
curl https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/all/data.json
```

## Repository layout

```
proxies/
├── all/                            All live proxies in one shard
│   ├── data.txt                    protocol://ip:port  (one per line)
│   ├── data.json                   array of objects with metadata
│   └── data.csv                    CSV with metadata columns
├── protocols/
│   ├── http/                       protocol=http
│   ├── https/                      protocol=http with ssl=true (CONNECT-capable)
│   ├── socks4/                     protocol=socks4
│   └── socks5/                     protocol=socks5
├── countries/
│   ├── us/                         lowercase ISO-3166 alpha-2 codes
│   ├── de/
│   └── …                           ~80–100 country shards depending on the run
└── stats.json                      summary: total count, per-protocol counts, country list
```

Every shard has the same three files: `data.txt`, `data.json`, `data.csv`.

## File formats

### `data.txt`
One proxy per line, formatted as `protocol://ip:port`:

```
http://203.0.113.4:8080
socks5://198.51.100.7:1080
socks4://192.0.2.91:4145
```

### `data.json`
Array of objects, one per proxy:

```json
[
  {
    "protocol": "http",
    "ip": "203.0.113.4",
    "port": 8080,
    "country": "Germany",
    "country_code": "DE",
    "city": "Falkenstein",
    "anonymity": "elite",
    "ssl": true,
    "uptime_percent": 92.71,
    "asn": "AS24940",
    "isp": "Hetzner Online GmbH",
    "latency_ms": 187.34,
    "last_checked": 1779919128.63
  }
]
```

### `data.csv`
Same columns as the JSON in header order:

```
protocol,ip,port,country,country_code,city,anonymity,ssl,uptime_percent,asn,isp,latency_ms,last_checked
http,203.0.113.4,8080,Germany,DE,Falkenstein,elite,true,92.71,AS24940,Hetzner Online GmbH,187.34,1779919128.63
```

### `stats.json`
```json
{
  "total": 22848,
  "by_protocol": { "http": 2302, "https": 0, "socks4": 372, "socks5": 20174 },
  "countries": ["AE", "AL", "AR", "…"],
  "country_count": 96
}
```

## CDN URLs

Each file is mirrored on jsDelivr for fast, global, cached access:

| What | URL |
|---|---|
| All — TXT | `https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/all/data.txt` |
| All — JSON | `https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/all/data.json` |
| All — CSV | `https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/all/data.csv` |
| HTTP only | `…/proxies/protocols/http/data.txt` |
| HTTPS only | `…/proxies/protocols/https/data.txt` |
| SOCKS4 only | `…/proxies/protocols/socks4/data.txt` |
| SOCKS5 only | `…/proxies/protocols/socks5/data.txt` |
| Per country | `…/proxies/countries/<iso-alpha-2>/data.txt` (lowercase) |
| Stats | `…/proxies/stats.json` |

Pin to a specific commit if you need reproducibility:

```
https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@<commit-sha>/proxies/all/data.txt
```

## Usage examples

### curl

```bash
# Plain text list of all proxies
curl https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/all/data.txt

# Pick a random elite German proxy via jq
curl -s https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/countries/de/data.json \
  | jq '[.[] | select(.anonymity == "elite")] | .[0]'
```

### Python

```python
import json, urllib.request, random

url = "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/socks5/data.json"
proxies = json.loads(urllib.request.urlopen(url).read())
elite = [p for p in proxies if p["anonymity"] == "elite" and p["uptime_percent"] and p["uptime_percent"] > 80]
print(random.choice(elite))
```

### Node.js

```js
const res = await fetch(
  "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/all/data.json"
);
const proxies = await res.json();
const fast = proxies.filter(p => p.latency_ms && p.latency_ms < 500);
console.log(`Found ${fast.length} sub-500ms proxies`);
```

## Want the live API instead?

The HTTP API behind this repo is documented at [docs.proxyscrape.com](https://docs.proxyscrape.com/api-reference/public-api/get-proxy-list). It updates **every minute** (this mirror updates every 5 minutes) and supports query-time filters (protocol, country, anonymity, timeout, ports, ASN) that this static mirror doesn't.

```bash
curl 'https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text&country=us&anonymity=elite'
```

## How it works

[`scripts/update.py`](scripts/update.py) is a single-file Python 3 script (stdlib only) that:

1. Pages through the v4 public API in 2,000-proxy batches with retry + backoff
2. Deduplicates on `(protocol, ip, port)`
3. Enriches each row with country / ASN / uptime / latency / SSL flag
4. Shards by protocol and country and writes `data.{txt,json,csv}` for each
5. Writes `proxies/stats.json` with the summary

The [`.github/workflows/update.yml`](.github/workflows/update.yml) action runs the script on a 5-minute cron, commits any changes, and pushes. Run it locally too:

```bash
python3 scripts/update.py
```

No dependencies — Python 3.10+, stdlib only.

## Caveats — read this if you actually plan to use these

These are **public, free proxies**. That means:

- **They are not safe.** Anyone can run a proxy that logs your traffic, injects content, or hijacks sessions. Never send credentials, cookies, or anything sensitive through them.
- **They are unstable.** A proxy that worked at the time of the last check may be dead 30 seconds later. Build retries and health checks into your client.
- **They are slow.** Latency is unpredictable, throughput is shared. Expect failures, not SLAs.
- **They may be blacklisted.** Many of these IPs are already known to anti-bot systems and reputation services.

If you need reliable proxies for production scraping, automation, or privacy, [ProxyScrape's paid plans](https://proxyscrape.com/pricing) (datacenter, residential, mobile) start at a few cents per proxy.

## License

Code in this repository — including `scripts/update.py` and the workflow — is MIT licensed; see [LICENSE](LICENSE). The proxy data itself is collected from public sources and provided as-is, with no warranty of fitness for any purpose.

## Links

- 🌐 Website: [proxyscrape.com/free-proxy-list](https://proxyscrape.com/free-proxy-list)
- 🔌 API docs: [docs.proxyscrape.com](https://docs.proxyscrape.com/api-reference/public-api/get-proxy-list)
- 🛠 Free proxy checker (online): [proxyscrape.com/online-proxy-checker](https://proxyscrape.com/online-proxy-checker)
- 🖥 Free proxy checker (desktop, open source): [proxyscrape.com/proxy-checker](https://proxyscrape.com/proxy-checker)
- 💬 Discord: [discord.gg/scrape](https://discord.gg/scrape)
