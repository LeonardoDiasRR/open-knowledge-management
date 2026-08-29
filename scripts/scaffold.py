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
generated: {{ by: openkm/1.0.0, at: {iso} }}
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
- **database/data.duckdb** — derived tabular data, created on demand by
  ingestion. It is separate from immutable `raw/`; do not create it while
  scaffolding and do not treat `database/` as a Markdown wiki section.
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
1. Read the source completely and copy the original under `raw/` before any
   helper call. `raw/` is immutable: never modify or replace the copied source.
2. Discuss takeaways with the user and create its Source Summary page in
   `wiki/sources/`.
3. For genuinely tabular CSV, TSV, and XLSX sources, persist automatically to
   the derived `database/data.duckdb` after inspection. Create one table per
   logical dataset, or one table per tabular XLSX worksheet. Show the result
   afterward, including the first five rows and the source page.
4. Inspect ordinary documents for visual tables and tabulatable text. These
   candidates are approval-gated: propose the logical dataset, schema, and
   first five rows, and persist only after explicit approval. A rejected
   proposal must not create a table.
 5. Add `source_id`, `source_page`, and `source_section` to every row; add
    `source_sheet` for Excel rows. Keep ambiguous values as text when possible,
    otherwise use `NULL` and record the caveat in the source page.
    `source_id` remains required and must never be `None`/`NULL`; set
    non-applicable `source_page`, `source_section`, and `source_sheet` fields to
    `None`/`NULL`.
6. Exclude formula-derived columns and aggregate cells from DuckDB while
   retaining their input columns. Document the original formula and equivalent
   DuckDB SQL only in the Source Summary page, never in the database or its
   catalog.
 7. On reingestion, reconstruct only the tables owned by that source; do not
    duplicate rows or change tables owned by other sources.
8. Create/update `entities/` and `concepts/` pages. Cross-link with
    `[[wikilinks]]`. Update every affected `index.md` and append a newest-first
    entry to the relevant `log.md`.

### Tabular persistence contract
 1. Before persistence, inspect the complete copied source. A missing or
   unreadable file, invalid raw/source paths, invalid JSON, malformed input
   (including CSV/TSV/XLSX), missing DuckDB support, unsupported extension, or
   non-tabular input is an explicit failure/status. Do not create a table or
   claim that data was saved. A non-tabular direct file follows the
   ordinary-document candidate workflow instead of automatic persistence.
2. Persist approved datasets to `database/data.duckdb` in one transaction. A
   persist or rebuild commits only after every data table, source catalog row,
   and table catalog row succeeds. On any parse, validation, dependency, or
   write failure, roll back the transaction, leave no partial writes, report the
   failure and source ID, and never claim success.
3. Rebuilds replace only the tables and catalog rows owned by the source ID,
   atomically. Remove the old source-owned data and write the replacement in
   the same transaction; preserve every other source and do not duplicate rows.
 4. A Source Summary in `wiki/sources/` is required for every persisted or
   proposed dataset. It must include source metadata and resource provenance,
   the database path `database/data.duckdb` when applicable, extraction status,
   a table inventory, each table's schema and row count, exactly the first five
   rows (or all rows when fewer exist), row provenance, formula notes, and
   caveats. Formula notes document excluded formula-derived or aggregate
   columns, their original formulas, retained input columns, and an equivalent
   DuckDB SQL expression when safe; when translation is unsafe, record exactly
   `no equivalent query was generated`. Formula definitions and cached formula
   values never go into DuckDB.
 5. Formula metadata is never stored in `_openkm_sources`, `_openkm_tables`,
    or user data tables. This includes formula definitions, original formulas,
    equivalent DuckDB SQL, and cached formula values; these belong only in the
    Source Summary.
 6. Every Source Summary must record the original formula and equivalent
    DuckDB SQL expression for each excluded formula-derived column or aggregate
    cell when translation is safe; when translation is unsafe, record exactly
    `no equivalent query was generated`.

