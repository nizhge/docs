#!/usr/bin/env python3
"""Run Telegram collection, fresh-news drafting, review and authorized publishing.

Default: collect and prepare review only. --publish-approved uses existing exact
approvals plus live mode. Unknown sends are only reconciled, never resubmitted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from engine import candidates_from_sources, draft_prompt, generate_draft, load_sources
from meta_connection import write_private
from pipeline import (ROOT, DEFAULT_DB, add_draft, connect, digest, event, exclusive,
                      generation_candidates, load_env, load_voice, reconcile,
                      reconcile_publora, send, send_publora, source_gate, source_hash, store_sources,
                      verify_identity)

UNRESOLVED = {"ATTEMPT_STARTED", "BROWSER_ATTEMPT_STARTED", "UNKNOWN_REQUIRES_RECONCILIATION",
              "API_CONFIRMED_LINK_UNVERIFIED", "PUBLORA_ATTEMPT_STARTED", "PUBLORA_PENDING",
              "PUBLORA_PUBLISHED_REQUIRES_READBACK", "PUBLORA_EXISTING_REQUIRES_RECONCILIATION"}


def queue_records(db):
    records = []
    for row in db.execute("SELECT * FROM drafts ORDER BY created_at"):
        record = json.loads(row["payload"])
        record.update(status=row["status"], account=row["account"],
                      receipt=json.loads(row["receipt"] or "null"))
        records.append(record)
    return records


def export_review(db, work_dir, account, max_age_days=7, now=None):
    records = queue_records(db)
    write_private(work_dir / "review.json", json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    cards = []
    labels = {"REVIEW_REQUIRED": "На согласовании", "APPROVED": "Согласован",
              "PUBLISHED_VERIFIED": "Публикация проверена", "PUBLORA_PENDING": "Ожидает отправки",
              "PUBLORA_PUBLISHED_REQUIRES_READBACK": "Нужно проверить пост в Threads"}
    for record in reversed(records):
        text, url = escape(record["text"]), escape(record["source_url"], quote=True)
        source = db.execute("SELECT payload FROM sources WHERE url=?", (record["source_url"],)).fetchone()
        needs_refresh = source is None or source_gate(json.loads(source[0]), max_age_days, now) is not None
        freshness_note = '<p>Для новостной публикации источник нужно обновить или перепроверить.</p>' if needs_refresh and record["status"] in {"REVIEW_REQUIRED", "APPROVED"} else ''
        cards.append('<article><small>' + escape(labels.get(record["status"], "Требуется проверка результата")) +
                     ' · ' + escape(str(record.get("source_date") or "Дата не указана")) + '</small>' +
                     '<textarea readonly onclick="this.select()">' + text + '</textarea>' +
                     '<p>' + escape(str(record.get("verification_notes") or "Факты и стиль нужно проверить перед отправкой.")) +
                     '</p>' + freshness_note + '<a href="' + url + '" target="_blank" rel="noreferrer">Открыть источник</a></article>')
    page = ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            '<title>GTMBE · Публикации</title><style>body{font:17px/1.5 system-ui;background:#f6f3ed;color:#242722;'
            'max-width:900px;margin:40px auto;padding:0 20px}article{background:white;border:1px solid #ddd;'
            'border-radius:16px;padding:24px;margin:20px 0}small{color:#687067}textarea{display:block;width:100%;'
            'box-sizing:border-box;min-height:170px;border:0;resize:vertical;font:20px/1.5 system-ui;margin-top:15px;'
            'color:inherit;background:transparent}p{font-size:14px;color:#62675f}a{color:#356647}</style>'
            '<h1>Публикации GTMBE</h1><p>Адресат: @' + escape(account or "не указан") +
            '. Нажми на текст, чтобы выделить и скопировать его. Согласование и отправка учитываются отдельно.</p>' +
            ''.join(cards) + '</html>')
    write_private(work_dir / "review.html", page)
    return records


def publishing_problem(settings):
    provider = settings.get("PUBLISH_PROVIDER", "meta")
    if provider not in {"meta", "publora"}:
        return "UNKNOWN_PUBLISH_PROVIDER"
    if not re.fullmatch(r"[a-z0-9_.]{1,30}", settings.get("THREADS_USERNAME", "")):
        return "THREADS_ACCOUNT_NOT_CONFIGURED"
    if provider == "publora":
        if not settings.get("PUBLORA_API_KEY") or not re.fullmatch(r"threads-\d+", settings.get("THREADS_PLATFORM_ID", "")):
            return "PUBLORA_CHANNEL_NOT_CONNECTED"
    elif not settings.get("THREADS_ACCESS_TOKEN"):
        return "META_TOKEN_NOT_CONNECTED"
    return None


def submit_approved(db, draft_id, settings):
    if settings.get("PUBLISH_PROVIDER", "meta") == "publora":
        return send_publora(db, draft_id, settings["THREADS_USERNAME"],
                            settings["PUBLORA_API_KEY"], settings["THREADS_PLATFORM_ID"])
    return send(db, draft_id, settings["THREADS_USERNAME"], settings["THREADS_ACCESS_TOKEN"],
                settings.get("THREADS_USER_ID", ""))


def read_attempt(db, draft_id, settings):
    row = db.execute("SELECT receipt FROM drafts WHERE id=?", (draft_id,)).fetchone()
    receipt = json.loads(row["receipt"] or "{}")
    if receipt.get("provider") == "publora":
        return reconcile_publora(db, draft_id, settings["PUBLORA_API_KEY"],
                                 settings["THREADS_USERNAME"], settings["THREADS_PLATFORM_ID"])
    if receipt.get("provider") == "threads_browser":
        raise ValueError("Browser attempt requires visible Threads readback")
    if settings.get("PUBLISH_PROVIDER", "meta") != "meta":
        raise ValueError("Attempt requires its original provider")
    verify_identity(settings["THREADS_ACCESS_TOKEN"], settings.get("THREADS_USER_ID", ""), settings["THREADS_USERNAME"])
    return reconcile(db, draft_id, settings["THREADS_ACCESS_TOKEN"])


def _run_flow(db, sources_path, voice_path, work_dir, settings, *, report, limit=3, max_age_days=7,
             publish_approved=False, publish_limit=1, now=None, collector=candidates_from_sources,
             drafter=generate_draft, submitter=submit_approved, reconciler=read_attempt):
    if not 0 <= limit <= 10 or not 1 <= publish_limit <= 10 or not 0 < max_age_days <= 365:
        raise ValueError("Invalid drafting, publishing or news-age limit")
    now = now or datetime.now(timezone.utc)
    sources = load_sources(sources_path)
    items, errors = collector(sources, max_age_days=max_age_days, now=now)
    store_sources(db, items)
    report["collection"] = {"channels": len(sources), "items": len(items),
                            "errors": [{"source": e.get("source"), "error": "SOURCE_FETCH_FAILED"} for e in errors]}
    current_urls = {item["url"] for item in items}
    candidates, report["excluded"] = generation_candidates(db, max_age_days, now, current_urls)
    report["eligible_sources"] = len(candidates)
    requests = []
    if limit and not settings.get("OPENAI_API_KEY"):
        report["blockers"].append("AUTOMATIC_GENERATION_MODEL_NOT_CONNECTED")
    if limit and candidates:
        try:
            voice = load_voice(voice_path)
        except (ValueError, OSError, json.JSONDecodeError):
            report["blockers"].append("OWNER_VOICE_PROFILE_NEEDS_REVIEW")
        else:
            key = settings.get("OPENAI_API_KEY", "")
            if not key:
                requests = [{"source_url": item["url"], "source_sha256": source_hash(item),
                             "voice_sha256": digest(voice), "messages": draft_prompt(item, voice)}
                            for item in candidates[:limit]]
            else:
                for item in candidates[:max(3, limit * 3)]:
                    if len(report["created"]) >= limit:
                        break
                    try:
                        draft = drafter(item, key, settings.get("OPENAI_MODEL", "gpt-4.1-mini"), voice)
                        draft["voice_sha256"] = digest(voice)
                        report["created"].append(add_draft(db, item, draft)["id"])
                    except Exception as exc:
                        report["errors"].append({"stage": "draft", "source_url": item["url"], "error_type": type(exc).__name__})
    write_private(work_dir / "generation_requests.json", json.dumps(requests, ensure_ascii=False, indent=2) + "\n")
    problem = publishing_problem(settings)
    if problem:
        report["blockers"].append(problem)
    # Reconcile already journaled attempts with GETs even when live mode is off.
    unresolved = list(db.execute("SELECT id,status,account FROM drafts WHERE account=? ORDER BY created_at",
                                 (settings.get("THREADS_USERNAME", ""),)))
    if not problem:
        for row in unresolved:
            if row["status"] not in UNRESOLVED:
                continue
            try:
                receipt = reconciler(db, row["id"], settings)
                report["reconciled"].append({"id": row["id"], "status": receipt["status"]})
            except Exception as exc:
                report["errors"].append({"stage": "reconcile", "id": row["id"], "error_type": type(exc).__name__})
    unresolved = [r[0] for r in db.execute("SELECT status FROM drafts WHERE account=?", (settings.get("THREADS_USERNAME", ""),)) if r[0] in UNRESOLVED]
    if unresolved:
        report["blockers"].append("PRIOR_ATTEMPT_REQUIRES_READBACK")
    if publish_approved and settings.get("ENABLE_LIVE_THREADS") != "1":
        report["blockers"].append("LIVE_PUBLISHING_NOT_ENABLED")
    if publish_approved and not problem and not unresolved and settings.get("ENABLE_LIVE_THREADS") == "1":
        approved = list(db.execute("SELECT * FROM drafts WHERE status='APPROVED' AND account=? ORDER BY created_at",
                                   (settings["THREADS_USERNAME"],)))
        for row in approved:
            if len(report["submitted"]) >= publish_limit:
                break
            source = db.execute("SELECT payload FROM sources WHERE url=?", (row["source_url"],)).fetchone()
            item = json.loads(source[0]) if source else {}
            reason = source_gate(item, max_age_days, now) if source else "source_missing"
            if row["source_url"] not in current_urls:
                reason = reason or "source_not_fetched_this_run"
            if json.loads(row["payload"]).get("source_sha256") != source_hash(item):
                reason = reason or "source_changed_requires_review"
            if reason:
                report["errors"].append({"stage": "publish_preflight", "id": row["id"], "reason": reason})
                continue
            try:
                receipt = submitter(db, row["id"], settings)
                report["submitted"].append({"id": row["id"], "status": receipt["status"]})
                if receipt["status"] in UNRESOLVED:
                    receipt = reconciler(db, row["id"], settings)
                    report["reconciled"].append({"id": row["id"], "status": receipt["status"]})
                if receipt["status"] in UNRESOLVED:
                    report["blockers"].append("PRIOR_ATTEMPT_REQUIRES_READBACK")
                    break
            except Exception as exc:
                report["errors"].append({"stage": "publish", "id": row["id"], "error_type": type(exc).__name__})
                break
    records = export_review(db, work_dir, settings.get("THREADS_USERNAME", ""), max_age_days, now)
    report["queue"] = {row[0]: row[1] for row in db.execute("SELECT status,count(*) FROM drafts GROUP BY status")}
    report["verified_publications_total"] = sum(r["status"] == "PUBLISHED_VERIFIED" for r in records)
    report["blockers"] = list(dict.fromkeys(report["blockers"]))
    report["status"] = "ACTION_REQUIRED" if report["blockers"] or report["errors"] else "REVIEW_READY"
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    with db:
        event(db, None, "FLOW_FINISHED", report)
    write_private(work_dir / "flow_report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def run_flow(db, sources_path, voice_path, work_dir, settings, **options):
    """Caller holds the queue lock. Every run records start and terminal evidence."""
    options["now"] = options.get("now") or datetime.now(timezone.utc)
    report = {"run_id": str(uuid4()), "status": "RUNNING", "started_at": options["now"].isoformat(),
              "account": settings.get("THREADS_USERNAME"), "provider": settings.get("PUBLISH_PROVIDER", "meta"),
              "max_age_days": options.get("max_age_days", 7), "created": [], "submitted": [],
              "reconciled": [], "blockers": [], "errors": [],
              "automatic_model_configured": bool(settings.get("OPENAI_API_KEY"))}
    with db:
        event(db, None, "FLOW_STARTED", {"run_id": report["run_id"],
                                         "publish_requested": options.get("publish_approved", False)})
    write_private(work_dir / "flow_report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    try:
        return _run_flow(db, sources_path, voice_path, work_dir, settings, report=report, **options)
    except Exception as exc:
        report.update(status="INTERRUPTED", finished_at=datetime.now(timezone.utc).isoformat())
        report["errors"].append({"stage": "run", "error_type": type(exc).__name__})
        with db:
            event(db, None, "FLOW_INTERRUPTED", report)
        write_private(work_dir / "flow_report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        raise


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--env-file", type=Path, default=ROOT / "private/connection.env")
    parser.add_argument("--sources", type=Path, default=ROOT / "config/research_sources.json")
    parser.add_argument("--voice", type=Path, default=ROOT / "private/voice_profile.json")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "private")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--max-age-days", type=float, default=7)
    parser.add_argument("--publish-approved", action="store_true")
    parser.add_argument("--publish-limit", type=int, default=1)
    args = parser.parse_args()
    load_env(args.env_file)
    if os.uname().sysname == "Darwin" and not os.getenv("SSL_CERT_FILE"):
        os.environ["SSL_CERT_FILE"] = "/etc/ssl/cert.pem"
    os.environ.setdefault("GTMBE_OWNER_TELEGRAM_URL", "https://t.me/s/gtmbe")
    os.environ.setdefault("GTMBE_OWNER_TELEGRAM_CONFIRMED", "1")
    settings = {name: os.environ.get(name, "") for name in
                ("OPENAI_API_KEY", "PUBLORA_API_KEY", "THREADS_PLATFORM_ID", "THREADS_USERNAME",
                 "THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "ENABLE_LIVE_THREADS")}
    settings["OPENAI_MODEL"] = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    settings["PUBLISH_PROVIDER"] = os.getenv("PUBLISH_PROVIDER", "meta")
    with exclusive(args.db):
        db = connect(args.db)
        try:
            result = run_flow(db, args.sources, args.voice, args.work_dir, settings,
                              limit=args.limit, max_age_days=args.max_age_days,
                              publish_approved=args.publish_approved, publish_limit=args.publish_limit)
        finally:
            db.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "FLOW_INTERRUPTED", "error_type": type(exc).__name__,
                          "detail": "Check the private queue; never repeat an uncertain publication"}))
        raise SystemExit(1)
