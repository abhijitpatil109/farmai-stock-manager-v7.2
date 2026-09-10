#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


BASE_URL = os.getenv(
    "FARMAI_BASE_URL",
    "https://farmai-stock-manager-v7-2.vercel.app",
).rstrip("/")
API_KEY = os.getenv("FARMAI_API_KEY")


def load_dotenv():
    p = Path(".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k,v=line.split("=",1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get(path):
    if not API_KEY:
        raise RuntimeError("FARMAI_API_KEY is required for HTTP acceptance.")
    req = urllib.request.Request(
        BASE_URL + path,
        headers={"X-API-Key": API_KEY, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def main():
    load_dotenv()
    global API_KEY
    API_KEY = os.getenv("FARMAI_API_KEY")

    checks = []

    status, health = get("/api/v1/operations/health")
    data = health.get("data", {})
    checks.append(("health_200", status == 200))
    checks.append(("contract_oi12", data.get("contract_version") == "OI-1.2.0"))
    checks.append(("health_ready", data.get("status") == "READY"))

    status, stock = get("/api/v1/operations/stock")
    sd = stock.get("data", {})
    comp = sd.get("completeness", {})
    checks.append(("stock_200", status == 200))
    checks.append((
        "stock_complete_projection",
        comp.get("complete_active_product_projection") is True,
    ))
    checks.append((
        "stock_count_consistent",
        comp.get("active_product_count") == comp.get("returned_product_count"),
    ))

    status, hist = get(
        "/api/v1/operations/activity-history?limit=20"
    )
    hd = hist.get("data", {})
    checks.append(("history_200", status == 200))
    checks.append(("history_contract_oi12", hd.get("contract_version") == "OI-1.2.0"))

    failed = [name for name, ok in checks if not ok]
    print(json.dumps(
        {
            "base_url": BASE_URL,
            "checks": [{"name":n, "pass":ok} for n,ok in checks],
            "result": "PASS" if not failed else "FAIL",
            "failed": failed,
        },
        indent=2,
        default=str,
    ))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
