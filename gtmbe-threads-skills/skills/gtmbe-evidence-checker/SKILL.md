---
name: gtmbe-evidence-checker
description: "Check all material figures and claims against primary sources and block unverified first-person or client assertions."
---
# gtmbe-evidence-checker


## Trigger
Between research and publication; also before reusing metrics or creating a case study, quote, or timely news claim.

## Evidence method
1. Decompose a draft into atomic claims, including dates, percentages, comparisons, customer results, market size, product status, regulatory claims, and first-person statements.
2. Attach an exact supporting public URL, owner-authorized internal record, or explicit owner-supplied testimony for each. Assess source date and whether a claim is the source's observation, interpretation, or a verified fact.
3. Flag confidence: `verified`, `source-attributed opinion`, `needs verification`, `contradicted`, `private / requires permission`.
4. Independently corroborate quantitative and time-sensitive assertions if feasible. Do not present an industry opinion as settled science.
5. Verify all figures, names, customer identities and permission to disclose. Only publicly cleared data may go into publication. Redact client confidential information or skip.

## Gate
A major unverified, materially misleading, or private claim is a hard stop even if a draft otherwise scores above 80/100. Rewrite a claim as a clearly attributed opinion only when faithful to the source; otherwise exclude it.

## Format
Return a claim ledger with `claim, source URL/record, timestamp, status, revision, risk`, then a safe factual spine of no more than five points. Do not make up evidence or URLs.
