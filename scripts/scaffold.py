#!/usr/bin/env python3
"""Scaffold an Open Knowledge Management LLM-Wiki (OKF-strict).

Creates the directory tree and skeleton files described in SKILL.md:
AGENTS.md (self-contained governing rules), index.md and log.md at the root
and in every wiki subdirectory, plus raw/, output/ and the wiki sections.

Usage:
    python3 scaffold.py --root /path/to/wiki-root

Self-contained: only the Python standard library. Templates are embedded
here so the script works even if shipped without the templates/ folder.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

INDEX_SKELETON = """# {title}

Master catalog of this directory. Updated on every operation.

## {section}

(this section auto-populates as pages are added)

"""
# Newest-first per OKF §9.
LOG_SKELETON = """# {title}

Chronological history, newest-first. Never edit existing entries.

"""

# A ready-to-copy page template.
PAGE_TEMPLATE = """---
type: {type}                 # Source Summary | Entity | Concept | Synthesis
title: {Title}
description: One-line summary of the page.
tags: [tag1, tag2]
sources:
  - id: source-file.md
    resource: path/or/url/to/source
generated: {{ by: open-knowledge-management/1.0.0, at: {iso} }}
---

# {Title}

(body in structural Markdown; cross-link pages with [[wikilinks]])
"""

AGENTS_MD = """# AGENTS.md — Open Knowledge Management Wiki

You are the librarian of a personal LLM-Wiki in the **Open Knowledge Format (OKF)**.
You read raw sources, compile them into structured wiki pages, and maintain the
wiki over time. You never improvise structure. Follow these rules exactly.
(Pattern: Karpathy's LLM Wiki · Format: Google Open Knowledge Format v0.2.)

## Architecture (three roles)

- **raw/** — immutable source documents. Read, but NEVER modify.
- **wiki/** — your workspace. Create, update, and maintain all files here.
  - `wiki/sources/` — one summary page per ingested source
  - `wiki/entities/` — people, organizations, products, tools
  - `wiki/concepts/` — ideas, frameworks, theories, patterns
  - `wiki/synthesis/` — comparisons, analyses, cross-cutting themes
- **output/** — reports, query results, and generated artifacts.

Every `wiki/*` subdirectory keeps its own `index.md` (catalog) and `log.md`
(history). The root also keeps `index.md` and `log.md`.

## Page format (OKF)

Every page except `index.md`/`log.md`/`AGENTS.md` is a concept with YAML
frontmatter and a Markdown body:

```yaml
---
type: Entity                 # REQUIRED: Source Summary | Entity | Concept | Synthesis
title: Page Name             # Optional display name
description: One-line summary
resource: https://...        # Optional canonical URI
tags: [tag1, tag2]           # Optional
sources:
  - id: src.md               # stable footnote key
    resource: path/url/to/source
sources_verified_by: human:owner   # optional trust signal
---
```

- `type` is the only required key.
- All timestamps are ISO 8601 with an explicit UTC offset.
- Prefer structural Markdown (headings, lists, tables, fenced code).
- Use `[[wikilinks]]` for all internal references to pages that exist.

## Operations

### Ingest
1. Read the source completely. 2. Discuss takeaways with the user.
3. Save the original under `raw/` (immutable). 4. Create a Source Summary page
in `wiki/sources/`. 5. Create/update `entities/` and `concepts/` pages.
6. Cross-link with `[[wikilinks]]`. 7. Update every affected `index.md`.
8. Append a newest-first entry to the relevant `log.md`.

### Query
1. Read the root `index.md` to find relevant pages. 2. Read them.
3. Synthesize an answer with `[[wikilink]]` citations. 4. Offer to save durable
answers in `wiki/synthesis/` (and then update index/log).

### Lint
Scan for contradictions, stale claims, orphan pages (no inbound links), missing
concept pages, and weak cross-references. Report and offer to fix. Log the pass.

## Rules
1. Never modify files in `raw/`.
2. Always update `index.md` (root + per-directory) on create/delete.
3. Always append to `log.md`, newest-first, on every operation.
4. Use `[[wikilinks]]` for all internal references.
5. Every page has YAML frontmatter with at least `type` and `title`.
6. New information that contradicts old content: update the page, note both.
7. Keep source summaries factual; put interpretation in concept/synthesis pages.
8. When asked a question, search the wiki first.
9. Prefer updating existing pages over creating new ones.
10. Keep index entries one line, under 120 characters.
"""

# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------

SECTIONS = ["sources", "entities", "concepts", "synthesis"]

SECTION_TITLES = {
    "sources": "Sources",
    "entities": "Entities",
    "concepts": "Concepts",
    "synthesis": "Synthesis",
}


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def scaffold(root: Path) -> None:
    if root.exists() and any(root.iterdir()):
        print(f"error: {root} is not empty; refusing to overwrite", file=sys.stderr)
        sys.exit(1)

    write(root / "AGENTS.md", AGENTS_MD)
    write(root / "index.md", INDEX_SKELETON.format(title="Index", section="Pages"))
    write(root / "log.md", LOG_SKELETON.format(title="Log"))
    (root / "raw").mkdir(parents=True, exist_ok=True)
    (root / "output").mkdir(parents=True, exist_ok=True)
    wiki = root / "wiki"
    wiki.mkdir()
    write(wiki / "index.md", INDEX_SKELETON.format(title="Wiki Index", section="Sections"))
    write(wiki / "log.md", LOG_SKELETON.format(title="Wiki Log"))
    for section in SECTIONS:
        title = SECTION_TITLES[section]
        write(wiki / section / "index.md", INDEX_SKELETON.format(title=title, section=title))
        write(wiki / section / "log.md", LOG_SKELETON.format(title=title))
    # Self-contained config.
    write(root / "data" / "config.json", json.dumps({"wiki_root": str(root)}, indent=2) + "\n")


def print_tree(root: Path) -> None:
    print(f"Created wiki at {root}")
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        depth = dirpath.replace(str(root), "").count(os.sep)
        indent = "  " * depth
        print(f"{indent}{os.path.basename(dirpath)}/")
        for name in sorted(filenames):
            print(f"{indent}  {name}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Scaffold an OKF LLM-Wiki.")
    ap.add_argument("--root", required=True, help="Absolute path of the wiki root.")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    scaffold(root)
    print_tree(root)


if __name__ == "__main__":
    main()