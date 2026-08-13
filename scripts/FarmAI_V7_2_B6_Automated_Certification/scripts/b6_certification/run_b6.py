from __future__ import annotations

import sys

from config import Config
from report import CertificationReport
from state import save_state
from tests import run_all


def main():
    try:
        config = Config.from_env()
    except Exception as exc:
        print(f"CONFIG ERROR: {exc}")
        return 2

    print("=" * 64)
    print("FarmAI Stock Manager V7.2 — Automated B6 Certification")
    print("=" * 64)
    print(f"Target: {config.base_url}")
    print("Authentication: X-API-Key from environment")
    print()

    report = CertificationReport()
    state = run_all(config, report)
    save_state(state)

    print()
    print("B6 state written to:")
    print("scripts/b6_certification/b6_state.json")
    print()

    return report.summary()


if __name__ == "__main__":
    sys.exit(main())
