#!/usr/bin/env python3
"""
FarmAI V7.2 — B6 Cleanup Executor

Purpose
-------
Neutralize stock created by the latest automated B6 certification run
without deleting audit history.

Behavior
--------
- Reads b6_state.json produced by run_b6.py.
- Reads current live inventory for each B6 test product.
- In preview mode, changes nothing.
- With --confirm, posts a physical verification adjustment to 0 stock
  for each B6 test product that still has non-zero physical stock.
- Uses deterministic cleanup idempotency keys.
- Re-reads inventory after each adjustment.
- Does NOT deactivate products; run deactivate_b6_products.sql separately.

Usage
-----
Preview:
    python3 scripts/b6_certification/cleanup_execute.py

Execute:
    python3 scripts/b6_certification/cleanup_execute.py --confirm
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation

from client import FarmAIClient
from config import Config
from state import load_state


def to_decimal(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def extract_inventory(body):
    data = FarmAIClient.data(body)

    if isinstance(data, list):
        return data[0] if data else {}

    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            return data["items"][0] if data["items"] else {}
        return data

    return {}


def physical_stock(inv):
    for key in (
        "physical_stock",
        "current_physical_stock",
        "physical",
    ):
        if key in inv:
            return to_decimal(inv.get(key))
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually post zero-stock verification adjustments.",
    )
    args = parser.parse_args()

    config = Config.from_env()
    client = FarmAIClient(config)
    state = load_state()

    if not state:
        print("ERROR: b6_state.json was not found or is empty.")
        return 2

    run_id = state.get("run_id", "unknown")
    products = state.get("products", [])

    if not products:
        print("ERROR: No B6 products found in b6_state.json.")
        return 2

    print("=" * 72)
    print("FarmAI V7.2 — B6 Cleanup")
    print("=" * 72)
    print(f"Run ID : {run_id}")
    print(f"Mode   : {'EXECUTE' if args.confirm else 'PREVIEW ONLY'}")
    print()

    failures = 0

    for product in products:
        code = product["product_code"]
        name = product.get("product_name", "")

        read = client.get(f"/api/v1/inventory/{code}")
        if read.status != 200:
            print(f"FAIL {code} — inventory read HTTP {read.status}")
            failures += 1
            continue

        inv = extract_inventory(read.body)
        qty = physical_stock(inv)
        unit = inv.get("unit") or inv.get("base_unit") or "kg"

        print(f"{code} — {name}")
        print(f"  Current physical stock: {qty} {unit}")

        if qty is None:
            print("  FAIL: physical stock could not be determined.")
            failures += 1
            print()
            continue

        if qty == 0:
            print("  No stock neutralization required.")
            print()
            continue

        if not args.confirm:
            print(f"  WOULD ADJUST: {qty} {unit} -> 0 {unit}")
            print()
            continue

        key = f"b6-cleanup-{run_id}-{code}".lower()

        result = client.post(
            "/api/v1/inventory/adjustments",
            {
                "product_code": code,
                "verified_quantity": 0,
                "unit": unit,
                "location_code": config.location_code,
                "idempotency_key": key,
                "reason": "B6 certification cleanup",
                "notes": (
                    f"Neutralize stock created by B6 certification run {run_id}. "
                    "Audit history intentionally preserved."
                ),
            },
        )

        if result.status != 200:
            print(f"  FAIL: adjustment HTTP {result.status}")
            print(f"  Response: {result.body}")
            failures += 1
            print()
            continue

        verify = client.get(f"/api/v1/inventory/{code}")
        verify_inv = extract_inventory(verify.body)
        final_qty = physical_stock(verify_inv)

        if verify.status == 200 and final_qty == 0:
            print("  PASS: stock neutralized to 0.")
        else:
            print(
                f"  FAIL: post-cleanup verification returned "
                f"{final_qty} (HTTP {verify.status})"
            )
            failures += 1

        print()

    print("=" * 72)

    if not args.confirm:
        print("PREVIEW COMPLETE — no data changed.")
        print()
        print("If every listed product is a B6 certification product, run:")
        print(
            "python3 scripts/b6_certification/cleanup_execute.py --confirm"
        )
        return 0

    if failures:
        print(f"CLEANUP RESULT: FAIL ({failures} problem(s))")
        print("Do not deactivate products until these are resolved.")
        return 1

    print("CLEANUP RESULT: PASS")
    print("All latest-run B6 product stock has been neutralized.")
    print("Next: deactivate B6 CERT products using deactivate_b6_products.sql.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
