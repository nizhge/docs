#!/usr/bin/env python3
"""Offline validation for the GTMBE Threads skill pack (stdlib only)."""
from pathlib import Path
import csv
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted((ROOT / "skills").glob("*/SKILL.md"))
ERRORS = []
if len(FILES) != 13:
    ERRORS.append(f"expected 13 skill files, got {len(FILES)}")

for file in [ROOT / "SKILL.md", *FILES]:
    content = file.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", content, flags=re.S)
    if not match:
        ERRORS.append(f"{file.relative_to(ROOT)}: missing YAML frontmatter")
        continue
    frontmatter = match.group(1)
    for key in ("name", "description"):
        if not re.search(rf"^{key}:\s*\S", frontmatter, flags=re.M):
            ERRORS.append(f"{file.relative_to(ROOT)}: missing {key}")
    if file != ROOT / "SKILL.md":
        expected = file.parent.name
        if not re.search(rf"^name:\s*{re.escape(expected)}\s*$", frontmatter, flags=re.M):
            ERRORS.append(f"{file.relative_to(ROOT)}: name must be {expected}")

with (ROOT / "config/source_seeds.csv").open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle))
    for row in rows:
        if not row.get("id") or not row.get("verification_status"):
            ERRORS.append("source_seeds.csv: empty id/status")

for file in ROOT.rglob("*"):
    if file.is_file() and ".git" not in file.parts and file.suffix.lower() in {".md", ".yaml", ".csv", ".py", ".yml"}:
        text = file.read_text(encoding="utf-8")
        if "app.notion.com" + "/p/" in text:
            ERRORS.append(f"{file.relative_to(ROOT)}: private Notion page URL included")
        if "ghp" + "_" in text or "sk" + "_live_" in text:
            ERRORS.append(f"{file.relative_to(ROOT)}: possible credential string included")

if ERRORS:
    print("Validation failed:")
    print("\n".join(" - " + message for message in ERRORS))
    sys.exit(1)
print(f"Validation passed: {len(FILES)} skills, {len(rows)} source candidates, no obvious secret URLs")
