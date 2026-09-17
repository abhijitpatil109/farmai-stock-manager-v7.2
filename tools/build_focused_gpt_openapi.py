#!/usr/bin/env python3
"""Build the focused FarmAI GPT Action schema from the live FastAPI contract."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.main import app


SELECTED_OPERATION_IDS = {
    "getOperationalHealth",
    "getOperationalCapabilities",
    "getOperationalStock",
    "getOperationalActivityHistory",
    "getOperationalContext",
    "getOperationalCropDecisionContext",
    "getBestOperationalSprayWindow",
    "checkOperationalWeather",
    "previewOperationalActivity",
    "completeOperationalActivity",
    "searchProducts",
    "getProduct",
    "getProductInventory",
    "getStockTransactions",
    "createProduct",
    "recordStockPurchase",
    "recordBatchStockPurchase",
}

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def _schema_names(value):
    names = set()
    if isinstance(value, dict):
        ref = value.get("$ref")
        prefix = "#/components/schemas/"
        if isinstance(ref, str) and ref.startswith(prefix):
            names.add(ref[len(prefix):])
        for child in value.values():
            names.update(_schema_names(child))
    elif isinstance(value, list):
        for child in value:
            names.update(_schema_names(child))
    return names


def build_focused_schema():
    source = app.openapi()
    paths = {}
    found = set()
    for path, path_item in source.get("paths", {}).items():
        selected = {}
        for method, operation in path_item.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if operation_id in SELECTED_OPERATION_IDS:
                selected[method] = copy.deepcopy(operation)
                found.add(operation_id)
        if selected:
            paths[path] = selected

    missing = sorted(SELECTED_OPERATION_IDS - found)
    if missing:
        raise RuntimeError("Selected operationIds missing from FastAPI: " + ", ".join(missing))

    source_schemas = source.get("components", {}).get("schemas", {})
    needed = _schema_names(paths)
    schemas = {}
    pending = list(needed)
    while pending:
        name = pending.pop()
        if name in schemas:
            continue
        if name not in source_schemas:
            raise RuntimeError(f"Unresolved component schema: {name}")
        value = copy.deepcopy(source_schemas[name])
        schemas[name] = value
        pending.extend(_schema_names(value) - schemas.keys())

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "FarmAI GPT Operational Actions",
            "version": "OI-1.3.1",
            "description": (
                "Focused FarmAI Action surface for authoritative stock, activity, "
                "purchase, crop decision and geotag-resolved spray-window workflows."
            ),
        },
        "servers": copy.deepcopy(source.get("servers", [])),
        "paths": paths,
        "components": {
            "securitySchemes": copy.deepcopy(
                source.get("components", {}).get("securitySchemes", {})
            ),
            "schemas": dict(sorted(schemas.items())),
        },
    }


def validate(schema):
    operation_ids = []
    for path_item in schema["paths"].values():
        for method, operation in path_item.items():
            if method in HTTP_METHODS:
                operation_ids.append(operation["operationId"])
    if len(operation_ids) != len(set(operation_ids)):
        raise RuntimeError("Duplicate operationId found in focused schema.")
    if len(operation_ids) > 30:
        raise RuntimeError("Focused schema exceeds the Custom GPT 30-operation limit.")
    oversized = []
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            description = operation.get("description", "")
            if len(description) > 300:
                oversized.append(
                    f"{operation['operationId']}={len(description)} chars at {method.upper()} {path}"
                )
    if oversized:
        raise RuntimeError(
            "Custom GPT operation descriptions exceed 300 characters: "
            + "; ".join(oversized)
        )
    unresolved = []
    for name in _schema_names(schema):
        if name not in schema["components"]["schemas"]:
            unresolved.append(name)
    if unresolved:
        raise RuntimeError("Unresolved references: " + ", ".join(sorted(set(unresolved))))
    return operation_ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("openapi/FarmAI_GPT_Focused_OpenAPI_OI1_3.json"),
    )
    args = parser.parse_args()
    schema = build_focused_schema()
    operation_ids = validate(schema)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "output": str(args.output),
        "operation_count": len(operation_ids),
        "operations": sorted(operation_ids),
    }, indent=2))


if __name__ == "__main__":
    main()
