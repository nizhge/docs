#!/usr/bin/env python3
"""Guarded Meta Threads text publisher; never invoked by the research workflow.

Requires explicit SHA-256 approval, live flag, OAuth credentials and an operator --publish.
If publish status is uncertain, it records UNKNOWN and refuses an automatic retry.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://graph.threads.net/v1.0"


def write_atomic(path: Path, content: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def fetch_approved(drafts_file: Path, approval_file: Path, draft_id: str) -> dict:
    if not approval_file.exists():
        raise ValueError("Approval file missing. No post may be published.")
    draft = next((d for d in json.loads(drafts_file.read_text(encoding="utf-8")) if d.get("id") == draft_id), None)
    if not draft:
        raise ValueError("Draft ID not found")
    if draft.get("status") != "REVIEW_REQUIRED":
        raise ValueError("Only reviewed source-backed drafts may enter this publisher")
    text = draft.get("text", "")
    expected = sha256(text.encode("utf-8")).hexdigest()
    if not 30 <= len(text) <= 500 or expected != draft.get("text_sha256"):
        raise ValueError("Draft text changed or is outside standard length limits")
    approvals = json.loads(approval_file.read_text(encoding="utf-8"))
    if approvals.get(draft_id) != expected:
        raise ValueError("Draft has not been approved with its exact SHA-256")
    return draft


def _post(url: str, args: dict, token: str, timeout: int = 25) -> dict:
    request = Request(url, data=urlencode(args).encode("utf-8"), method="POST",
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(150_000))


def publish(draft: dict, receipts_file: Path, user_id: str, token: str, poster=_post) -> dict:
    if not user_id.isdigit():
        raise ValueError("THREADS_USER_ID must be numeric")
    if not token:
        raise ValueError("THREADS_ACCESS_TOKEN is missing")
    receipts = json.loads(receipts_file.read_text(encoding="utf-8")) if receipts_file.exists() else {}
    draft_id = draft["id"]
    if draft_id in receipts:
        raise ValueError(f"Refusing duplicate/uncertain retry: previous state = {receipts[draft_id]['status']}")
    # Guard before the first external request, so interrupted runs do not post duplicates.
    receipts[draft_id] = {"status": "ATTEMPT_STARTED", "at": datetime.now(timezone.utc).isoformat()}
    write_atomic(receipts_file, receipts)
    try:
        container = poster(f"{BASE}/{user_id}/threads", {"media_type": "TEXT", "text": draft["text"]}, token)
        container_id = container["id"]
        receipts[draft_id] = {"status": "CONTAINER_CREATED", "container_id": container_id}
        write_atomic(receipts_file, receipts)
        result = poster(f"{BASE}/{user_id}/threads_publish", {"creation_id": container_id}, token)
        media_id = result["id"]
        receipts[draft_id] = {"status": "API_CONFIRMED", "container_id": container_id,
                              "post_id": media_id, "at": datetime.now(timezone.utc).isoformat()}
        write_atomic(receipts_file, receipts)
        return receipts[draft_id]
    except Exception as exc:
        previous = receipts[draft_id]
        previous["status"] = "UNKNOWN_REQUIRES_MANUAL_RECONCILIATION"
        previous["error_type"] = type(exc).__name__
        write_atomic(receipts_file, receipts)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drafts", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True, help="Private JSON map of draft_id to approved sha256")
    parser.add_argument("--id", required=True, help="Exact draft id")
    parser.add_argument("--receipts", type=Path, default=Path(__file__).resolve().parents[1] / "private" / "publish_receipts.json")
    parser.add_argument("--publish", action="store_true", help="Without this flag, only local approval checks run")
    args = parser.parse_args()
    draft = fetch_approved(args.drafts, args.approval, args.id)
    if not args.publish:
        print(json.dumps({"status": "DRY_RUN_APPROVAL_VALID", "id": args.id}, ensure_ascii=False))
        return 0
    if os.getenv("ENABLE_LIVE_THREADS") != "1":
        raise SystemExit("Live mode blocked: ENABLE_LIVE_THREADS must equal 1")
    result = publish(draft, args.receipts, os.getenv("THREADS_USER_ID", ""), os.getenv("THREADS_ACCESS_TOKEN", ""))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
