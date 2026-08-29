# Karpathy's LLM Wiki — conceptual origin

The pattern this skill implements was proposed by **Andrej Karpathy** in a
short 2023 gist, ["An observation on LLM software development" / the LLM Wiki
gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

## Why it exists

An LLM is stateless across sessions: it forgets the codebase, domain notes,
and decisions it reasoned about yesterday. The LLM Wiki is Karpathy's answer —
make the model's own long-term memory a **browserable, persistent Markdown
knowledge base** that the agent reads at the beginning of every session and
writes back into as it works.

## The core insight

- Notes are **plain Markdown files** in the repo — human-readable, diffable,
  version-controlled. No database, no proprietary format.
- The agent **reads them up front** (context injection) and **writes them back**
  (new facts, corrections) as it goes.
- The wiki is a **shared, living artifact** — a human teammate can read it
  with any editor or tool, and the same notes drive a different agent tomorrow.

## How it maps to this skill

| Karpathy idea | openkm |
|---|---|
| Persistent Markdown memory | The wiki root (`raw/` + `wiki/`) |
| Agent reads it each session | Query/inject from `index.md` + pages |
| Agent writes back as it works | Ingest keeps pages current |
| Human-readable plain files | OKF Markdown + YAML frontmatter |
| Keep it structured, not a dump | `sources/entities/concepts/synthesis` + per-dir index/log |

## Why add OKF on top

Karpathy's original is deliberately loose ("just notes"). Google's **OKF**
([spec](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md))
adds the rigor an *agent-maintained* corpus needs once it grows: explicit
**provenance** (`sources`), **trust** (`generated`/`verified`, trust tiers),
**lifecycle**, and **attestation**, plus per-directory `index.md`/`log.md`.
The structure stays browserable Markdown, but the *where-from / how-much-to-trust /
is-it-fresh* questions become answerable from frontmatter, not left to prose.

## Reference

- Karpathy, A. — [LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- Google — [Open Knowledge Format spec](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
- Related community implementations: the `llm-wiki` skill, `second-brain`
  (NicholasSpisak/second-brain) — all descendants of the same idea.
