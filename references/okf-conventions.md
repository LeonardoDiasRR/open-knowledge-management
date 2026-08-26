# OKF Conventions — field reference

Condensed from Google's **Open Knowledge Format v0.2** spec
([GoogleCloudPlatform/knowledge-catalog/okf/SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)).
OKF = a directory of Markdown files with YAML frontmatter; reserved names
`index.md` (directory listing, §8) and `log.md` (update history, §9).

## Concept frontmatter

```yaml
---
type: <Type name>                  # REQUIRED (only always-required key)
title: <display name>              # Recommended
description: <one-line summary>    # Recommended
resource: <canonical URI>          # Optional, for assets
tags: [<tag>, ...]                 # Optional
sources: [...]                     # Optional (provenance, §5.1)
generated: {...}                   # Optional (trust, §5.2)
verified: [...]                    # Optional (trust, §5.2)
---
```

- `type` values are **not centrally registered**; pick descriptive ones.
  Consumers must tolerate unknown types. This wiki uses
  `Source Summary | Entity | Concept | Synthesis` per its subdirectories.
- Producers may add extra keys; consumers preserve and never reject them.

## Provenance — `sources` (§5.1)

```yaml
sources:
  - id: ga4-schema
    resource: https://developers.google.com/analytics/bigquery/export-schema
    title: GA4 BigQuery Export schema
    author: team:ga4-docs
    usage_count: 5000
    last_modified: 2026-05-30T00:00:00Z
usage_window: { from: 2026-06-01T00:00:00Z, to: 2026-06-30T00:00:00Z }
```

- Per entry: `resource` REQUIRED; `id`, `title`, and the **credibility signals**
  (`author`, `usage_count`, `last_modified`) optional.
- OKF records **objective signals, not a score** — credibility is inferred by
  the consumer, never stored (a stored score is subjective and goes stale).
- Lineage is expressed through links; an entry whose `resource` points at
  another concept lets a consumer recurse and propagate credibility.

**Per-claim attribution:** a footnote whose label is a `sources[].id`:

```markdown
The events table is sharded daily.[^ga4-schema]
[^ga4-schema]: GA4 BigQuery Export schema
```

Keyed (not positional) so agent rewrites that reorder the list never misattribute.

## Trust — `generated` and `verified` (§5.2)

```yaml
generated: { by: reference_agent/gemini-2.5-pro, at: 2026-06-20T22:53:05Z }
verified:
  - { by: human:ahormati, at: 2026-06-25T09:00:00Z }
  - { by: process:finance-nightly, at: 2026-06-26T02:00:00Z }
# a single verifier may be a bare mapping (treated as one-element list)
```

- `generated` = how content was written; `verified` = who/what confirmed it
  against its sources. Distinct by design: writer ≠ confirmer.
- Absence carries meaning (`verified` empty ⇒ unverified concept) but is never
  a rejection.
- **Trust tier:** unverified → machine-confirmed → human-reviewed (from
  `verified`).

## Lifecycle & actors

- **Actor convention:** `<producer>/<version>` (agents),
  `human:<id>` (people), `process:<id>` (automated).
- **Timestamps:** ISO 8601 with explicit UTC offset (`2026-06-30T14:00:00Z`).

## Index files (§8)

- `index.md` MAY appear in any directory. Body groups concepts under headings,
  newest/progressive for browsing; entries SHOULD reuse the linked concept's
  `description`.
```markdown
# Section / Group Heading
* [Title](relative-url) - short description of item
```
- Producers may generate it; consumers may synthesize on the fly.
- EXCEPTION: a bundle-root `index.md` MAY carry an `okf_version` key.

## Log files (§9)

- `log.md` MAY appear at any level; **newest-first**; date headings in
  ISO `YYYY-MM-DD`; entries are prose, optional leading bold verb convention:
```markdown
# Directory Update Log
## 2026-05-22
* **Update**: Added a reference for [Customer Metrics](/tables/customer-metrics.md).
* **Creation**: Established the [Dataplex Playbook](/playbooks/dataplex.md).
```

## Attested Computation (§10)

A concept with `type: Attested Computation` carries the sanctioned way to
compute a value: an **executor** returns a **receipt**; an **attester**
(deterministic, no-LLM code) inspects the receipt and returns a **verdict**.
Use when a derived number must be provably produced as specified.