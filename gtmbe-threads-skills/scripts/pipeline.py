#!/usr/bin/env python3
"""Persistent Telegram -> owner voice -> editorial review -> Threads pipeline.

All private corpus, drafts, approvals and receipts stay under private/. Stdlib only.
Run `python scripts/pipeline.py --help`. Only the `publish` command writes to Threads.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3

from engine import (candidates_from_sources, exclusion_reason, generate_draft,
                    is_owned_telegram, load_sources, threads_length, validate_draft)
from auto_publish_owner import verify_identity, already_on_threads
from publish_threads import publish, _read_post

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "private" / "pipeline.sqlite3"


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def digest(text):
    return sha256(text.encode("utf-8")).hexdigest()


def normalized(text):
    return " ".join(text.casefold().split())


def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    os.chmod(path, 0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            url TEXT PRIMARY KEY, payload TEXT NOT NULL, seen_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY, source_url TEXT NOT NULL UNIQUE,
            text TEXT NOT NULL, text_sha256 TEXT NOT NULL,
            payload TEXT NOT NULL, status TEXT NOT NULL,
            account TEXT, approved_sha256 TEXT, approved_at TEXT,
            receipt TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY, draft_id TEXT, kind TEXT NOT NULL,
            payload TEXT NOT NULL, at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS history (
            source_url TEXT PRIMARY KEY, reason TEXT NOT NULL);
    """)
    db.commit()
    if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise ValueError("Database integrity check failed")
    return db


