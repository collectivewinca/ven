---
title: Indie music feed cleanup and discovery quality
date: 2026-07-21
type: requirements
status: draft
product: ven (miny-ven)
reviewed: 2026-07-21 (ce-doc-review round 1 — safe fixes applied)
---

# Indie music feed cleanup and discovery quality

## Summary

Make VEN’s public feed **music-only**, then **indie-discovery-first** as inventory allows. Hard-clean the existing ~47k PocketBase `articles` corpus by **archiving, verifying restore on a pilot batch, then hard-deleting** non-music and **generic discovery noise**; demote major-press regurgitation so the list is not a Billboard/NME mirror; and retarget **SearXNG**/Brave (and other open-web discovery writers) so new rows favor music/indie domains. Full multi-source discovery pipeline (roster + Reddit primary + search last) is **phase 2**—not phase-1 acceptance.

## Problem

Live feed quality failed product intent:

- Newest items are dominated by **SearXNG Discovery** / **Brave Discovery**, including non-music stories.
- Soft ranking toward major music press (NME, Billboard) reduced random junk but **regurgitated majors**, which is the opposite of an indie discovery product.
- Client `sourceRank` currently **boosts** those majors—opposite of the desired product.
- Corpus size (~47k) includes years of mixed quality; the public UI should not treat all of it as first-class feed inventory.

Who hurts: creators and listeners opening `ven.minyvinyl.com` expecting music intelligence, not wire noise or hotel fires.

## Goals

- G1. Public feed shows **music** stories only.
- G2. Default ordering/feel moves toward **indie discovery**, not major-press echo.  
  - **Phase 1 bar:** music-only + majors de-centered (rarely show on first screen).  
  - **Phase 2 bar:** majority of first screen is specialty/community/curated/roster-linked (true discovery supply).
- G3. Existing non-music / generic discovery noise is **archived then removed** from live `articles` after a restore pilot (not soft-hidden only as the end state).
- G4. New open-web discovery ingest cannot re-pollute the corpus with non-music or generic web noise.
- G5. First ship (~1 week) **stops the bleed** and de-centers majors; mass hard-delete ships only after classifier holdout + archive restore pilot pass (may spill slightly past week-1 if safety gates fail).

## Non-goals

- Rewriting major-press headlines into original 60-word notes (deferred product).
- Deleting major-press **music** articles solely by source (user chose archive + demote, not ban-without-backup).
- Full roster + Reddit + search orchestration as phase-1 acceptance (phase 2).
- Redesigning VEN navigation/UI chrome beyond feed content rules.

## Key decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| K1 | Product feel = **indie discovery first** (full bar phase 2) | User confirmed; majors are not the default wire. |
| K2 | Cleanup = **hard delete + archive dump**, gated by **restore pilot** | Reversible only if restore is proven, not documented. |
| K3 | Majors = **demote, rarely show** with hard first-screen cap | Soft demotion alone can leave a major-heavy first page. |
| K4 | SearXNG/Brave (and peers): **allowlist phase 1**; full pipeline **phase 2** | Stop pollution first; add discovery supply next. |
| K5 | Week-1 = bleed stop + feed rules; mass delete after safety gates | Avoid over-deletion under calendar pressure. |

## Requirements

### Phase 1 — must ship for “clean public feed”

#### Corpus cleanup

- R1. Before any hard delete, produce an **archive dump** of rows selected for removal (full row payload including `id`, `source_url`, title/summary/source). Offline recoverable. **No delete until a pilot batch is restored to staging with id/count reconcile (see S5).**
- R2. From live `articles`, **hard-delete** (after archive) rows classified as **non-music** with **high precision** (prefer false-keep over false-delete). Definition of non-music: no durable music subject (artist, album, tour, label, scene, music product, or music industry).  
  - **Curated exception:** if `curated` is true, do not auto-delete; route to holdback review instead (aligns cleanup with operator intent).
