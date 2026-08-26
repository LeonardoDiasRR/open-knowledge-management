# Query & Lint workflow

Drives the QUERY and LINT operations referenced from SKILL.md.

## Query

1. **Read the root `index.md`** to find relevant pages.
2. **Broaden search** if needed: read the per-directory `index.md` files and
   grep the wiki (`search_files(pattern, path=wiki)`) for the topic — don't
   trust the catalog alone.
3. **Read the relevant pages.**
4. **Synthesize an answer** with `[[wikilink]]` citations to the pages you
   actually used. Link generously but honestly.
5. **Offer to save** a durable answer as a new page in `wiki/synthesis/`
   (type: `Synthesis`). If the user agrees, create it and update the affected
   `index.md` and `log.md`.

## Lint (health check)

Scan and report, then offer to fix:

1. **Contradictions** between pages (same concept, conflicting claims).
2. **Stale claims** — content a newer source has superseded.
3. **Orphan pages** — pages with no inbound `[[wikilinks]]`.
4. **Missing concept pages** — important concepts mentioned (linked or in
   prose) but lacking their own page.
5. **Missing cross-references** — related pages that should link to each other.
6. **Data gaps** that a web search could fill — suggest them.
7. **Broken/empty index consistency** — `index.md` entries whose target page
   doesn't exist.

Report findings; offer to fix; **log the lint pass** (newest-first) when run.

## Tool hints

- Content search: `search_files(pattern="term", path="<wiki>/wiki",
  file_glob="*.md")`
- File search: `search_files(target="files", pattern="*.md", path="<wiki>/wiki")`
- Prefer exact `[[wikilink]]` names; verify targets exist before linking.