# GTMBE → Threads | Customized Agent Skills Pack

> **Current operating priority (2026-11-11): TELEGRAM_FIRST v1.** The scheduled automation now selects public Telegram posts only (and owner-owned posts once ownership is confirmed). The [master prompt](MASTER_AUTOMATION_PROMPT.md) is authoritative. VC/blog/newsletter research and novel market-essay generation below describe **future capabilities, not the current operating plan**. Own posts are minimally edited; external posts are never near-copied without rights. Live Threads publishing is disabled until approval and integration.

Independent GTMBE adaptation inspired by [sergebulaev/threads-skills](https://github.com/sergebulaev/threads-skills) (MIT). Based on its eight specialized tasks, with five added GTMBE workflows. This is **not** a modified upstream GitHub repository, production deployment, or connected social account. No posts were published.

## Purpose

Create original founder-led Russian Threads content around go-to-market, market research, B2B sales, product discovery, AI, startup building and international expansion, supported by traceable evidence. Source ideas from GTMBE's own publicly authorized material, selected public Telegram channels, venture funds, practitioner publications and social discussions. Optimize for qualified interest in GTMBE, not content volume.

## Architecture

`gtmbe-source-researcher` → `gtmbe-evidence-checker` → (`gtmbe-threads-repurposer` for OWN material **or** `gtmbe-threads-post-writer` for new synthesis) → `gtmbe-threads-humanizer` → human/automated QA + dedupe → **approval gate** → `gtmbe-publisher` → `gtmbe-learning-loop`.

`gtmbe-voice-profiler` maintains voice and Story Bank; `gtmbe-threads-hook-extractor` analyzes structures; `gtmbe-threads-audience-insights` studies relevant discussions; `gtmbe-threads-reply-drafter` drafts high-quality replies; `gtmbe-threads-content-planner` creates the editorial calendar; `gtmbe-threads-profile-optimizer` handles profile conversion.

## Included 13 skills

**Adapted from eight upstream roles**
1. `gtmbe-threads-post-writer`
2. `gtmbe-threads-humanizer`
3. `gtmbe-threads-hook-extractor`
4. `gtmbe-threads-reply-drafter`
5. `gtmbe-threads-repurposer`
6. `gtmbe-threads-content-planner`
7. `gtmbe-threads-profile-optimizer`
8. `gtmbe-threads-audience-insights`

**New GTMBE-specific roles**
9. `gtmbe-source-researcher`
10. `gtmbe-evidence-checker`
11. `gtmbe-voice-profiler`
12. `gtmbe-publisher`
13. `gtmbe-learning-loop`

## Recommended first run

1. Read `MASTER_AUTOMATION_PROMPT.md` and `config/settings.example.yaml`.
2. Confirm your actual Telegram channel URL and Threads handle. They are **not assumed**.
3. Import 30–100 authentic owner-written samples for style, if available. Never mix another creator's posts into owner voice training. Keep sensitive examples outside git.
4. Build source registry from `config/source_seeds.csv`; mark each public resource as verified only after actual retrieval.
5. Fill `templates/voice_profile.template.md` and `templates/story_bank.template.md` from **verified** material.
6. Produce 10 evidence-backed topic candidates and 5 draft Threads posts. Review your preferred voice and topics.
7. Only then connect an authorized provider to publish. The initial setting is `DRAFT_ONLY`.

## Running the skills

For Claude Code, Codex, Cursor, or an agent that reads `SKILL.md` skill folders, place the `skills/` folders in the platform's supported skills directory and instruct the agent to read the root `SKILL.md`. Exact installation paths depend on the agent. The pack is **instructions**, not executable scheduling or API integrations.

Use `MASTER_AUTOMATION_PROMPT.md` as the scheduled agent's master instruction. Let your authorized automation platform handle schedule and persistence. Example commands in the prompt are role descriptions, not shell commands.

The upstream bundle uses Publora for posting and optionally Apify for public Threads discovery. This adaptation is provider-neutral: Publora, a supported Meta Threads API implementation, or an approved social scheduler may be connected **after** separate configuration and authorization. The presence of a name in this pack does not mean an integration is working.

## Editorial defaults

- Primary content language: Russian; English research material may be summarized into new Russian analysis.
- Account voice: founder-led GTMBE. Brand 'Фокус' is a hypothesis, not yet an approved rebrand.
- 3–5 candidate drafts per day, if there is enough good material; 1–2 possible publications per day *only after approved live mode*.
- Under 500 characters for an ordinary text post; use explicit multipart structure when warranted. Re-check platform rules periodically.
- No automatic replies to other people's posts by default; provide context-grounded reply drafts.
- Attribution to underlying sources in the research record; no near-copying competitors' content.
- Never invent traction, user metrics, client names, founder quotes, or private/project details.

## Canonical record integration

Prefer reusing existing GTMBE Notion project pages and the established central CONTACTS/COMMUNICATIONS tables. Do not create parallel generic contact logs. Suggested content records: `source`, `idea`, `draft`, `publication`, `experiment` with stable IDs and links to canonical projects. Do not store private tokens in Notion or commit them to git.

## Publication safety

`DRAFT_ONLY` (default) → `APPROVAL_REQUIRED` (account connected and each post reviewed) → `AUTO_APPROVED` (only after explicit scoped owner consent). Authorization to draft is not authorization to publish, quote, auto-comment, or outreach. `AUTO_APPROVED` allows only low-risk, fact-checked posts in a previously approved scope; sensitive client/project claims always require individual review.

## Files

- `MASTER_AUTOMATION_PROMPT.md`: scheduled agent instructions
- `SKILL.md`: root skill router
- `skills/*/SKILL.md`: 13 specialized instructions
- `config/settings.example.yaml`: editable operational choices
- `config/source_seeds.csv`: candidates, not proof of access
- `templates/`: voice, story bank, source registry, post log, report
- `.gitignore`: protect private material
- `ATTRIBUTION.md`: acknowledgement of upstream MIT project

## Public repository and privacy

This repository contains **instruction files and examples only**. It does not include verified founder voice samples, personal Telegram exports, private Notion documents, credentials, client data, or a live social integration. Configure those privately on your own machine/integration. The templates have deliberately blank identity fields.

This standalone version adds `scripts/validate_skillpack.py` and a GitHub Actions check to validate the skills using only Python's standard library.

## License / credits

See [ATTRIBUTION.md](ATTRIBUTION.md) and [LICENSE](LICENSE). Inspired by Sergey Bulaev's MIT-licensed [`threads-skills`](https://github.com/sergebulaev/threads-skills); 13 independent GTMBE-specific instructions, not an official fork or endorsement.

## Executable research pipeline (added 2026-11-10)

The portable pack now includes a **working, standard-library Python prototype** in `scripts/engine.py`, `scripts/run_daily.py`, and `scripts/publish_threads.py`. This is separate from the 13 text skills above.

### Local quickstart

```bash
python -m unittest discover -s tests -v
python scripts/validate_skillpack.py
python scripts/run_daily.py --fixture tests/fixtures/sample_feed.xml --out artifacts/offline-test
python scripts/run_daily.py --out artifacts/latest
```

`run_daily.py` reads `config/research_sources.json`: public RSS feeds and public Telegram channel preview pages, ranks relevant posts, deduplicates, and writes `candidates.json`, `briefs.json`, `drafts.json`, `report.json`, `report.md`. Failed sources are reported, not treated as successful. All output remains **DRAFT_ONLY**. This command never publishes anything.

If `OPENAI_API_KEY` is configured in the runner's secrets, the engine can also generate up to three 500-character, evidence-bounded Russian Threads draft candidates using `OPENAI_MODEL` (default `gpt-4.1-mini`). With no API key, it produces research briefs, not fabricated AI posts. A *verified* writing-style profile can optionally be supplied through `GTMBE_VOICE_PROFILE_PATH` (a local private file). An operator-confirmed public owner channel can optionally be supplied as `GTMBE_OWNER_TELEGRAM_URL`, e.g. `https://t.me/s/your_confirmed_public_channel`. Do not guess ownership. The repo contains neither keys nor personal Telegram exports.

### GitHub Actions

When embedded in `nizhge/docs`, use the workflows under `github_workflows_for_repo_root/` as **root** `.github/workflows/gtmbe-threads-ci.yml` and `.github/workflows/gtmbe-threads-research.yml`. The latter only produces review artifacts and can run daily at **08:23 Europe/Moscow**, but schedules require the workflow to exist on the repository's **default branch**. A branch-only implementation does not run on a daily schedule. Artifacts expire after 14 days; dedupe state uses a small Actions cache (not a permanent database). Source availability is best effort, and browser-only/private/paywalled sources are not accessed.

### Publishing (separately approved, never by the daily workflow)

`python scripts/publish_threads.py --drafts artifacts/latest/drafts.json --id draft_... --approval private/approved_sha256.json` validates the exact text hash in a private approval map and **dry-runs** only. For live mode, the operator must additionally provide `--publish`, `ENABLE_LIVE_THREADS=1`, `THREADS_USER_ID`, and `THREADS_ACCESS_TOKEN` from an authorized Meta Threads OAuth flow. These credentials must not be committed. The adapter records `ATTEMPT_STARTED` / `CONTAINER_CREATED` / `API_CONFIRMED`; unknown outcomes are marked for manual reconciliation, never automatically retried. No blanket consent to post is inferred.

### Limits

- Source snippets are not full article fact checks; all generated drafts require editorial review. The scores are relevance triage, not verified truth scores.
- The system does not currently read a personal Notion workspace or a private Telegram channel without additional authorized connectors.
- No Threads profile analytics or live account is connected, and no Threads posts have been published by this code.
- RSS and public Telegram HTML endpoints can change or block access; failures are surfaced.