- R3. From live `articles`, hard-delete (after archive) **generic discovery noise**: discovery-labeled sources (e.g. SearXNG Discovery, Brave Discovery, and peer open-web discovery labels) whose title/summary fail the music classifier—unless `curated` is true (then holdback, not silent keep-in-feed of non-music for public UI—see R6).
- R4. Do **not** hard-delete **music** rows solely because the source is NME/Billboard/etc.; those are demoted in the feed, not erased by source alone.
- R5. Cleanup is **idempotent and auditable**: operators see counts archived, deleted, retained, false-delete samples, and titles before/after.
- R6. Cleanup classifier must **not** reuse a weak keyword-only gate as the sole mass-delete authority without holdout precision proof (R17 / S6).

#### Public feed behavior

- R7. Public list and home **never show non-music** articles after cleanup and filter rules land (query/filter and/or post-cleanup inventory).
- R8. Public feed **demotes major press** (Billboard, NME, Rolling Stone, and similar wire/majors) relative to indie/music specialty, community, and curated sources. **Invert or replace** the current client `sourceRank` boost of majors (today majors rank above generic).
- R9. **Rarely show** is enforceable: in the first 25 public list rows, **at most 2** uncurated major-wire sources unless planning sets a different cap. Majors may appear more freely when `curated` is true.
- R10. Phase 1 major exceptions use **`curated === true` only**. Do not invent an open-ended “indie-relevant” auto-signal in phase 1 (that is phase-2 / roster territory).
- R11. If the public client path demotes using `curated`, it must **fetch** `curated` (and optionally `curator`)—those fields are currently omitted from the client article field list.
- R12. Soft client ranking is a **safety net only**; cleanup + ingest rules are required so junk never re-enters top inventory.

#### Ingest (phase 1)

- R13. New **open-web discovery** results (SearXNG, Brave, and any peer discovery writers that create PB rows—e.g. DDGS/Perplexity/Librarium if active) are accepted into live `articles` only if the landing domain is on a **music/indie domain allowlist** (ingest allowlist—not the same artifact as major demotion list).
- R14. Ship a **seed allowlist** in phase 1 (derived at least from known music RSS hosts + agreed indie domains), **fail-closed** if the list is missing/empty, with a named maintainer (closes O5).
- R15. Discovery queries for new ingest must be **music- and indie-oriented** (emerging artist, Bandcamp, underground/scene, genre music intents)—not open-web “breaking news” patterns.
- R16. At write time, reject non-music titles/summaries for discovery writers using a **shared music-enough definition** with cleanup. Prefer extracting/extending existing scraper keyword lists first; advanced/LLM classifiers only if holdback quality fails.  
  - **Split thresholds:** cleanup delete bar = high precision; ingest reject may quarantine uncertain rows rather than force the same cut.
- R17. A **holdback sample** of borderline rows (music-adjacent tech, festival cities, celebrity non-music, non-English titles) is reviewable before mass-delete thresholds lock. Require measured **music retention** on a labeled sample (see S6), not only “count dropped.”

### Phase 2 — deferred (not phase-1 acceptance)

These are product intent for the full indie discovery system. They do **not** gate the phase-1 ship.

- D1. Prefer discovery against **published roster / RapidConnect entities** (`sm_musicians` and related).
- D2. Prefer community sources already scaffolded (e.g. Reddit music subs including indieheads) as primary or co-primary.
- D3. SearXNG/Brave remain **last resort** after roster and community, still under allowlist + classifier.
- D4. Optional automatic “indie-relevant” major-press exception beyond `curated`.
- D5. Optional bounded quarantine for novel domains not yet on the allowlist (ops review), so discovery does not freeze forever.

**Optional phase-1 acceleration (not required):** enable one already-scaffolded indie supply path (e.g. Reddit indieheads preference) if S2a cannot be met by demotion alone—planning may promote this without waiting for full D1–D3.

## Success criteria

### Phase 1

