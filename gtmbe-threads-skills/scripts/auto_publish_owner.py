#!/usr/bin/env python3
"""GTMBE Telegram -> Threads: owner-only publisher with an opt-in live switch.

Runs with standard-library Python. Never auto-publishes text from third-party
channels. Persists an ATTEMPT_STARTED marker to GitHub *before* the API request.
All states survive the GitHub Actions runner. No token is printed or saved.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, urlopen

from engine import fetch_public, parse_telegram, exclusion_reason
from publish_threads import publish, BASE, write_atomic

ROOT = Path(__file__).resolve().parents[1]
STATE_DEFAULT = ROOT / "state" / "owner_publications.json"
SOURCE = "https://t.me/s/gtmbe"
SOURCE_NAME = "owner Telegram (operator supplied)"
TRUSTED_CHANNEL = "gtmbe"


def now_utc():
    return datetime.now(timezone.utc)


def text_digest(text: str) -> str:
    return sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def select_eligible(html: str, today=None, max_age_days=21) -> list[dict]:
    """Auto-publish only intact, fresh and standalone owner-written text <=500 chars.

    Longer posts, sensitive/quantitative claims, short throwaway messages,
    links/promos and forwards are kept for manual adaptation.
    """
    today = today or now_utc()
    found = parse_telegram(html, SOURCE_NAME, max_items=50)
    eligible = []
    for item in found:
        if not re.fullmatch(r"https://t\.me/gtmbe/\d+", item["url"]):
            continue
        reason = exclusion_reason(item)
        if reason:
            continue
        text = " ".join((item.get("body_text") or "").split()).strip()
        if not 120 <= len(text) <= 500:
            continue
        # Auto-mode cannot validate external links, images or specific numerical claims.
        if re.search(r"https?://|www\.|@[A-Za-z0-9_]{3,}|\b\d+(?:[.,]\d+)?\s*(?:%|к|млн|тыс|\$|руб|₽)", text, re.I):
            continue
        if re.search(r"(?i)\b(?:сегодня|завтра|вчера|позавчера|на следующей неделе|подписывайтесь|инвайт|промокод)\b", text):
            continue
        date_str = item.get("published_at")
        if not date_str:
            continue
        try:
            published_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if published_at < today - timedelta(days=max_age_days) or published_at > today + timedelta(minutes=10):
            continue
        # Source-origin status is set only after the channel has been explicitly whitelisted.
        eligible.append({
            "source_url": item["url"],
            "source_post_id": item["url"].rsplit("/", 1)[-1],
            "published_at": date_str,
            "text": text,
            "text_sha256": text_digest(text),
            "origin": "OWNER_VERBATIM",
            "char_count": len(text),
        })
    return sorted(eligible, key=lambda x: (x["published_at"], int(x["source_post_id"])), reverse=True)


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "entries": {}}
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or not isinstance(obj.get("entries"), dict):
        raise ValueError("Invalid published ledger: stop rather than risk duplicates.")
    return obj


def save_state(path: Path, state: dict, committer=None):
    """Write state locally and push to GitHub before publishing if runner is live."""
    write_atomic(path, state)
    if committer:
        committer(path)


def github_commit_state(path: Path):
    # Required in a live GitHub runner: write-ahead dedupe must be durable.
    subprocess.run(["git", "config", "user.name", "gtmbe-threads-bot"], check=True)
    subprocess.run(["git", "config", "user.email", "89929516+nizhge@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", str(path.relative_to(Path.cwd()))], check=True)
    subprocess.run(["git", "commit", "-m", "chore(threads): persist posting receipt [skip ci]"], check=True,
                   stdout=subprocess.DEVNULL)
    subprocess.run(["git", "push", "origin", "HEAD:main"], check=True,
                   stdout=subprocess.DEVNULL)


def get_json(endpoint: str, token: str, timeout=25) -> dict:
    req = Request(endpoint, headers={"Authorization": f"Bearer {token}"}, method="GET")
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read(160_000))


def verify_identity(token: str, expected_user_id: str, expected_username: str, getter=get_json) -> dict:
    if not expected_user_id.isdigit() or not expected_username.strip():
        raise ValueError("THREADS_USER_ID and THREADS_USERNAME are required.")
    data = getter(f"{BASE}/me?fields=id,username", token)
    if str(data.get("id")) != str(expected_user_id):
        raise ValueError("Threads token belongs to a different user ID. Refusing to publish.")
    if str(data.get("username", "")).casefold().lstrip("@") != expected_username.casefold().lstrip("@"):
        raise ValueError("Threads username does not match the approved account. Refusing to publish.")
    return {"id": str(data["id"]), "username": str(data["username"])}


def already_on_threads(text: str, token: str, getter=get_json) -> dict | None:
    """Check recent live text so old manual posts are not blindly reposted."""
    payload = getter(f"{BASE}/me/threads?fields=id,text,permalink&limit=50", token)
    if not isinstance(payload.get("data"), list):
        raise ValueError("Cannot check published feed. Refusing to publish.")
    wanted = text_digest(text)
    for item in payload["data"]:
        if item.get("text") and text_digest(str(item["text"])) == wanted:
            return {"id": item.get("id"), "permalink": item.get("permalink")}
    return None


def do_run(html: str, state_path: Path, live: bool, *, token="", user_id="",
           username="", max_age_days=21, getter=get_json, sender=publish,
           committer=None, today=None) -> dict:
    candidates = select_eligible(html, today=today, max_age_days=max_age_days)
    state = load_state(state_path)
    remaining = [p for p in candidates if p["source_url"] not in state["entries"]]
    result = {"mode": "LIVE" if live else "PREVIEW", "fetched": len(parse_telegram(html, SOURCE_NAME, max_items=50)),
              "eligible_owner_posts": len(candidates), "new_eligible": len(remaining),
              "posted": 0, "status": "NO_ELIGIBLE_POST", "selected": None}
    if not remaining:
        return result
    chosen = remaining[0]
    result["selected"] = {k: v for k, v in chosen.items() if k != "text"}
    if not live:
        result["status"] = "PREVIEW_ONLY"
        result["sample_text"] = chosen["text"]
        return result
    if os.getenv("GTMBE_AUTO_PUBLISH") != "true":
        raise ValueError("Live publishing requires explicit GTMBE_AUTO_PUBLISH=true opt-in.")
    if not committer:
        raise ValueError("Live mode requires durable GitHub state writer.")
    if not token:
        raise ValueError("Missing THREADS_ACCESS_TOKEN. Do not attempt to post.")
    verified = verify_identity(token, user_id, username, getter=getter)
    existing = already_on_threads(chosen["text"], token, getter=getter)
    key = chosen["source_url"]
    timestamp = now_utc().isoformat()
    if existing and existing.get("id") and existing.get("permalink"):
        state["entries"][key] = {"status": "ALREADY_ON_THREADS", "post_id": existing["id"],
                                 "permalink": existing["permalink"], "text_sha256": chosen["text_sha256"],
                                 "at": timestamp}
        save_state(state_path, state, committer)
        result["status"] = "ALREADY_ON_THREADS"
        return result
    # Durable write-ahead log. On timeout / failed push / unknown API status,
    # all future runs skip this source until manually reconciled.
    state["entries"][key] = {"status": "ATTEMPT_STARTED", "text_sha256": chosen["text_sha256"],
                             "account": verified["username"], "at": timestamp}
    save_state(state_path, state, committer)
    draft = {"id": "owner_" + chosen["source_post_id"], "text": chosen["text"]}
    try:
        receipt = sender(draft, ROOT / "local-state" / "api_receipts.json", user_id, token)
        state["entries"][key] = {"status": receipt.get("status", "UNKNOWN"),
                                 "text_sha256": chosen["text_sha256"], "post_id": receipt.get("post_id"),
                                 "permalink": receipt.get("permalink"), "at": timestamp}
        save_state(state_path, state, committer)
        result["status"] = receipt.get("status", "UNKNOWN")
        result["permalink"] = receipt.get("permalink")
        result["posted"] = int(result["status"] == "PUBLISHED_VERIFIED")
        return result
    except Exception:
        # ATTEMPT_STARTED was already durably saved. Never clear it automatically.
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Requires opt-in and Threads OAuth secrets")
    parser.add_argument("--state", type=Path, default=STATE_DEFAULT)
    parser.add_argument("--max-age-days", type=int, default=21)
    parser.add_argument("--fixture", type=Path, help="Local HTML fixture (preview/tests only)")
    args = parser.parse_args()
    if args.publish and args.fixture:
        raise SystemExit("Live publisher rejects test fixtures.")
    if args.publish and os.getenv("GITHUB_ACTIONS") != "true":
        raise SystemExit("Live publisher only runs from the configured GitHub Actions environment.")
    if args.publish and not os.getenv("GTMBE_AUTO_PUBLISH") == "true":
        raise SystemExit("Live publisher disabled: GTMBE_AUTO_PUBLISH is not true.")
    html = args.fixture.read_text(encoding="utf-8") if args.fixture else fetch_public(SOURCE)
    result = do_run(
        html, args.state, args.publish,
        token=os.getenv("THREADS_ACCESS_TOKEN", ""),
        user_id=os.getenv("THREADS_USER_ID", ""),
        username=os.getenv("THREADS_USERNAME", ""),
        max_age_days=args.max_age_days,
        committer=github_commit_state if args.publish else None,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
