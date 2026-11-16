---
name: gtmbe-publisher
description: "Safely publish only approved GTMBE Threads posts through an authenticated provider, with idempotency and receipt logging."
---
# gtmbe-publisher


## Trigger
A post is `APPROVED` or falls inside a clearly documented, still-valid `AUTO_APPROVED` scope AND a working authorized provider exists.

## Modes
- `DRAFT_ONLY` (default): NO network write; format drafts for human copy/paste and preserve review state.
- `APPROVAL_REQUIRED`: each post requires a specific approval identifying the final exact text/account; approval for one is not approval for every future post.
- `AUTO_APPROVED`: permitted only after owner explicitly authorizes account, categories, daily volume, exclusions, provider and dates. If any part is missing, revert to review.

## Provider
The current owner-selected provider is Publora. This package implements its single-target text-post client in `scripts/publish_publora.py`, private connection verification in `scripts/publora_connection.py`, and durable orchestration in `scripts/pipeline.py`. Direct Meta remains an alternative. A login, saved key or installed client does not prove the exact Threads channel is connected or that a post exists. Do not switch providers without the owner's instruction.

## Preflight
Confirm account ID; credentials held in secret store (never paste them into public notes); final content + exact char count; substantial claims checked; privacy/rights cleared; no duplicate or earlier published post; approval scope; current platform limits; explicit account destination.

## Transaction
Bind exact text and account approval in the persistent queue. Record the durable attempt before any outbound write. Publora sends one `publishNow` request with a stable idempotency key and saves the returned group ID. Read status with `reconcile`; no automatic or manual resend after uncertainty. Publora's reported success is `PUBLORA_PUBLISHED_REQUIRES_READBACK`: read the actual Threads post's visible text and permalink before `confirm-browser-publish` can record `PUBLISHED_VERIFIED`. Stored provider content is not live text readback. For partially published chains preserve exact components and inspect without re-sending; this implementation only submits a single text post.

## Output
`Published` only with actual external ID/URL/time. Otherwise `Scheduled`, `Failed` (reason), `PendingConfirmation` or `Draft`. Do not auto-comment or post quote replies unless separately approved and technically supported.
