# GTMBE → Threads | Customized Agent Skills Pack

> **Current operating priority (2026-11-11): TELEGRAM_FIRST v1.** The scheduled automation now selects public Telegram posts only (and owner-owned posts once ownership is confirmed). The [master prompt](MASTER_AUTOMATION_PROMPT.md) is authoritative. VC/blog/newsletter research and novel market-essay generation below describe **future capabilities, not the current operating plan**. Own posts are minimally edited; external posts are never near-copied without rights. Live Threads publishing is disabled until approval and integration.

Independent GTMBE adaptation inspired by [sergebulaev/threads-skills](https://github.com/sergebulaev/threads-skills) (MIT). Based on its eight specialized tasks, with five added GTMBE workflows. This is **not** a modified upstream GitHub repository, production deployment, or connected social account. No posts were published.

## Persistent Telegram → voice → Threads route

`scripts/pipeline.py` joins source intake, the owner voice prompt, editorial drafts,
account-specific approval, and the Meta publisher in one local SQLite queue. This
route supports original commentary from external channels such as `@kyrillic` as
well as minimally edited owner text. It does not activate the older owner-only
GitHub publisher or claim an account is connected.

```bash
cd gtmbe-threads-skills
python3 scripts/pipeline.py status
python3 scripts/pipeline.py collect
python3 scripts/pipeline.py --env-file private/connection.env generate --limit 3
python3 scripts/pipeline.py export
```

The collector defaults to the previously confirmed owner channel `@gtmbe` plus
the configured external sources. `private/voice_profile.json` must contain
`status: CORPUS_REVIEWED` and at least eight distinct owner sample permalinks in
`sample_urls`, plus the actual style instructions/examples. A smaller curated
corpus may be provisional; profile presence does not imply owner approval. No
third-party text belongs in that style corpus. The target remains 30–100 samples.

Without a model key, collect sources and write drafts in an interactive agent
session. Import a JSON array of drafts with `source_url`, `text`, `angle`,
`original_contribution` and `verification_notes` using
`import-drafts --file private/drafts.json`. Sources must already be collected.
The new route refuses generic voice fallback. Draft generation always requires
review; automatic tests and source snippets are not fact verification.

Reserve existing canonical Notion drafts with
`import-history --file private/prior-source-urls.json` (a JSON array of Telegram
post permalinks). This prevents recreating previously drafted sources. The
SQLite journal persists sources, drafts, exact approvals and attempt outcomes
across runs. Similarity checking catches close text matches; it does not prove
semantic uniqueness. Continue reviewing for repeated ideas.

For an authorized destination account, copy `.env.example` privately and provide
the model key and/or Threads OAuth token there. Never put tokens in chat or git.
The model and publishing credentials are independent. Then:

```bash
python3 scripts/pipeline.py --env-file private/connection.env check-account
python3 scripts/pipeline.py approve --id draft_ID --sha256 EXACT_SHA256 --account HANDLE --note 'Evidence, originality and voice reviewed' --score 85
# Only within actual owner authorization, with ENABLE_LIVE_THREADS=1:
python3 scripts/pipeline.py --env-file private/connection.env publish --id draft_ID
# Read-only recovery after an uncertain attempt; never automatically re-sends:
python3 scripts/pipeline.py --env-file private/connection.env reconcile --id draft_ID
```

Each approval is bound to the final text and account. Before sending, the script
verifies `/me`, checks recent Threads text and the older owner publication ledger,
and commits a durable attempt marker. Publication uses Meta's create/wait/publish
flow, then checks exact text and a real HTTPS permalink. Unknown outcomes block
retries until reconciliation. Use one publisher/runtime for a given account;
the local SQLite queue is not synchronized across machines or the older Actions
workflow. Installing the skill or running `collect` does not create a background
service. Keep `private/` backed up securely for durable operation.

Official API reference: [Threads publishing](https://developers.facebook.com/documentation/threads/posts).

An interactive browser operator can use the same queue without an API token.
First verify the signed-in Threads profile, inspect the feed for duplicates,
and prepare the approved post. In authorized live mode, run
`begin-browser-publish --id draft_ID --account HANDLE --verified-profile-url https://www.threads.com/@HANDLE`
immediately before clicking Publish. This records a durable attempt and blocks
both browser and API retries. After opening the actual live post, save its
observed full text and real URL as a private JSON object with `text` and
`permalink`; use `confirm-browser-publish --id draft_ID --readback-file private/readback.json`.
The confirmation checks exact text and account. If the outcome is uncertain,
leave the attempt marker and use read-only UI inspection to find the existing
post. Do not click Publish again. These commands track a real UI operator;
they do not automate the browser or turn a login into a headless API service.

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

`python scripts/publish_threads.py --drafts artifacts/latest/drafts.json --id draft_... --approval private/approved_sha256.json` validates the exact text hash in a private approval map and **dry-runs** only. For live mode, the operator must additionally provide `--publish`, `ENABLE_LIVE_THREADS=1`, `THREADS_USER_ID`, and `THREADS_ACCESS_TOKEN` from an authorized Meta Threads OAuth flow. These credentials must not be committed. The adapter records `ATTEMPT_STARTED` / `CONTAINER_CREATED` / `API_CONFIRMED_LINK_PENDING`, then reads back the real permalink and exact text. Only `PUBLISHED_VERIFIED` with a Threads permalink counts as published. A missing or uncertain readback remains `API_CONFIRMED_LINK_UNVERIFIED` and must be reconciled manually; it is never republished blindly. No blanket consent to post is inferred.

### Limits

- Source snippets are not full article fact checks; all generated drafts require editorial review. The scores are relevance triage, not verified truth scores.
- The system does not currently read a personal Notion workspace or a private Telegram channel without additional authorized connectors.
- No Threads profile analytics or live account is connected, and no Threads posts have been published by this code.
- RSS and public Telegram HTML endpoints can change or block access; failures are surfaced.

## Live Telegram-first verification (2026-11-11)

- Source priority is now owner-authored Telegram content first; the user previously identified [@gtmbe](https://t.me/gtmbe) as their author channel. The public preview was successfully read by [GitHub Actions run 43032494986](https://github.com/nizhge/docs/actions/runs/43032494986). This is distinct from their contact @geni_al.
- Six selected external public Telegram channels also fetched successfully in the same run. Run result: 7 sources attempted, 61 candidates, 13 excluded, 28 editorially eligible, 10 research briefs, 0 generated drafts and **0 live publications**. Source dates and forwarded status are parsed where available.
- Editorial filtering rejects some job listings, event promotions, sponsored launches and forwards. Human selection is still necessary; not every message is suitable for Threads.
- The workflow has no `OPENAI_API_KEY` configured, so GitHub Actions does not automatically generate posts. ChatGPT may prepare drafts in the authorized private canonical Notion content queue (URL intentionally omitted from public repository), but that is a separate workflow.
- The GitHub publisher has tests for exact approved text and a real Threads permalink. No authorized Threads profile/token has been provided, so it has **not** been tested against a live Meta account. The repo is not a live posting service yet.


## Owner Telegram → Live Threads (new opt-in route, 13 Nov 2026)

**Working preview:** [GTMBE Threads Owner Publishing workflow](https://github.com/nizhge/docs/actions/workflows/gtmbe-threads-owner-publish.yml). It fetches public `@gtmbe` messages directly, not external Telegram channels. The owner channel was already identified in the project. The first remote preview fetched 16 messages without credentials. It did **not** publish anything.

**Safe default:** GitHub variable `GTMBE_AUTO_PUBLISH` is unset/false. Nothing is sent. Daily scheduled live publishing (09:47 Moscow) is activated only by the owner after authorizing the Threads account and setting the opt-in variable. Each run publishes at most ONE intact owner-written post, only if the post:
- is from `https://t.me/gtmbe/<number>`, not forwarded, promotional or a job ad;
- is recent (last 7 days), self-contained and already 120–500 characters;
- has no embedded external links, @mentions or potentially time-sensitive numerical claims;
- has not been attempted according to the durable repo ledger and does not already appear in the recent Threads feed.

Longer Telegram articles and posts failing these gates are NOT auto-reposted. They require editorial adaptation and explicit review; no third-party Telegram text is ever automatically republished.

**Approved edited-post queue:** `queue/owner_reviews.json` contains two existing owner-sourced Threads adaptations with `status=REVIEW_REQUIRED` and `approved_by_owner=false`. They are intentionally **not live**. When the owner explicitly approves the exact final texts, the agent/operator can set each approved item to `status=APPROVED` and `approved_by_owner=true` without altering its `text_sha256`. If any text changes, the SHA-256 digest must be recalculated and the revised text separately approved. Approved edits take priority over automatic short posts, even if their original Telegram source is older than 7 days. The persistent ledger prevents posting a source twice.

### One-time authorization (do not paste tokens into chat or GitHub source files)

1. In [Meta for Developers](https://developers.facebook.com/apps/), create or select an app with the **Threads API** use case. Add the actual Threads account as a tester/user if required, and grant `threads_basic` and `threads_content_publish`. Use the official [Meta Threads API Postman collection](https://www.postman.com/meta/threads/collection/dht3nzz/threads-api) to obtain a Threads user OAuth token; exchange it for a long-lived token before using an unattended workflow. Meta may require app review for accounts other than app testers.
2. Open [GitHub Actions Secrets](https://github.com/nizhge/docs/settings/secrets/actions) and add `THREADS_ACCESS_TOKEN`. Optionally add `THREADS_USER_ID` if you want an additional fixed-ID check. Tokens must never be committed or written to Notion.
3. Open [GitHub Actions Variables](https://github.com/nizhge/docs/settings/variables/actions) and set `THREADS_USERNAME` to the **exact authorized Threads handle** (without @). The script verifies that `/me` returns this handle before any POST request. Do not set `GTMBE_AUTO_PUBLISH` yet.
4. Run the workflow manually with `action=preview`, inspect which original post it would select. If the text and account are correct and you explicitly authorize ongoing owner-source verbatim posting, set `GTMBE_AUTO_PUBLISH=true` in Actions Variables. Then run manually with `action=publish` to test one real post. After successful readback and receipt persistence, the daily schedule runs in the same gated mode.

**Persistent ledger:** `gtmbe-threads-skills/state/owner_publications.json` is created only on the first live or already-existing reconciliation. Before the outbound POST, an `ATTEMPT_STARTED` marker is committed and pushed to GitHub. A failed/unknown API call keeps this marker and blocks automatic retries. A post is counted as published only after API success, a verified Threads permalink, and a second committed receipt. There is no blanket retry and no silent marking as published.

**Important limitation:** A Meta Threads long-lived token has an expiry and must be kept valid/renewed (typically within ~60 days). Current GitHub Actions cannot update repository secrets automatically. Reauthorize/rotate the token as required; otherwise the automated posting stops. Adding a Meta token is a user-controlled authorization step; it is not handled by the ChatGPT GitHub connector.

**Alternative:** Metricool can connect a Threads account and schedule posts through its own account connection flow, avoiding the need to build a Meta developer application. However it is not currently connected to this GitHub workflow.

### Validation / test

```bash
python -m unittest discover -s gtmbe-threads-skills/tests -v
python gtmbe-threads-skills/scripts/auto_publish_owner.py   # preview, no credentials, NEVER posts
```

The publisher stores only public post identifiers, text hashes, timestamps and public permalinks in git. It does not persist tokens or client content.