@contextmanager
def exclusive(path):
    """Serialize collection, approval and publication across local processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def event(db, draft_id, kind, payload):
    db.execute("INSERT INTO events(draft_id,kind,payload,at) VALUES(?,?,?,?)",
               (draft_id, kind, json.dumps(payload, ensure_ascii=False), utcnow()))


def store_sources(db, items):
    with db:
        for item in items:
            db.execute("INSERT INTO sources VALUES(?,?,?) ON CONFLICT(url) DO UPDATE SET payload=excluded.payload, seen_at=excluded.seen_at",
                       (item["url"], json.dumps(item, ensure_ascii=False), utcnow()))


def load_voice(path):
    profile = json.loads(path.read_text(encoding="utf-8"))
    urls = profile.get("sample_urls", [])
    if profile.get("status") != "CORPUS_REVIEWED" or len(set(urls)) < 8:
        raise ValueError("Voice needs at least 8 reviewed owner samples; generic fallback is disabled")
    if any(not re.fullmatch(r"https://t\.me/gtmbe/\d+", u) for u in urls):
        raise ValueError("Voice samples must all come from the verified owner channel")
    return json.dumps(profile, ensure_ascii=False)


def add_draft(db, item, draft):
    text = draft.get("text", "").strip()
    reason = validate_draft(text, item)
    if reason:
        raise ValueError(reason)
    if not is_owned_telegram(item):
        channel = item["url"].split("/")[-2]
        if channel.casefold() not in text.casefold():
            raise ValueError("External-source commentary must credit the channel by name")
        # Catch verbatim passages hidden inside otherwise different commentary.
        words = normalized(item.get("body_text") or item["summary"]).split()
        if any(" ".join(words[i:i+12]) in normalized(text) for i in range(max(0, len(words)-11))):
            raise ValueError("External draft copies a 12-word source passage")
    if db.execute("SELECT 1 FROM history WHERE source_url=?", (item["url"],)).fetchone():
        raise ValueError("Source already in the canonical editorial history")
    for row in db.execute("SELECT text FROM drafts"):
        if SequenceMatcher(None, normalized(text), normalized(row[0])).ratio() > .88:
            raise ValueError("Draft duplicates an existing queue text")
    draft_id = "draft_" + item["id"]
    payload = dict(draft, id=draft_id, source_url=item["url"], source_id=item["id"],
                   text=text, text_sha256=digest(text), status="REVIEW_REQUIRED",
                   ownership="OWNER" if is_owned_telegram(item) else "THIRD_PARTY",
                   source_date=item.get("published_at"), char_count=len(text),
                   platform_count=threads_length(text), published=False)
    with db:
        db.execute("INSERT INTO drafts(id,source_url,text,text_sha256,payload,status,created_at) VALUES(?,?,?,?,?,?,?)",
                   (draft_id, item["url"], text, digest(text), json.dumps(payload, ensure_ascii=False),
                    "REVIEW_REQUIRED", utcnow()))
        event(db, draft_id, "DRAFT_CREATED", {"sha256": digest(text), "source_url": item["url"]})
    return payload


def approve(db, draft_id, expected_sha, account, note, score):
    account = account.lstrip("@").casefold()
    if not re.fullmatch(r"[a-z0-9_.]{1,30}", account) or not note.strip() or not 80 <= score <= 100:
        raise ValueError("Approval needs exact account, evidence/review note, and quality score 80–100")
    row = db.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if not row or row["status"] != "REVIEW_REQUIRED":
        raise ValueError("Draft is missing or already approved/attempted")
    if expected_sha != row["text_sha256"] or digest(row["text"]) != expected_sha:
        raise ValueError("Approval hash does not match the exact final text")
    with db:
        db.execute("UPDATE drafts SET status='APPROVED',account=?,approved_sha256=?,approved_at=? WHERE id=?",
                   (account, expected_sha, utcnow(), draft_id))
        event(db, draft_id, "APPROVED", {"account": account, "sha256": expected_sha,
                                         "review_note": note, "quality_score": score})


def verify_receipt(post, row, account):
    from urllib.parse import urlparse
    p = urlparse(str(post.get("permalink", "")))
    if p.scheme != "https" or p.hostname not in {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}:
        raise ValueError("Readback lacks a verified Threads permalink")
    if not p.path.casefold().startswith("/@" + account.casefold() + "/post/"):
        raise ValueError("Readback permalink belongs to a different account")
    if post.get("text") != row["text"] or not str(post.get("id", "")).isdigit():
        raise ValueError("Readback text or media ID mismatch")


def send(db, draft_id, account, token, user_id="", sender=publish,
         verifier=verify_identity, finder=already_on_threads, receipts_path=None):
    row = db.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    account = account.lstrip("@").casefold()
    if not row or row["status"] != "APPROVED" or row["account"] != account:
        raise ValueError("No approval for this exact draft/account, or a prior attempt exists")
    if digest(row["text"]) != row["approved_sha256"] or row["text_sha256"] != row["approved_sha256"]:
        raise ValueError("Approved text changed")
    identity = verifier(token, user_id, account)
    # Also honor durable attempts made by the older owner-only publisher.
    legacy = ROOT / "state" / "owner_publications.json"
    if legacy.exists() and row["source_url"] in json.loads(legacy.read_text())["entries"]:
        raise ValueError("Source already attempted by the owner-only publisher")
    existing = finder(row["text"], token)
    if existing:
        # This is reconciliation of an existing post, never a new send.
        receipt = {"status": "ALREADY_ON_THREADS", "post_id": existing["id"],
                   "permalink": existing.get("permalink")}
        with db:
            db.execute("UPDATE drafts SET status=?,receipt=? WHERE id=?",
                       (receipt["status"], json.dumps(receipt), draft_id))
            event(db, draft_id, receipt["status"], receipt)
        return receipt
    # FULL synchronous SQLite commit precedes any remote write. Never auto-clear.
    with db:
        db.execute("UPDATE drafts SET status='ATTEMPT_STARTED' WHERE id=?", (draft_id,))
        event(db, draft_id, "ATTEMPT_STARTED", {"account": account, "sha256": row["text_sha256"]})
    try:
        receipt = sender({"id": draft_id, "text": row["text"]}, receipts_path,
                         identity["id"], token)
        if receipt.get("status") == "PUBLISHED_VERIFIED":
            verify_receipt({"id": receipt.get("post_id"), "permalink": receipt.get("permalink"),
                            "text": row["text"]}, row, account)
    except Exception as exc:
        with db:
            db.execute("UPDATE drafts SET status='UNKNOWN_REQUIRES_RECONCILIATION' WHERE id=?", (draft_id,))
            event(db, draft_id, "UNKNOWN_REQUIRES_RECONCILIATION", {"error_type": type(exc).__name__})
        raise
    with db:
        db.execute("UPDATE drafts SET status=?,receipt=? WHERE id=?",
                   (receipt["status"], json.dumps(receipt), draft_id))
        event(db, draft_id, receipt["status"], receipt)
    return receipt


def reconcile(db, draft_id, token, reader=_read_post, finder=already_on_threads):
    row = db.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if not row or row["status"] in {"REVIEW_REQUIRED", "APPROVED", "PUBLISHED_VERIFIED"}:
        raise ValueError("Only an unresolved publication attempt can be reconciled")
    saved = json.loads(row["receipt"] or "{}")
    post_id = saved.get("post_id")
    if not post_id:
        existing = finder(row["text"], token)
        post_id = existing.get("id") if existing else None
    if not post_id:
        return {"status": row["status"], "detail": "No matching post found; no retry performed"}
    post = reader(str(post_id), token)
    verify_receipt(post, row, row["account"])
    receipt = {"status": "PUBLISHED_VERIFIED", "post_id": post["id"], "permalink": post["permalink"]}
    with db:
        db.execute("UPDATE drafts SET status=?,receipt=? WHERE id=?",
                   (receipt["status"], json.dumps(receipt), draft_id))
        event(db, draft_id, "RECONCILED", receipt)
    return receipt


def load_env(path):
    """Read KEY=value without executing shell code; existing env wins."""
    if path is None:
        return
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
            raise ValueError("Env file must contain KEY=value entries")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--env-file", type=Path)
    sub = p.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--sources", type=Path, default=ROOT / "config/research_sources.json")
    generate = sub.add_parser("generate")
    generate.add_argument("--voice", type=Path, default=ROOT / "private/voice_profile.json")
    generate.add_argument("--limit", type=int, default=3)
    imp = sub.add_parser("import-drafts")
    imp.add_argument("--file", type=Path, required=True)
    history = sub.add_parser("import-history")
    history.add_argument("--file", type=Path, required=True, help="JSON array of previously used source URLs")
    app = sub.add_parser("approve")
    app.add_argument("--id", required=True)
    app.add_argument("--sha256", required=True)
    app.add_argument("--account", required=True)
    app.add_argument("--note", required=True, help="Evidence/originality/voice review, after owner agreement")
    app.add_argument("--score", type=int, required=True)
    for command in ("publish", "reconcile"):
        cmd = sub.add_parser(command)
        cmd.add_argument("--id", required=True)
    sub.add_parser("check-account")
    sub.add_parser("status")
    export = sub.add_parser("export")
    export.add_argument("--out", type=Path, default=ROOT / "private/review.json")
    args = p.parse_args()
    load_env(args.env_file)
    # Trust the machine's normal CA bundle on macOS. Certificate verification stays on.
    if os.uname().sysname == "Darwin" and not os.getenv("SSL_CERT_FILE"):
        os.environ["SSL_CERT_FILE"] = "/etc/ssl/cert.pem"
    token = os.getenv("THREADS_ACCESS_TOKEN", "")
    username = os.getenv("THREADS_USERNAME", "")
    uid = os.getenv("THREADS_USER_ID", "")
    with exclusive(args.db):
        db = connect(args.db)
        result = {}
        if args.command == "collect":
            os.environ.setdefault("GTMBE_OWNER_TELEGRAM_URL", "https://t.me/s/gtmbe")
            os.environ.setdefault("GTMBE_OWNER_TELEGRAM_CONFIRMED", "1")
            sources = load_sources(args.sources)
            items, errors = candidates_from_sources(sources)
            store_sources(db, items)
            result = {"sources_attempted": len(sources), "items": len(items), "source_errors": errors}
        elif args.command == "generate":
            voice = load_voice(args.voice)
            key = os.getenv("OPENAI_API_KEY", "").strip()
            if not key:
                raise ValueError("OPENAI_API_KEY missing. Import reviewed drafts or connect the model before automatic generation")
            created, errors = [], []
            rows = db.execute("SELECT payload FROM sources WHERE url NOT IN (SELECT source_url FROM drafts) AND url NOT IN (SELECT source_url FROM history)").fetchall()
            items = sorted((json.loads(r[0]) for r in rows), key=lambda x: x.get("relevance_score", 0), reverse=True)
            for item in items:
                if len(created) >= min(max(args.limit, 0), 10):
                    break
                if exclusion_reason(item) or item.get("relevance_score", 0) < 37:
                    continue
                try:
                    draft = generate_draft(item, key, os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), voice)
                    draft["voice_sha256"] = digest(voice)
                    created.append(add_draft(db, item, draft)["id"])
                except Exception as exc:
                    errors.append({"url": item["url"], "error_type": type(exc).__name__})
            result = {"created": created, "errors": errors, "published": 0}
        elif args.command == "import-drafts":
            created = []
            for draft in json.loads(args.file.read_text()):
                row = db.execute("SELECT payload FROM sources WHERE url=?", (draft["source_url"],)).fetchone()
                if not row:
                    raise ValueError("Collect the source before importing a draft")
                created.append(add_draft(db, json.loads(row[0]), draft)["id"])
            result = {"created": created, "published": 0}
        elif args.command == "import-history":
            urls = json.loads(args.file.read_text())
            if not isinstance(urls, list) or any(not isinstance(u, str) or not re.fullmatch(r"https://t\.me/[A-Za-z0-9_]+/\d+", u) for u in urls):
                raise ValueError("History must be an array of Telegram post permalinks")
            with db:
                db.executemany("INSERT OR IGNORE INTO history VALUES(?,?)", [(u, "canonical_notion_prior_draft") for u in urls])
            result = {"prior_sources": len(urls), "published": 0}
        elif args.command == "approve":
            approve(db, args.id, args.sha256, args.account, args.note, args.score)
            result = {"id": args.id, "status": "APPROVED", "published": 0}
        elif args.command == "check-account":
            if not token:
                raise ValueError("THREADS_ACCESS_TOKEN missing")
            result = verify_identity(token, uid, username)
        elif args.command == "publish":
            if os.getenv("ENABLE_LIVE_THREADS") != "1" or not token or not username:
                raise ValueError("Live publishing requires ENABLE_LIVE_THREADS=1 and the authorized Threads token/username")
            result = send(db, args.id, username, token, uid, receipts_path=args.db.parent / "pipeline_receipts.json")
        elif args.command == "reconcile":
            verify_identity(token, uid, username)
            result = reconcile(db, args.id, token)
        elif args.command == "export":
            records = []
            for row in db.execute("SELECT * FROM drafts ORDER BY created_at"):
                record = json.loads(row["payload"])
                record.update(status=row["status"], account=row["account"], receipt=json.loads(row["receipt"] or "null"))
                records.append(record)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
            result = {"queue_file": str(args.out), "drafts": len(records)}
        else:
            result = {"database": str(args.db), "sources": db.execute("SELECT count(*) FROM sources").fetchone()[0],
                      "prior_sources": db.execute("SELECT count(*) FROM history").fetchone()[0],
                      "queue": dict(db.execute("SELECT status,count(*) FROM drafts GROUP BY status")),
                      "voice_profile_present": (ROOT / "private/voice_profile.json").exists(),
                      "model_key_configured": bool(os.getenv("OPENAI_API_KEY")),
                      "threads_token_configured": bool(token), "threads_username_configured": bool(username),
                      "live_enabled": os.getenv("ENABLE_LIVE_THREADS") == "1"}
        db.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not print API errors/bodies/URLs which may contain credentials.
        print(json.dumps({"error": str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else type(exc).__name__}, ensure_ascii=False))
        raise SystemExit(1)
