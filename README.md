# Chitrak — Rulebook & Technical Inspection Checklist

Interactive checklist dashboard for the **SIEP E-Bike Challenge 2026** rulebook and
technical inspection (TI) sheet. 239 items, dependency-aware, with shared progress.

**Live:** https://checklist-three-omega.vercel.app

No login. Open the link, tick boxes, progress syncs for everyone.

---

## Build

```bash
npm install          # jsdom + puppeteer, for tests only
npm run build        # -> Chitrak — Rulebook Checklist.html
```

`npm run build` runs two steps:

1. `_build.py` concatenates the rule data (`_data_rules.py`, `_data_ti.py`) with the
   client script, injecting Supabase credentials from `supabase-config.json`.
2. `_assemble.py` wraps the result in the single-file HTML shell.

The output is one self-contained HTML file — no runtime dependencies, no network
calls except Supabase. Drop it on any static host.

### Deploying

```bash
npm run build
mkdir -p deploy && cp "Chitrak — Rulebook Checklist.html" deploy/index.html
```

Then either push `deploy/` to Vercel as a static site, or use **Vercel → Add New →
Deploy** and drag the folder in. The current deployment is a Vercel Drop, not a
Git-connected project.

---

## Supabase setup

Credentials are **not** in this repository. `supabase-config.json` is git-ignored and
`_build.py` reads it at build time:

```json
{
  "url": "https://<project>.supabase.co",
  "anonKey": "sb_publishable_<publishable-key>"
}
```

If the file is missing, the build still succeeds and produces a **local-only** build
with sync disabled — useful for offline review.

To start a fresh project, run the schema in [`supabase/schema.sql`](supabase/schema.sql).

### Two tables

| Table | Grain | Written when |
|---|---|---|
| `rule_state` | one row per rulebook item | a rulebook checkbox is ticked |
| `inspection_state` | one row per TI item | a TI checkbox is ticked |

Un-ticking a box **deletes** the row, so the table is a sparse set of *completed* items
rather than a flag per item. Writes are upserts keyed on the item's stable id, which is
why the same item resolves to the same row across browsers and reloads.

Sync is last-write-wins per item. Two people ticking the same item within the same
second can race; in practice the UI hides the conflict because both end up ticked.

---

## Local development

```bash
npm run serve        # static server on :8000
npm run mock         # mock Supabase on :54321 (see mock-supabase.js)
npm test             # 109 functional tests, no network
npm run test:sync    # end-to-end sync tests against the mock
npm run verify       # re-verify OCR data against the source PDFs
```

`localhost` and `vercel.app` are **different origins**, so their browser-local state is
independent. To move progress between them, use **Export JSON** and **Import JSON** in
the dashboard UI.

---

## Data provenance

`_data_rules.py` and `_data_ti.py` were transcribed from:

- `Rulebook-V-1.0.pdf` — 173 items
- `TI SHEET.pdf` — 66 items

The PDFs are git-ignored (27 MB). Transcription was machine-verified for all 144
numbers and standards. **Prose was not fully reviewed** — items **C.10** (battery/motor)
and **C.12** (gear) should be checked against the PDFs before this is relied on as
compliance evidence.

---

## Tests

`npm test` covers item counts, rule dependency logic, persistence, sync reconciliation,
and export/import. `npm run test:sync` exercises the real request paths against the mock
server. Both are runnable without any credentials.
