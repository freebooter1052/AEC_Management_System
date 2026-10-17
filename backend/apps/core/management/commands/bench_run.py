"""
API latency benchmark against a running server (docs/SPRINT3_TEST_REPORT.md, "Benchmarks").

    python manage.py runserver 127.0.0.1:8001          # with COUCHDB_NAME=aec_bench_...
    python manage.py bench_run --base-url http://127.0.0.1:8001 --requests 200 --concurrency 1 8
    python manage.py bench_run --base-url http://127.0.0.1:8001 http://127.0.0.1:8002 ...   # several server processes

Signs in as the accounts `bench_seed` created (they exist only in benchmark databases, so pointing this at
any other server fails at sign-in). Latency is measured at the HTTP client: it includes the server, the
CouchDB queries and the loopback network, not browser rendering. Every scenario is warmed up first (one
request per account) so index builds and the throttled reminder sweep are reported separately as
`first_ms`, then `--requests` requests are spread over the accounts at each `--concurrency`. With several
`--base-url`s (server processes sharing one DJANGO_SECRET_KEY and database) requests are spread round-robin,
which shows how throughput scales with worker processes.
Writes JSON results to --out (default ../output/benchmarks/, git-ignored).
"""

import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from .bench_seed import BENCH_PASSWORD

# (name, role, method, path)
SCENARIOS = [
    ("dashboard: admin", "admin", "GET", "/api/dashboard/"),
    ("dashboard: counsellor", "counsellor", "GET", "/api/dashboard/"),
    ("dashboard: student", "student", "GET", "/api/dashboard/"),
    ("students list: counsellor", "counsellor", "GET", "/api/students/?page=1"),
    ("applications list: admin", "admin", "GET", "/api/applications/?page=1"),
    ("applications list: counsellor", "counsellor", "GET", "/api/applications/?page=1"),
    ("applications summary: admin", "admin", "GET", "/api/applications/summary/"),
    ("documents summary: admin", "admin", "GET", "/api/documents/summary/"),
    ("documents review queue: counsellor", "counsellor", "GET", "/api/documents/"),
    ("notifications list: student", "student", "GET", "/api/notifications/"),
    ("unread count: student", "student", "GET", "/api/notifications/unread-count/"),
    ("recommendations list: student", "student", "GET", "/api/recommendations/"),
    ("recommendations generate: student", "student", "POST", "/api/recommendations/generate/"),
]


def call(base, method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else (b"{}" if method == "POST" else None)
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            payload = res.read()
            status = res.status
    except urllib.error.HTTPError as exc:
        payload, status = exc.read(), exc.code
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        payload, status = b"", 0
    return (time.perf_counter() - start) * 1000, status, payload


def pct(values, q):
    values = sorted(values)
    return round(values[min(len(values) - 1, int(round(q * (len(values) - 1))))], 1) if values else None


class Command(BaseCommand):
    help = "Measure p50/p95 API latency, throughput and errors against a server running on a bench database."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", nargs="+", default=["http://127.0.0.1:8001"])
        parser.add_argument("--requests", type=int, default=200, help="Measured requests per scenario and concurrency.")
        parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 8])
        parser.add_argument("--accounts", type=int, default=8, help="Distinct students/counsellors to rotate through.")
        parser.add_argument("--only", default="", help="Run only scenarios whose name contains this text.")
        parser.add_argument("--label", default="", help="Dataset label for the report, e.g. 10k.")
        parser.add_argument("--out", default="")

    def login(self, base, email, required=True):
        _, status, payload = call(base, "POST", "/api/auth/login/", body={"email": email, "password": BENCH_PASSWORD})
        if status != 200:
            if not required:
                return None
            raise CommandError(f"Could not sign in as {email} ({status}). Is the server running on a bench_seed database?")
        return json.loads(payload)["token"]

    def logins(self, base, role, n):
        """Up to n accounts of a role (small datasets have fewer counsellors than --accounts)."""
        tokens = []
        for i in range(n):
            token = self.login(base, f"{role}{i}@bench.example.org", required=not tokens)
            if token is None:
                break
            tokens.append(token)
        return tokens

    def handle(self, *args, **o):
        bases = [u.rstrip("/") for u in o["base_url"]]
        base = bases[0]
        n = o["accounts"]
        tokens = {
            "admin": [self.login(base, "admin@bench.example.org")],
            "counsellor": self.logins(base, "counsellor", n),
            "student": self.logins(base, "student", n),
        }
        results = []
        for name, role, method, path in SCENARIOS:
            if o["only"] and o["only"] not in name:
                continue
            first = [call(base, method, path, t)[0] for t in tokens[role]]  # warm-up: one per account
            for conc in o["concurrency"]:
                jobs = [(bases[i % len(bases)], tokens[role][i % len(tokens[role])]) for i in range(o["requests"])]
                start = time.perf_counter()
                with ThreadPoolExecutor(max_workers=conc) as pool:
                    out = list(pool.map(lambda job: call(job[0], method, path, job[1])[:2], jobs))
                wall = time.perf_counter() - start
                lat = [ms for ms, _ in out]
                row = {"scenario": name, "concurrency": conc, "processes": len(bases), "requests": len(out),
                       "ok": sum(1 for _, s in out if 200 <= s < 300), "http_4xx": sum(1 for _, s in out if 400 <= s < 500),
                       "http_5xx_or_failed": sum(1 for _, s in out if s >= 500 or s == 0),
                       "p50_ms": pct(lat, .5), "p95_ms": pct(lat, .95), "max_ms": round(max(lat), 1),
                       "mean_ms": round(statistics.fmean(lat), 1), "rps": round(len(out) / wall, 1),
                       "first_ms": round(max(first), 1)}
                results.append(row)
                self.stdout.write(f"  {name:<38} c={conc:<2} w={len(bases)} p50 {row['p50_ms']:>7} ms  p95 {row['p95_ms']:>7} ms  "
                                  f"{row['rps']:>6} req/s  ok {row['ok']}/{row['requests']}  5xx {row['http_5xx_or_failed']}  "
                                  f"first {row['first_ms']} ms")
        out_path = Path(o["out"]) if o["out"] else settings.REPO_ROOT / "output" / "benchmarks" / (
            f"bench-{o['label'] or settings.COUCHDB_NAME}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"label": o["label"], "base_urls": bases, "database": settings.COUCHDB_NAME,
                                        "measured_at": datetime.now(timezone.utc).isoformat(), "results": results}, indent=1))
        self.stdout.write(self.style.SUCCESS(f"Results written to {out_path}"))
