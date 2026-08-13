from __future__ import annotations

from client import FarmAIClient
from config import Config
from state import load_state


def main():
    config = Config.from_env()
    client = FarmAIClient(config)
    state = load_state()

    if not state:
        print("No B6 state file found.")
        return 1

    print("=" * 64)
    print("FarmAI B6 Cleanup Preview")
    print("=" * 64)
    print(f"Run ID: {state.get('run_id')}")
    print()

    products = state.get("products", [])
    for product in products:
        code = product["product_code"]
        print(f"Product: {code} — {product['product_name']}")

        inv = client.get(f"/api/v1/inventory/{code}")
        print(f"  Inventory HTTP: {inv.status}")
        print(f"  Inventory: {FarmAIClient.data(inv.body)}")

        tx = client.get(
            "/api/v1/transactions",
            {"product_code": code, "limit": 100},
        )
        print(f"  Transactions HTTP: {tx.status}")
        print(f"  Transactions: {FarmAIClient.data(tx.body)}")
        print()

    print("PREVIEW ONLY — no data was changed.")
    print()
    print(
        "Use cleanup_b6.sql only after reviewing these products and "
        "transactions. Do not hard-delete ledger history."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