### Query
1. The agent is the only query interface. Do not expose a SQL CLI or database
   UI to users. Read the root `index.md`, relevant catalog, and source page.
2. Use a read-only helper query against `database/data.duckdb`; never write SQL
   data during a query.
3. Synthesize an answer with `[[wikilink]]` citations and preserve source
   context. Offer to save durable answers in `wiki/synthesis/` (and then update
   index/log).
4. Locate the relevant Source Summary and table inventory before querying. A
   missing table, missing DuckDB support, unavailable database, or query
   failure is an explicit failure/status; do not claim a result or success.
5. Queries must be single, parameterized, read-only statements (`SELECT`,
   read-only `WITH`, `DESCRIBE`, or `SHOW`) executed through the helper in
   read-only mode. Reject unsafe or mutating queries, including multiple
   statements and `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP`, `ALTER`,
   `COPY`, `ATTACH`, `INSTALL`, `LOAD`, `EXPORT`, `VACUUM`, or `PRAGMA`.

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
 11. Report helper failures, invalid JSON, invalid raw/source paths,
    unsupported formats, malformed or unreadable input, rejected proposals,
    non-tabular input, missing tables, unsafe queries, rollback, and transaction
    failures honestly, with an explicit failure/status. Never claim a
    successful write or query when the data or result was not produced; a
    failed persistence or rebuild must leave no partial write.
12. Never invent values or provenance, and never modify immutable raw sources.
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


def write_if_missing(path: Path, content: str) -> bool:
    """Write only if the file does not yet exist. Used in adopt mode so the
    skill never overwrites a user's existing content. Returns True on write."""
    if path.exists():
        return False
    write(path, content)
    return True


def scaffold(root: Path, adopt: bool = False) -> None:
    existing_content = root.exists() and any(root.iterdir())
    if existing_content and not adopt:
        print(f"error: {root} is not empty; use --adopt to reuse it", file=sys.stderr)
        sys.exit(1)

    # AGENTS.md: always write for a fresh scaffold; keep any user one on adopt.
    write_if_missing(root / "AGENTS.md", AGENTS_MD) if adopt else write(root / "AGENTS.md", AGENTS_MD)
    if adopt:
        write_if_missing(root / "index.md", INDEX_SKELETON.format(title="Index", section="Pages"))
        write_if_missing(root / "log.md", LOG_SKELETON.format(title="Log"))
    else:
        write(root / "index.md", INDEX_SKELETON.format(title="Index", section="Pages"))
        write(root / "log.md", LOG_SKELETON.format(title="Log"))

    # Directories are idempotent — create only what is missing either way.
    (root / "raw").mkdir(parents=True, exist_ok=True)
    (root / "output").mkdir(parents=True, exist_ok=True)
    wiki = root / "wiki"
    wiki.mkdir(exist_ok=True)

    # Per-directory index/log: never clobber on adopt.
    def ensure_section(wiki: Path, section: str) -> None:
        title = SECTION_TITLES[section]
        w = wiki / section
        w.mkdir(parents=True, exist_ok=True)
        write_if_missing(w / "index.md", INDEX_SKELETON.format(title=title, section=title))
        write_if_missing(w / "log.md", LOG_SKELETON.format(title=title))

    ensure_section(wiki, "sources")
    ensure_section(wiki, "entities")
    ensure_section(wiki, "concepts")
    ensure_section(wiki, "synthesis")
    # ../wiki index/log at the wiki-level: only upgrade if missing.
    write_if_missing(wiki / "index.md", INDEX_SKELETON.format(title="Wiki Index", section="Sections"))
    write_if_missing(wiki / "log.md", LOG_SKELETON.format(title="Wiki Log"))

    # Self-contained config (a pointer, safe to write/update on adopt).
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
    ap.add_argument("--adopt", action="store_true",
                    help="Reuse an existing non-empty directory: create only missing "
                         "dirs/index/log and never overwrite existing content.")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    scaffold(root, adopt=args.adopt)
    print_tree(root)


if __name__ == "__main__":
    main()
