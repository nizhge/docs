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
Upstream scripts use Publora. Other supported paths can be configured using Meta Threads Graph API or a connected approved scheduler such as Metricool; **this package does not implement an API client**. Never claim direct API access based merely on these instructions.

## Preflight
Confirm account ID; credentials held in secret store (never paste them into public notes); final content + exact char count; substantial claims checked; privacy/rights cleared; no duplicate or earlier published post; approval scope; current platform limits; explicit account destination.

## Transaction
Create a unique `content_id` and idempotency key; record `publish_requested_at` and provider request ID. After call, verify a confirmed live post URL or provider success proof. On timeout/unknown result, look up provider status before retrying. For partially published threads record exact components and seek remediation, never blindly re-send entire thread.

## Output
`Published` only with actual external ID/URL/time. Otherwise `Scheduled`, `Failed` (reason), `PendingConfirmation` or `Draft`. Do not auto-comment or post quote replies unless separately approved and technically supported.
