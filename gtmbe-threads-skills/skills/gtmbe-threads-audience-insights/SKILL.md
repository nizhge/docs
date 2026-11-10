---
name: gtmbe-threads-audience-insights
description: "Analyze observed Threads performance and niche conversations without manufacturing unavailable audience metrics."
---
# gtmbe-threads-audience-insights


## Trigger
Before planning, weekly, and when evaluating niche opportunities or competitor discussion.

## Inputs
Actual Threads results from authorized analytics or compliant public read sources, plus dated screenshots/pastes where available. Upstream uses optional Apify for public niche/profile reads; absence of a token means data unavailable, not zero.

## Measures
By post: timestamp, topic, source category, hook, chars, type, observed views, replies, reposts, quotes, likes, follows, profile visits, UTM clicks and qualified business interest where accessible. By niche: list of observed discussions and precise URLs. Distinguish raw counts from normalized ratios and avoid false apples-to-apples comparisons when competitor follower counts aren't known.

## Analysis
Find which audience problems get thoughtful replies, not just engagement bait. Identify recurring objections, gaps and actionable ideas for GTMBE. Do not claim commenter identity or export private liker lists. Separate platform stats from website and CRM conversion data.

## Output
A dated evidence table, up to five editorial hypotheses, five discussion opportunities with URLs when actually retrieved, and limitations of the dataset. Feed topics into `gtmbe-threads-content-planner` and outcome data into `gtmbe-learning-loop`.
