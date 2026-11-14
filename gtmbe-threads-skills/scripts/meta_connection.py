#!/usr/bin/env python3
"""Connect or refresh a Meta Threads user token without printing credentials.

Uses the official Threads token endpoints and checks /me before saving. The
connect command leaves live publishing disabled. No command publishes a post.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from getpass import getpass
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from auto_publish_owner import verify_identity

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "private" / "connection.env"
META_PATH = ROOT / "private" / "meta_connection.json"
TOKEN_BASE = "https://graph.threads.com"


def read_settings(path):
    data = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
                raise ValueError("Private settings must contain KEY=value entries")
            data[key.strip()] = value.strip().strip("\"'")
    return data


def write_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".meta-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def validate_secret(value):
    value = value.strip()
    if not 8 <= len(value) <= 8192 or any(c.isspace() for c in value):
        raise ValueError("Credential is empty, too long, or contains whitespace")
    return value


def secret_input(path, prompt):
    if path is None:
        return validate_secret(getpass(prompt))
    if path.stat().st_mode & 0o077:
        raise ValueError("Secret input file must be private (chmod 600)")
    return validate_secret(path.read_text(encoding="utf-8"))


def token_request(operation, token, app_secret=""):
    if operation == "exchange":
        endpoint = "/access_token"
        form = {"grant_type": "th_exchange_token", "client_secret": app_secret}
    elif operation == "refresh":
        endpoint = "/refresh_access_token"
        form = {"grant_type": "th_refresh_token"}
    else:
        raise ValueError("Unknown token operation")
    # Meta's OAuth endpoints specify query parameters. Never log this URL.
    form["access_token"] = token
    request = Request(TOKEN_BASE + endpoint + "?" + urlencode(form), method="GET")
    with urlopen(request, timeout=25) as response:
        result = json.loads(response.read(150_000))
    validate_secret(str(result.get("access_token", "")))
    if not isinstance(result.get("expires_in"), int) or result["expires_in"] <= 0:
        raise ValueError("Meta token response did not include a valid lifetime")
    return result


def save_connection(token, expected_username, env_path=ENV_PATH, metadata_path=META_PATH,
                    exchange=False, app_secret="", verifier=verify_identity,
                    requester=token_request, refresh=False, now=None):
    now = now or datetime.now(timezone.utc)
    token = validate_secret(token)
    settings = read_settings(env_path)
    # Never replace a working credential with a token for an unintended account.
    identity = verifier(token, settings.get("THREADS_USER_ID", ""), expected_username)
    lifetime = None
    if exchange or refresh:
        if exchange:
            validate_secret(app_secret)
        response = requester("refresh" if refresh else "exchange", token, app_secret)
        replacement = validate_secret(str(response.get("access_token", "")))
        lifetime = response.get("expires_in")
        if not isinstance(lifetime, int) or lifetime <= 0:
            raise ValueError("Meta token response did not include a valid lifetime")
        identity = verifier(replacement, identity["id"], expected_username)
        token = replacement
    settings.update(THREADS_USERNAME=identity["username"], THREADS_USER_ID=identity["id"],
                    THREADS_ACCESS_TOKEN=token)
    if not refresh:
        settings["ENABLE_LIVE_THREADS"] = "0"
    metadata = {"status": "IDENTITY_VERIFIED_PUBLISH_NOT_TESTED", "account": identity,
                "token_updated_at": now.isoformat(),
                "token_kind": "long_lived" if lifetime else "unknown",
                "expires_at": (now + timedelta(seconds=lifetime)).isoformat() if lifetime else None,
                "publishing_permissions_verified": False,
                "verification": "Meta /me identity only; no post or permission grant was attempted"}
    content = "# Private GTMBE connection settings; never commit or share.\n"
    content += "\n".join(k + "=" + v for k, v in settings.items()) + "\n"
    write_private(env_path, content)
    write_private(metadata_path, json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    return metadata


def main():
    os.umask(0o077)
    if os.uname().sysname == "Darwin" and not os.getenv("SSL_CERT_FILE"):
        os.environ["SSL_CERT_FILE"] = "/etc/ssl/cert.pem"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=ENV_PATH)
    parser.add_argument("--metadata", type=Path, default=META_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    connect = sub.add_parser("connect", help="Read a Threads user token privately and verify the account")
    connect.add_argument("--username", default="gtmberu")
    connect.add_argument("--token-file", type=Path, help="Private file; without this, use a masked terminal prompt")
    connect.add_argument("--exchange", action="store_true", help="Exchange a short-lived token using the Threads app secret")
    connect.add_argument("--app-secret-file", type=Path)
    sub.add_parser("refresh", help="Refresh an eligible, unexpired long-lived token; never retries automatically")
    sub.add_parser("status", help="Show safe connection metadata, never the token")
    args = parser.parse_args()
    settings = read_settings(args.settings)
    if args.command == "status":
        print(json.dumps({"username": settings.get("THREADS_USERNAME"),
                          "token_configured": bool(settings.get("THREADS_ACCESS_TOKEN")),
                          "live_enabled": settings.get("ENABLE_LIVE_THREADS") == "1",
                          "connection": json.loads(args.metadata.read_text()) if args.metadata.exists() else None}, indent=2))
        return
    if args.command == "connect":
        token = secret_input(args.token_file, "Threads user access token (hidden): ")
        app_secret = secret_input(args.app_secret_file, "Threads app secret (hidden): ") if args.exchange else ""
        result = save_connection(token, args.username, args.settings, args.metadata,
                                 exchange=args.exchange, app_secret=app_secret)
    else:
        token = settings.get("THREADS_ACCESS_TOKEN", "")
        username = settings.get("THREADS_USERNAME", "")
        if not token or not username:
            raise ValueError("Connect the authorized Threads account first")
        if args.metadata.exists():
            metadata = json.loads(args.metadata.read_text())
            updated = datetime.fromisoformat(metadata["token_updated_at"])
            if datetime.now(timezone.utc) - updated < timedelta(hours=24):
                raise ValueError("The current token is less than 24 hours old; do not refresh yet")
        result = save_connection(token, username, args.settings, args.metadata, refresh=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # HTTP exceptions can contain tokens in URLs. Never print exception text.
        print(json.dumps({"status": "CONNECTION_NOT_CONFIRMED", "error_type": type(exc).__name__,
                          "detail": str(exc) if isinstance(exc, ValueError) else "Meta connection failed; no credential details were logged"}))
        raise SystemExit(1)
