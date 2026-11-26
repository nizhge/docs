#!/usr/bin/env python3
"""Verify and save a Publora Threads connection; never creates or publishes posts.

Official contract: https://docs.publora.com/endpoints/platform-connections
The active flag is Publora's cached connection verdict, not a live posting test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse
from urllib.request import Request, build_opener

from meta_connection import read_settings, write_private, secret_input, validate_secret
from publish_publora import NoRedirect

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "private" / "connection.env"
METADATA_PATH = ROOT / "private" / "publora_connection.json"
CONNECTIONS_URL = "https://api.publora.com/api/v1/platform-connections"


def list_connections(key, opener=None):
    """Read the public API using the key in a header, never a URL or log."""
    request = Request(CONNECTIONS_URL, headers={"x-publora-key": validate_secret(key),
                                              "Accept": "application/json"}, method="GET")
    opener = opener or build_opener(NoRedirect()).open
    with opener(request, timeout=25) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Publora connection response is too large")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("Publora did not confirm the connections lookup")
    connections = payload.get("connections")
    if not isinstance(connections, list) or any(not isinstance(c, dict) for c in connections):
        raise ValueError("Publora returned an invalid connection list")
    return connections


def verify_connection(key, username, expected_platform_id="", reader=list_connections):
    key = validate_secret(key)
    username = username.lstrip("@").casefold()
    if not re.fullmatch(r"[a-z0-9_.]{1,30}", username):
        raise ValueError("An exact intended Threads username is required")
    matches = [c for c in reader(key)
               if re.fullmatch(r"threads-\d+", str(c.get("platformId", "")))
               and str(c.get("username") or "").lstrip("@").casefold() == username]
    if expected_platform_id:
        matches = [c for c in matches if c["platformId"] == expected_platform_id]
    if len(matches) != 1:
        raise ValueError("Exactly one matching Threads account must be connected in Publora")
    channel = matches[0]
    if channel.get("connectionStatus") != "active" or channel.get("tokenStatus") == "expired":
        raise ValueError("The matching Publora account needs reconnection")
    profile_url = channel.get("profileUrl")
    if profile_url:
        parsed = urlparse(profile_url)
        if (parsed.scheme != "https" or parsed.hostname not in
                {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}
                or parsed.path.rstrip("/").casefold() != "/@" + username):
            raise ValueError("Publora profile URL does not match the intended Threads account")
    # Return only fields needed for identity and connection status, never raw errors.
    return {"username": username, "platform_id": channel["platformId"],
            "profile_url": profile_url, "connection_status": "active",
            "token_status": channel.get("tokenStatus"),
            "expires_at": channel.get("accessTokenExpiresAt"),
            "verification": "Publora account listing; Meta posting permissions and publication untested"}


def save_connection(key, username, settings_path=ENV_PATH, metadata_path=METADATA_PATH,
                    platform_id="", reader=list_connections):
    key = validate_secret(key)
    settings = read_settings(settings_path)
    old_platform_id = settings.get("THREADS_PLATFORM_ID", "")
    if old_platform_id and platform_id and old_platform_id != platform_id:
        raise ValueError("Existing Publora platform ID differs; review the connection before replacing it")
    channel = verify_connection(key, username, platform_id or old_platform_id, reader)
    settings.update(PUBLISH_PROVIDER="publora", PUBLORA_API_KEY=key,
                    THREADS_PLATFORM_ID=channel["platform_id"],
                    THREADS_USERNAME=channel["username"], ENABLE_LIVE_THREADS="0")
    metadata = {"provider": "publora", "status": "CHANNEL_LISTED_PUBLISH_NOT_TESTED",
                "channel": channel, "verified_at": datetime.now(timezone.utc).isoformat(),
                "publishing_permissions_verified": False, "published_posts": 0}
    content = "# Private GTMBE connection settings; never commit or share.\n"
    content += "\n".join(k + "=" + v for k, v in settings.items()) + "\n"
    write_private(settings_path, content)
    write_private(metadata_path, json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    return metadata


def main():
    os.umask(0o077)
    if os.uname().sysname == "Darwin" and not os.getenv("SSL_CERT_FILE"):
        os.environ["SSL_CERT_FILE"] = "/etc/ssl/cert.pem"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=ENV_PATH)
    parser.add_argument("--metadata", type=Path, default=METADATA_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("connect", help="After owner authorization, read the API key privately and verify the exact Threads channel")
    setup.add_argument("--username", default="gtmberu")
    setup.add_argument("--platform-id", default="")
    setup.add_argument("--key-file", type=Path, help="Private mode-600 file; otherwise use a masked prompt")
    sub.add_parser("check", help="Read-only check of the configured exact channel")
    sub.add_parser("status", help="Safe local configuration summary; never prints the key")
    args = parser.parse_args()
    settings = read_settings(args.settings)
    if args.command == "status":
        result = {"provider": settings.get("PUBLISH_PROVIDER"),
                  "api_key_configured": bool(settings.get("PUBLORA_API_KEY")),
                  "username": settings.get("THREADS_USERNAME"),
                  "platform_id": settings.get("THREADS_PLATFORM_ID"),
                  "live_enabled": settings.get("ENABLE_LIVE_THREADS") == "1",
                  "connection": json.loads(args.metadata.read_text()) if args.metadata.exists() else None}
    elif args.command == "connect":
        key = secret_input(args.key_file, "Publora API key (hidden): ")
        result = save_connection(key, args.username, args.settings, args.metadata, args.platform_id)
    else:
        key = os.getenv("PUBLORA_API_KEY") or settings.get("PUBLORA_API_KEY", "")
        platform_id = settings.get("THREADS_PLATFORM_ID", "")
        if not key or not platform_id:
            raise ValueError("Connect the intended Publora Threads channel first")
        result = verify_connection(key, settings.get("THREADS_USERNAME", ""), platform_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Remote response bodies and exception messages may contain credentials.
        print(json.dumps({"status": "PUBLORA_CONNECTION_NOT_CONFIRMED", "error_type": type(exc).__name__,
                          "detail": "No posts were sent; check the account connection and private key"}))
        raise SystemExit(1)
