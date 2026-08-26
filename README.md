# Open Knowledge Management

> A self-contained agent skill that creates and manages a **personal LLM-Wiki** — a structured, queryable Markdown knowledge base using the **Open Knowledge Format (OKF)** — following **Andrej Karpathy's LLM Wiki** pattern.

On first use, the skill asks you **where** to store the wiki, saves that path, and scaffolds the folder structure and governing files (`AGENTS.md`, `index.md`, `log.md`). After that it ingests, queries, and lints the wiki the way a librarian-agent would.

---

## Why

- Karpathy's **LLM Wiki** [gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) is the founding pattern: a Markdown knowledge base that an AI agent maintains, cross-links, and answers questions from.
- Google's **Open Knowledge Format (OKF)** ([spec](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md), `okf/SPEC.md`, v0.2) defines a plain-Markdown + YAML-frontmatter format that makes an agent-maintained corpus **trustable** — `sources` (provenance), `generated`/`verified` (trust, lifecycle), `attestation`, `index.md`/`log.md` per directory.
- This skill combines both: **Karpathy's wiki shape, OKF's rigor.**

## Quick start (as a user)

```
hermes skills install --category note-taking --yes \
  https://raw.githubusercontent.com/LeonardoDiasRR/open-knowledge-management/main/SKILL.md
```

> Note: Hermes' `skills install` copies only `SKILL.md`; the first-run flow is fully described inside it, so it works standalone. For the deterministic scaffold, `scaffold.py` + templates, clone this repo or copy the `scripts/` directory into the installed skill folder.

Then ask the agent: **"create a wiki for me"** — it will ask for the root path, scaffold, and save the choice.

## What it does

| Task | Behavior |
|------|----------|
| **First run** | Asks for the wiki root path, saves it, scaffolds `AGENTS.md` + structure |
| **Ingest** | Reads sources (docs, web research) → source pages + entity/​concept pages + wikilinks, updates index/log |
| **Query** | Searches the wiki and answers with `[[wikilink]]` citations |
| **Lint** | Health-check: orphan pages, stale claims, broken links, data gaps |

## Directory structure the skill scaffolds

```
<wiki-root>/
├── AGENTS.md            # Governing rules (generated, self-contained)
├── index.md             # Root index (OKF §8)
├── log.md               # Root log, newest-first (OKF §9)
├── raw/                 # Immutable source materials (never edited)
├── wiki/
│   ├── index.md · log.md        # per-directory index/log (OKF)
│   ├── sources/   # one summary page per ingested source
│   ├── entities/  # people, organizations, products, tools
│   ├── concepts/  # ideas, frameworks, patterns
│   └── synthesis/ # comparisons, analyses, cross-cutting themes
└── output/             # reports, query results, generated artifacts
```

Every `wiki/*` subdirectory keeps its own `index.md` and `log.md` (newest-first), per OKF §8/§9.

## License

MIT — see [LICENSE](LICENSE).

## Origins

- [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Google Open Knowledge Format (OKF) spec](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
- Pattern reference: the [knowledge-management](note-taking) skill.