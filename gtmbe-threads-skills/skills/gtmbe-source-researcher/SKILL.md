---
name: gtmbe-source-researcher
description: "Discover and rank GTMBE owner content, public Telegram channels, VC/GTM research and relevant Threads discussions, with evidence links."
---
# gtmbe-source-researcher


## Trigger
Run daily for content discovery or when a GTM, SaaS, AI, startup or venture-building research topic is needed.

## Inputs
Current source registry, previous last-seen timestamps, GTMBE project's approved Notion links, validated personal Telegram address, public sites, optional accessible Threads search. Default to only publicly available content or content the owner is authorized to use.

## Coverage / rotation
1. **Owner-owned:** first look at verified GTMBE Telegram posts, public founder writing, personal author-approved notes, Notion project descriptions, previously published content. Proprietary or sensitive business records are NOT publication-ready merely because they are accessible.
2. **Public expert channels:** discover and maintain 15–30 quality Telegram channels by B2B leadgen, product marketing, growth, research, founder-led sales, venture, international GTM. Candidate seeds in `config/source_seeds.csv` are not vetted endorsements.
3. **VC/practitioner:** First Round Review, a16z, Bessemer Atlas, YC Library, Sequoia, Greylock, NFX, GTMnow, Lenny, SaaStr, Demand Curve, Reforge, ProductLed; broaden by evidence quality.
4. **Threads social listening:** only accessible public niche discussion topics with URLs and timestamps; do not fabricate unseen post text or engagement metrics.

## Extraction
For every material record `source_id, publisher, author, url, publication_at, retrieved_at, license_or_access, language, content_kind (owner/external), key_claims, original_contribution_opportunity, confidence, owner_relevance, source_quality, risk_flags`. Keep original source text private where needed; store only limited necessary quotes and summaries.

## Rank and dedupe
Prioritize high-quality primary evidence, market insight, case specificity, timeliness, usefulness to B2B founder/buyer, and novelty relative to existing output. Collapse syndicated reposts to the earliest primary source. Do not treat claims from a newsletter or creator as independently verified facts. Score 0–5 each: originality, buyer relevance, evidence, actionability, freshness; shortlist only defensible topics.

## Output
10–20 candidate ideas (or fewer if evidence is thin); each with a source URL, 1-sentence takeaway, 1 original GTMBE angle, evidence status, a proposed post type, and `hold` if it needs validation. Do not turn an external post into a disguised near-paraphrase.

## Safety
No joining private channels, bypassing paywalls, bulk harvesting personal data, copying gated content, or using borrowed writing as voice samples. A search snippet is not enough to verify a detailed claim; inspect original source where possible. Track access gaps accurately.
