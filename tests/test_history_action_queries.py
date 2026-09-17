"""Exercise query parsing through ASGI without a database or extra HTTP client."""
import asyncio
from datetime import date
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from uuid import UUID

from app.main import app
from app.core.security import require_api_key
from tools.build_focused_gpt_openapi import build_focused_schema, validate


async def request(params):
    messages = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        messages.append(message)
    path = "/api/v1/operations/activity-history"
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": urlencode(params).encode(), "headers": [], "root_path": "",
        "server": ("test", 80), "client": ("127.0.0.1", 1),
    }
    await app(scope, receive, send)
    body = b"".join(m.get("body", b"") for m in messages)
    return messages[0]["status"], json.loads(body)


class HistoryActionQueryTests(unittest.TestCase):
    def setUp(self):
        self.overrides = dict(app.dependency_overrides)
        app.dependency_overrides[require_api_key] = lambda: "test-key"
        self.patcher = patch("app.api.v1.operational_integration.operational_activity_history")
        self.reader = self.patcher.start()
        self.reader.return_value = {"history": [{"execution_status": "COMPLETED"}], "summary": {"returned_rows": 1}}

    def tearDown(self):
        self.patcher.stop()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.overrides)

    def test_minimal_request_matches_null_and_blank_unused_filters(self):
        baseline = asyncio.run(request({"crop_name": "Turmeric"}))
        expected_arguments = self.reader.call_args.kwargs.copy()
        for placeholder in ("", "null", "None", " NULL "):
            with self.subTest(placeholder=placeholder):
                status, body = asyncio.run(request({
                    "crop_name": " Turmeric ", "crop_cycle_id": placeholder,
                    "date_from": placeholder, "date_to": placeholder,
                    "execution_status": placeholder,
                }))
                self.assertEqual(status, 200)
                self.assertEqual(body["data"], baseline[1]["data"])
                self.assertEqual(self.reader.call_args.kwargs, expected_arguments)

    def test_valid_filters_preserve_ids_and_dates(self):
        uid = "11111111-1111-1111-1111-111111111111"
        status, _ = asyncio.run(request({"crop_cycle_id": uid, "date_from": "2026-08-01",
                                        "date_to": "2026-09-18", "execution_status": " completed "}))
        self.assertEqual(status, 200)
        kwargs = self.reader.call_args.kwargs
        self.assertEqual(kwargs["crop_cycle_id"], UUID(uid))
        self.assertEqual(kwargs["date_from"], date(2026, 8, 1))
        self.assertEqual(kwargs["date_to"], date(2026, 9, 18))
        self.assertEqual(kwargs["execution_status"], "COMPLETED")

    def test_all_statuses_omits_status_filter(self):
        status, _ = asyncio.run(request({"crop_name": "Turmeric", "execution_status": "all"}))
        self.assertEqual(status, 200)
        self.assertIsNone(self.reader.call_args.kwargs["execution_status"])

    def test_invalid_filters_do_not_reach_database(self):
        for key, value in (("crop_cycle_id", "unknown-id"), ("date_from", "yesterday"),
                           ("execution_status", "TYPO"), ("limit", "501")):
            with self.subTest(key=key):
                self.reader.reset_mock()
                status, body = asyncio.run(request({"crop_name": "Turmeric", key: value}))
                self.assertEqual(status, 422)
                self.assertEqual(body["detail"][0]["loc"], ["query", key])
                self.reader.assert_not_called()

    def test_authentication_remains_required(self):
        app.dependency_overrides.pop(require_api_key)
        with patch.dict("os.environ", {"FARMAI_API_KEY": "test-only-key"}):
            status, _ = asyncio.run(request({"crop_name": "Turmeric"}))
        self.assertEqual(status, 401)
        self.reader.assert_not_called()

    def test_action_schema_uses_omission_for_unused_query_fields(self):
        schema = build_focused_schema()
        self.assertEqual(len(validate(schema)), 17)
        operation = schema["paths"]["/api/v1/operations/activity-history"]["get"]
        for param in operation["parameters"]:
            self.assertFalse(param["required"])
            self.assertNotIn("anyOf", param["schema"])
        fields = {p["name"]: p["schema"] for p in operation["parameters"]}
        self.assertEqual(fields["crop_cycle_id"]["format"], "uuid")
        self.assertEqual(fields["date_from"]["format"], "date")
        self.assertIn("COMPLETED", fields["execution_status"]["enum"])
        self.assertEqual(fields["limit"]["default"], 200)

    def test_consolidated_instructions_fit_gpt_limit(self):
        path = Path(__file__).resolve().parents[1] / "docs/gpt/OI13_GPT_INSTRUCTION.txt"
        self.assertLessEqual(len(path.read_text(encoding="utf-8")), 8000)
