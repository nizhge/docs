#!/usr/bin/env python3
"""Read-only Meta Threads account check for GitHub Actions.

This never creates media containers, publishes, refreshes, or displays tokens.
An identity match does not prove that content-publishing scope was granted.
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROFILE_URL = "https://graph.threads.com/v1.0/me?fields=id,username"


class AuthCheckError(Exception):
    """A safe error code, never an HTTP response or bearer credential."""

    def __init__(self, status: str, http_status: int | None = None, meta_code: int | None = None):
        super().__init__(status)
        self.status = status
        self.http_status = http_status
        self.meta_code = meta_code


def get_profile(token: str, opener=urlopen) -> dict:
    request = Request(PROFILE_URL, method="GET", headers={"Authorization": f"Bearer {token}"})
    try:
        with opener(request, timeout=25) as response:
            payload = json.loads(response.read(160_000))
    except HTTPError as exc:
        code = None
        try:
            response = json.loads(exc.read(8_192))
            reported = response.get("error", {}).get("code")
            if isinstance(reported, int):
                code = reported
        except (ValueError, TypeError, AttributeError):
            pass
        raise AuthCheckError("THREADS_HTTP_ERROR", http_status=exc.code, meta_code=code) from None
    except URLError:
        raise AuthCheckError("THREADS_NETWORK_ERROR") from None
    except (ValueError, UnicodeError, TypeError):
        raise AuthCheckError("THREADS_INVALID_RESPONSE") from None
    if not isinstance(payload, dict):
        raise AuthCheckError("THREADS_INVALID_RESPONSE")
    return payload


def check_auth(token: str, expected_username: str, expected_user_id: str = "", fetcher=get_profile) -> dict:
    """Check account identity only, never claim publish scope or live success."""
    expected_username = expected_username.strip().lstrip("@").casefold()
    expected_user_id = expected_user_id.strip()
    if not token:
        return {"status": "MISSING_THREADS_ACCESS_TOKEN", "ok": False}
    if not expected_username:
        return {"status": "MISSING_THREADS_USERNAME", "ok": False}
    if not re.fullmatch(r"[a-z0-9_.]{1,30}", expected_username):
        return {"status": "INVALID_THREADS_USERNAME", "ok": False}
    if expected_user_id and not expected_user_id.isdigit():
        return {"status": "INVALID_THREADS_USER_ID", "ok": False}
    try:
        profile = fetcher(token)
    except AuthCheckError as exc:
        result = {"status": exc.status, "ok": False}
        if exc.http_status is not None:
            result["http_status"] = exc.http_status
        if exc.meta_code is not None:
            result["meta_code"] = exc.meta_code
        return result
    except Exception:
        # Never stringify an exception, which could contain a credential or URL.
        return {"status": "THREADS_CHECK_FAILED", "ok": False}
    account_id = str(profile.get("id", ""))
    username = str(profile.get("username", "")).lstrip("@").casefold()
    if not account_id.isdigit() or not username:
        return {"status": "THREADS_INCOMPLETE_PROFILE", "ok": False}
    if username != expected_username:
        return {"status": "THREADS_WRONG_ACCOUNT", "ok": False, "expected": expected_username,
                "actual": username}
    if expected_user_id and account_id != expected_user_id:
        return {"status": "THREADS_WRONG_USER_ID", "ok": False, "username": username}
    return {"status": "IDENTITY_VERIFIED_PUBLISH_SCOPE_UNCHECKED", "ok": True,
            "username": username, "user_id": account_id,
            "posting_enabled": False, "publish_scope_verified": False}


def main() -> int:
    result = check_auth(os.environ.get("THREADS_ACCESS_TOKEN", ""),
                        os.environ.get("THREADS_USERNAME", ""),
                        os.environ.get("THREADS_USER_ID", ""))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
