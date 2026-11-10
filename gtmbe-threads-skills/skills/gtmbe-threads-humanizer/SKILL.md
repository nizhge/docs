---
name: gtmbe-threads-humanizer
description: "Edit GTMBE Threads drafts to match Georgy voice, remove templated AI rhetoric, and audit content quality without inventing facts."
---
# gtmbe-threads-humanizer


## Trigger
After every drafted post or comment, before approval/publishing. A profile-building request routes to `gtmbe-voice-profiler`.

## Inputs
Draft, verified claim ledger, voice version, audience, post goal, whether material is owner-first-person or externally sourced.

## Passes
1. **Faithfulness:** no new claims, quotations, invented numbers, fake customer outcomes or personal experiences; restore hedges only where the evidence warrants them.
2. **Owner voice:** read real samples from `Voice Profile`, not competitor channels. Favor clear conversational Russian, specificity, occasional light informality; preserve authentic quirks without mimicry of private messages. Minimal use of em dash. Do not force robotic sentence-length variation.
3. **De-template:** remove generic corporate hype, overstuffed triads, repeated rhetorical questions, artificial cliffhangers, emoji clutter, hashtags, 'не просто X, а Y' on repeat, 'в современном мире' and fake revelations.
4. **Format:** single idea; interesting first line; <=500 chars per ordinary post; <=1 hashtag; readable punctuation; no misleading source attribution, inappropriate link placement or off-platform 'subscribe now' artifacts.
5. **Readability:** check a founder/manager can understand the point without knowing source context.

## Quality score (100)
Actionable value 25; originality 20; GTMBE buyer relevance 20; owner voice 15; credibility 15; constructive discussion potential 5. Require >=80 AND zero factual blockers. This is an editorial heuristic, not a prediction of views.

## Output
Final version, exact character count, a short list of material edits, quality score, confidence in voice match, and status `READY_FOR_REVIEW` or `BLOCKED`. Never claim that edits beat an AI detector.
