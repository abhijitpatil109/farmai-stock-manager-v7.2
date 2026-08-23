#!/usr/bin/env python3
"""
FarmAI Activity Register V1 backend installer.

Purpose:
- Copy the supplied NEW Activity Register files into the current FarmAI repo.
- Patch app/main.py safely with only the router import + include registration.
- Preserve all existing Stock Manager code.
- Create a timestamped main.py backup before changing it.

Run from the FarmAI repository root:
    python tools/install_activity_register_backend_v1.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sys


ROOT = Path.cwd()
PACKAGE_ROOT = Path(__file__).resolve().parents[1]

FILES = {
    PACKAGE_ROOT / "app/api/v1/activity_register.py": ROOT / "app/api/v1/activity_register.py",
    PACKAGE_ROOT / "app/services/activity_register.py": ROOT / "app/services/activity_register.py",
    PACKAGE_ROOT / "app/schemas/activity_register.py": ROOT / "app/schemas/activity_register.py",
}

MAIN = ROOT / "app/main.py"
IMPORT_LINE = "from .api.v1.activity_register import router as activity_register_router"
INCLUDE_LINE = "app.include_router(activity_register_router)"


def fail(message: str):
    print(f"ERROR: {message}")
    sys.exit(1)


if not MAIN.exists():
    fail("app/main.py was not found. Run this installer from the FarmAI repository root.")

text = MAIN.read_text(encoding="utf-8")

for source, target in FILES.items():
    if not source.exists():
        fail(f"Package file missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    print(f"Installed: {target.relative_to(ROOT)}")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = MAIN.with_name(f"main.py.backup_activity_{stamp}")
shutil.copy2(MAIN, backup)
print(f"Backup: {backup.relative_to(ROOT)}")

if IMPORT_LINE not in text:
    anchor = "from .api.v1.health import router as health_router"
    if anchor not in text:
        fail("Could not find the expected router-import anchor in app/main.py.")
    text = text.replace(anchor, anchor + "\n" + IMPORT_LINE, 1)

if INCLUDE_LINE not in text:
    anchor = "app.include_router(health_router)"
    if anchor not in text:
        fail("Could not find the expected router-registration anchor in app/main.py.")
    text = text.replace(anchor, anchor + "\n" + INCLUDE_LINE, 1)

MAIN.write_text(text, encoding="utf-8")
print("Updated: app/main.py")
print("Activity Register backend foundation installation completed.")
