# GTMBE → Threads | Customized Agent Skills Pack

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
