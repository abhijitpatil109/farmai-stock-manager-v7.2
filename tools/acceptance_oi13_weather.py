#!/usr/bin/env python3
"""Validate OI-1.3 schema locally and optionally test the deployed spray window."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


REQUIRED_OPERATION = "getBestOperationalSprayWindow"
REQUIRED_PATH = "/api/v1/operations/spray-window"


def check_schema(path: Path):
    schema = json.loads(path.read_text(encoding="utf-8"))
    operation = schema.get("paths", {}).get(REQUIRED_PATH, {}).get("post", {})
    body_schema = (
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    ref = body_schema.get("$ref", "")
    request_name = ref.rsplit("/", 1)[-1] if ref else ""
    request_schema = schema.get("components", {}).get("schemas", {}).get(request_name, {})
    properties = request_schema.get("properties", {})
    descriptions = [
        operation.get("description", "")
        for path_item in schema.get("paths", {}).values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
        and isinstance(operation, dict)
    ]
    return [
        ("operation_exposed", operation.get("operationId") == REQUIRED_OPERATION),
        ("mandatory_routing_description", "MANDATORY" in operation.get("description", "")),
        ("farm_name_supported", "farm_name" in properties),
        ("crop_name_supported", "crop_name" in properties),
        ("relative_day_supported", "target_day" in properties),
        ("coordinates_not_requested", "latitude" not in properties and "longitude" not in properties),
        ("refresh_defaults_true", properties.get("refresh_before_assessment", {}).get("default") is True),
        ("all_operation_descriptions_within_300", all(len(x) <= 300 for x in descriptions)),
    ]


def live_check(base_url: str, api_key: str, farm_name: str, crop_name: str):
    body = json.dumps({
        "farm_name": farm_name,
        "crop_name": crop_name,
        "target_day": "TOMORROW",
        "expected_duration_minutes": 120,
        "rainfast_minutes": None,
        "refresh_before_assessment": True,
        "persist": False,
    }).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + REQUIRED_PATH,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-API-Key": api_key,
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data", {})
    context = data.get("resolved_context", {})
    return [
        ("live_http_ok", payload.get("ok") is True),
        ("stored_geotag_resolved", bool(context.get("weather_location_id"))),
        ("farm_resolved", bool(context.get("farm_id"))),
        ("crop_resolved", bool(context.get("crop_cycle_id"))),
        ("recommendation_present", data.get("recommendation") in {
            "SPRAY", "CONDITIONAL", "AVOID", "INSUFFICIENT_DATA"
        }),
        ("primary_window_or_insufficient", bool(data.get("primary_window")) or data.get("recommendation") == "INSUFFICIENT_DATA"),
    ], data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("openapi/FarmAI_GPT_Focused_OpenAPI_OI1_3.json"),
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--base-url",
        default=os.getenv("FARMAI_BASE_URL", "https://farmai-stock-manager-v7-2.vercel.app"),
    )
    parser.add_argument("--farm-name", default="Bendri")
    parser.add_argument("--crop-name", default="Drumstick")
    args = parser.parse_args()

    checks = check_schema(args.schema)
    evidence = None
    if args.live:
        api_key = os.getenv("FARMAI_API_KEY")
        if not api_key:
            parser.error("FARMAI_API_KEY is required with --live")
        try:
            live_checks, evidence = live_check(
                args.base_url, api_key, args.farm_name, args.crop_name
            )
            checks.extend(live_checks)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(json.dumps({"http_status": exc.code, "body": body}, indent=2))
            return 1

    failed = [name for name, passed in checks if not passed]
    print(json.dumps({
        "result": "PASS" if not failed else "FAIL",
        "checks": [{"name": name, "pass": passed} for name, passed in checks],
        "failed": failed,
        "live_evidence": evidence,
    }, indent=2, default=str))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
