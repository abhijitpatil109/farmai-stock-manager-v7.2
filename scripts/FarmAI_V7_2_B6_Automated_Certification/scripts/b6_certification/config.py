from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str
    location_code: str = "MAIN"
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "Config":
        base_url = os.getenv(
            "BASE_URL",
            "https://farmai-stock-manager-v7-2.vercel.app",
        ).rstrip("/")

        api_key = os.getenv("FARMAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "FARMAI_API_KEY is not set. "
                "Export it before running B6 certification."
            )

        return cls(
            base_url=base_url,
            api_key=api_key,
            location_code=os.getenv("FARMAI_LOCATION_CODE", "MAIN"),
            timeout_seconds=int(os.getenv("FARMAI_TIMEOUT_SECONDS", "30")),
        )