- S1. Opening `/` and `/list` on a cold load: **zero non-music** stories in the first two pages (50 rows) for three consecutive days after phase-1 feed/ingest rules ship.
- S2a. In the first 25 list rows: **≤2** uncurated major-wire sources (rarely show), and **zero** generic discovery noise sources.
- S2b. *(Phase 2)* Majority of first 25 rows are specialty/community/curated/roster-linked—not major wire.
- S3. Of **raw open-web discovery candidates** in a sample window, reject rate for non-music / non-allowlisted is measurable; of **accepted** writes, re-validation pass rate ≥95%. Pair with a floor on accepted music volume so “95% pass” is not achieved by near-zero ingest.
- S4. After mass delete: live count drop reconciles with archive dump size ± error budget.
- S5. **Pilot restore:** one archived batch restored to staging with zero silent field loss (id + count checksum)—required before mass delete.
- S6. **Music retention:** on a human-labeled music holdout, ≥99% retained by the delete classifier before mass delete (or planning-agreed precision target).

## Scope boundaries

| Phase 1 | Phase 2+ | Outside product identity |
|---------|----------|---------------------------|
| Archive + restore pilot + hard-delete non-music / generic discovery noise | Roster-driven discovery | General news app |
| Invert major boost; hard first-screen major cap | Reddit/community primary | Original long-form CMS |
| Ingest domain allowlist (all open-web discovery writers) + music queries | Search as last resort | Firebase restoration |
| Shared high-precision cleanup + write-time reject | Novel-domain quarantine process | Ban majors without archive |

## Outstanding questions (for planning)

- O1. Exact major-wire domain/source list and first-screen cap (default ≤2 in 25).
- O2. Music-adjacent boundary (e.g. “Apple Music price hike” keep vs drop).
- O3. Archive storage location (object storage vs PB archive collection vs secured dump).
- O4. Demotion mechanism: client sort only vs server `filter`/`sort` vs `feed_weight` field.
- O5. Allowlist maintainer name + seed list review cadence (**must close in plan**, not leave open).
- O6. Whether week-1 enables one positive indie supply path (Reddit/roster) or waits for phase 2.

## Dependencies / assumptions

- A1. PocketBase `articles` remains source of truth for the live feed.
- A2. Fields `curated`, `curator`, `source`, `primary_genre`, `title`, `summary` are available; public fetch must include `curated` if used for R9–R10.
- A3. Scraper under `scraper/` owns ingest rules; existing music keyword helpers should be reused before inventing a second classifier.
- A4. Today’s PB archive step is effectively a no-op for historical tooling—**new** archive/export path is required (do not assume Firestore-era archive still applies).
- A5. Soft rank in the web client is inverted/replaced as part of phase 1, not left boosting majors.

## Approach selected

**Phase 1: stop pollution + music-only feed + majors rarely show (restore-gated hard cleanup).**  
**Phase 2: full indie discovery supply (roster + community + search last).**

## Context

- Live corpus ~47k+ articles; recent samples heavily SearXNG/Brave Discovery mixed with real music press.
- Client soft-rank currently elevates major press—must be inverted for this product.
- Scraper already has Reddit music sources (including indieheads) and curation concepts.
- Recent prod fixes: bounded PB pagination, SW v4—feed *loads* reliably; content quality is the remaining product gap.

## Review notes (round 1)

Applied from multi-persona review without changing product direction:

- Split G2 / S2 into phase-1 (music-only + rarely-show majors) vs phase-2 (indie majority).
- Gated hard-delete on restore pilot + music retention metric.
- Closed curated exception conflict (R2/R3); limited major exceptions to `curated` in phase 1.
- Expanded allowlist to all open-web discovery writers; seed list + fail-closed.
- Relabeled phase-2 items as D1–D5 (not phase-1 R acceptance).
- Required invert of existing major-boost soft rank; hard first-screen major cap.
- Normalized terminology: **SearXNG**, **generic discovery noise**.
