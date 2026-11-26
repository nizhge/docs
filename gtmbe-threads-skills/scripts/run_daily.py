#!/usr/bin/env python3
"""Daily GTMBE Threads research. Writes review-only artifacts; never posts."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from engine import candidates_from_sources, generate_draft, load_sources, write_json, exclusion_reason

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=ROOT / "config" / "research_sources.json")
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts" / "latest")
    parser.add_argument("--state", type=Path, default=ROOT / "local-state" / "drafted.json")
    parser.add_argument("--fixture", type=Path, help="Offline RSS fixture for tests; no live sourcing")
    parser.add_argument("--max-drafts", type=int, default=3)
    args = parser.parse_args()
    run_at = datetime.now(timezone.utc).isoformat()
    sources = load_sources(args.sources)
    if args.fixture:
        data = args.fixture.read_text(encoding="utf-8")
        sources = [{"name": "OFFLINE_FIXTURE", "type": "rss", "url": "https://example.com/feed"}]
        candidates, errors = candidates_from_sources(sources, fetcher=lambda _: data, max_age_days=36500)
        is_fixture = True
    else:
        candidates, errors = candidates_from_sources(sources)
        is_fixture = False
    state = {"drafted_ids": []}
    if args.state.exists():
        try:
            state = json.loads(args.state.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    used = set(state.get("drafted_ids", []))
    excluded = [{"id": x["id"], "source": x["source"], "url": x["url"], "reason": reason}
                for x in candidates if (reason := exclusion_reason(x))]
    excluded_ids = {x["id"] for x in excluded}
    fresh = [x for x in candidates if x["id"] not in used and x["id"] not in excluded_ids
             and x["relevance_score"] >= 37]
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    voice_path = Path(os.getenv("GTMBE_VOICE_PROFILE_PATH", ROOT / "private" / "voice_profile.md"))
    voice = voice_path.read_text(encoding="utf-8") if voice_path.exists() else ""
    # Never use real account credentials or publish from this command.
    drafts, generation_errors = [], []
    if api_key and not is_fixture:
        for item in fresh[: max(0, min(args.max_drafts, 10))]:
            try:
                draft = generate_draft(item, api_key, model, voice)
                drafts.append(draft)
                used.add(item["id"])
            except Exception as e:
                generation_errors.append({"item_id": item["id"], "error": f"{type(e).__name__}: {str(e)[:150]}"})
    briefs = [{"id": x["id"], "title": x["title"], "source": x["source"], "url": x["url"],
               "summary": x["summary"], "relevance_score": x["relevance_score"], "status": "RESEARCH_BRIEF_NOT_DRAFT"} for x in fresh[:10]]
    output = args.out
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "candidates.json", candidates)
    write_json(output / "excluded.json", excluded)
    write_json(output / "briefs.json", briefs)
    write_json(output / "drafts.json", drafts)
    report = {"run_at": run_at, "mode": "OFFLINE_TEST" if is_fixture else "DRAFT_ONLY", "sources_attempted": len(sources),
              "candidates_found": len(candidates), "candidates_eligible": len(fresh), "excluded_posts": len(excluded),
              "research_briefs": len(briefs), "review_required_drafts": len(drafts),
              "posts_published": 0, "voice_verified": False, "voice_profile_supplied": bool(voice.strip()), "model_enabled": bool(api_key) and not is_fixture,
              "source_errors": errors, "generation_errors": generation_errors}
    write_json(output / "report.json", report)
    report_text = f"# GTMBE Threads daily research\n\nRun: {run_at}\nMode: {report['mode']}\n\n"
    report_text += f"Sources attempted: {len(sources)}; candidates: {len(candidates)}; editorially excluded: {len(excluded)}; eligible: {len(fresh)}; briefs: {len(briefs)}; drafts needing review: {len(drafts)}; **published: 0**.\n\n"
    if not api_key:
        report_text += "No OPENAI_API_KEY: collected research briefs only; did not fabricate draft posts.\n\n"
    if not voice.strip():
        report_text += "No verified owner voice profile: generation (if enabled) uses conservative generic founder tone.\n\n"
    report_text += "## Highest-ranked research leads\n\n"
    for item in briefs[:7]:
        report_text += f"- [{item['title']}]({item['url']}) — {item['source']} (score {item['relevance_score']})\n"
    if errors:
        report_text += "\n## Unavailable sources\n\n"
        for error in errors:
            report_text += f"- {error['source']}: {error['error']}\n"
    if generation_errors:
        report_text += "\n## Drafting failures\n\n"
        for error in generation_errors:
            report_text += f"- {error['item_id']}: {error['error']}\n"
    (output / "report.md").write_text(report_text, encoding="utf-8")
    if not is_fixture:
        write_json(args.state, {"drafted_ids": sorted(used)[-1200:]})
    print(json.dumps(report, ensure_ascii=False))
    return 0 if candidates or not is_fixture else 1


if __name__ == "__main__":
    raise SystemExit(main())
