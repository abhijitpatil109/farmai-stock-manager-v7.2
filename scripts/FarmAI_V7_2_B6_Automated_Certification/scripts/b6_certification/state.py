from __future__ import annotations

import json
from pathlib import Path


STATE_FILE = Path(__file__).with_name("b6_state.json")


def save_state(data: dict):
    STATE_FILE.write_text(
        json.dumps(data, indent=2, default=str),
        encoding="utf-8",
    )


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))
