"""Gửi một request /chat với x-request-id cố định (dùng cho prompt versioning/rollback).

    python scripts/send_chat.py req-b0000001
    python scripts/send_chat.py req-c0000001 --message "What is the refund policy?"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

BASE_URL = "http://127.0.0.1:8000"


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_id", help="Giá trị x-request-id, ví dụ req-b0000001")
    parser.add_argument("--message", default="What is the refund policy?")
    parser.add_argument("--feature", default="qa")
    args = parser.parse_args()

    r = httpx.post(
        f"{BASE_URL}/chat",
        headers={"x-request-id": args.request_id},
        json={"user_id": "u_demo", "session_id": "s_prompt_demo", "feature": args.feature, "message": args.message},
        timeout=30.0,
    )
    print(r.status_code, "x-request-id:", r.headers.get("x-request-id"))
    print(r.json())


if __name__ == "__main__":
    main()
