# Remaining Items Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the 5 remaining items: X source supplementation, last30days integration, RC deep enrichment, DATA_FLOWS.md, and push design docs to repo.

**Architecture:** X and last30days run as Mac-side steps (tools only on Mac, not VM). RC deep enrichment uses SearXNG content snippets (RC SPA has no server API). Docs are written and committed to ven repo.

**Tech Stack:** Python 3.12, bird CLI (Mac), last30days CLI (Mac), SearXNG, PocketBase, git

---

## Task 1: X Source Supplementation for Thin Cities

**Problem:** Thin-press cities (<3 articles) only get SearXNG supplementation. X/Twitter often has music news these cities miss.

**Constraint:** `bird` CLI is only on Mac (not VM). X supplementation must run on Mac, not VM.

**Approach:** Add a Mac-side step to the deploy script that:
1. Reads the generated music-cities HTML to find thin cities
2. Searches X via `bird search "<city> music" --json --count 5` for each
3. LLM-filters results for music relevance
4. Appends qualifying tweets to the feed HTML

**Files:**
- Create: `scraper/x_supplement.py` (Mac-side, in ven repo)
- Modify: `/Users/aletviegas/bin/deploy-music-cities.sh` (add X step after VM pull)

**Step 1: Write x_supplement.py**

```python
#!/usr/bin/env python3
"""
x_supplement.py — Supplement thin cities in music-cities feed with X/Twitter results.

Runs on Mac (bird CLI is Mac-only). Reads the generated HTML, identifies cities
with <3 articles, searches X for music news, LLM-filters, and appends to HTML.

Usage:
    python3 x_supplement.py --html /path/to/music-cities.html [--dry-run]
"""
```

Key logic:
- Parse the HTML to count articles per city (regex on `<h3>City Name <span class="count">· N</span>`)
- For cities with <3 articles, run `bird search "{city} music news" --json --count 5`
- Use Ollama Cloud (from Mac env or hardcoded) to filter tweets for music relevance
- Append qualifying tweets as `<div class="article">` blocks under the city
- Add `source: "X Discovery"` to the meta
- Write modified HTML back

**Step 2: Integrate into deploy script**

Add after the SCP pull but before Vercel deploy:
```bash
# X supplementation (Mac-side, bird CLI)
python3 /tmp/ven-commit/scraper/x_supplement.py --html "$REPO_DIR/music-cities/index.html" 2>&1 || true
```

**Step 3: Test and commit**

---

## Task 2: last30days Integration for Thin Cities

**Problem:** Some cities have zero press coverage but active social discussion. last30days captures Reddit/X/YouTube/TikTok/HN posts.

**Constraint:** last30days CLI is only on Mac. Same pattern as X supplement.

**Approach:** Add a Mac-side step that runs last30days for cities with 0 articles.

**Files:**
- Create: `scraper/l30d_supplement.py` (Mac-side, in ven repo)

**Step 1: Write l30d_supplement.py**

Key logic:
- Parse HTML for cities with 0 articles
- For each, run `python3 ~/.claude/skills/last30days/skills/last30days/scripts/last30days.py "{city} music scene news"`
- Parse the last30days output (JSON) for music-related posts
- LLM-filter for relevance
- Append as articles with `source: "Social Discovery"`
- Cap at 2 per city

**Step 2: Integrate into deploy script** (after X supplement, before Vercel deploy)

**Step 3: Test and commit**

---

## Task 3: RC Deep Enrichment (Bio, Socials, Genres)

**Problem:** Current enrichment only stores the RC profile URL. We want bio, socials, and genres.

**Constraint:** RapidConnect is a client-rendered SPA with no server API. fastCRW gets a 404 page. But SearXNG search results include a `content` field with the bio text from the page meta tags.

**Approach:** Enhance `enrich_directory.py` to parse the SearXNG `content` field for bio data, and use fastCRW with `waitFor` + `renderDecision: {kind: "forceBrowser"}` to try getting the full page.

**Files:**
- Modify: `scraper/enrich_directory.py` (on VM + ven repo)

**Step 1: Update search_rc_profile to extract more data from SearXNG content**

The SearXNG result for Bad Bunny had content like:
> "Bad Bunny, born Benito Antonio Martínez Ocasio on March 10, 1994 in Puerto Rico, is a multifaceted artist known for his talents as a rapper, singer, and record producer in the genres of reggaeton, trap latino, and urbano latino."

Parse this for:
- `rc_bio`: the content text (first 2000 chars)
- `rc_genres`: extract genre names from the content (regex for "genres of X, Y, and Z")

**Step 2: Try fastCRW with forced browser rendering**

```python
payload = {
    "url": profile_url,
    "formats": ["markdown"],
    "waitFor": 8000,
    "renderDecision": {"kind": "forceBrowser"}
}
```

If this returns real content (not 404), parse the markdown for:
- Bio section
- Social links (Spotify, Instagram, etc.)
- Genre tags

**Step 3: Store all extracted data in PocketBase entities**

Update the PATCH to include `rc_bio`, `rc_socials`, `rc_genres` alongside `rc_profile_url`.

**Step 4: Test, commit, push**

---

## Task 4: DATA_FLOWS.md

**Purpose:** Document the full y0 pipeline architecture in the ven repo.

**Files:**
- Create: `DATA_FLOWS.md` in ven repo root (or `docs/DATA_FLOWS.md`)

**Content:**
- Architecture diagram (ASCII)
- All scripts and their schedules
- PocketBase collections and their roles
- Data flow: RSS → tagger → generator → entities → curator → enricher → deploy
- VM cron schedule
- Mac launchd schedule
- Vercel deploy flow
- Key env vars (non-secret)
- Troubleshooting guide

**Step 1: Write the doc**
**Step 2: Commit to ven repo**

---

## Task 5: Push Design/Plan Docs to Repo

**Purpose:** The design doc and implementation plan are only on the Mac. Push them to the ven repo for persistence.

**Files:**
- Copy: `docs/plans/2026-06-26-ve-curator-entity-directory-design.md` → `ven repo docs/`
- Copy: `docs/plans/2026-06-26-ve-curator-entity-directory-plan.md` → `ven repo docs/`

**Step 1: Copy docs to ven repo**
**Step 2: Commit and push**

---

## Summary

| Task | What | Effort | Where |
|------|------|--------|-------|
| 1 | X source supplement (bird CLI, Mac-side) | medium | ven repo + deploy script |
| 2 | last30days supplement (Mac-side) | medium | ven repo + deploy script |
| 3 | RC deep enrichment (bio/socials/genres) | medium | ven repo (modify enrich_directory.py) |
| 4 | DATA_FLOWS.md | small | ven repo |
| 5 | Push design/plan docs to repo | small | ven repo |

Tasks 1 and 2 can be built in parallel. Task 3 is independent. Tasks 4 and 5 are quick docs.