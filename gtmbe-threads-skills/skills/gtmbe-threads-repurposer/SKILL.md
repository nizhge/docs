---
name: gtmbe-threads-repurposer
description: "Turn GTMBE owner-owned Telegram posts, notes and public writing into native Threads posts while preserving original substance."
---
# gtmbe-threads-repurposer


## Trigger
An authenticated owner-owned post, talk excerpt, permitted project note or own publication exists and should be repurposed for Threads.

## Critical source rule
Repurpose ONLY the owner's content or content licensed/authorized for transformation. For third-party Telegram/VC/newsletter content, do original synthesis with `gtmbe-source-researcher` + `gtmbe-evidence-checker` + `gtmbe-threads-post-writer`; never use a tone rewriter to disguise copied work.

## Workflow
1. Preserve original permalink, author, date, copyright/access status.
2. Extract one key claim or observed lesson and what GTMBE can add now; split multiple ideas into separate drafts.
3. Recheck dated claims, numbers, strategic positioning and projects. An old post may no longer describe current business accurately.
4. Convert a Telegram essay into one <=500 char post or 2–4 connected posts if materially necessary. Avoid 'read more on Telegram' unless there is a genuine follow-up resource.
5. Rebuild the first line for Threads without changing meaning or pretending that 2024 anecdote happened in 2026.
6. Match current Voice Profile, run humanizer + evidence checker + dedupe against own archive.

## Output
`source`, `what was preserved`, `what updated`, `what excluded`, `draft`, `char count`, `attribution`, `quality`, `review status`. Never auto-publish by default.
