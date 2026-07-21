# Indie feed cleanup runbook (phase 1)

Origin: `docs/brainstorms/2026-07-21-indie-music-feed-cleanup-requirements.md`  
Plan: `docs/plans/2026-07-21-001-feat-indie-feed-cleanup-plan.md`

## Prerequisites

- Python 3.10+ with scraper deps
- Network access to `https://miny-database.exe.xyz`
- For **restore-pilot** and **execute**:  
  `ARTICLES_PB_ADMIN_EMAIL`, `ARTICLES_PB_ADMIN_PASSWORD`
- Staging collection `articles_restore_pilot` created in PB admin (clone schema of `articles`) **before** restore-pilot

## Order of operations

### 1. Classifier dry-run (safe, public read)

```bash
cd scraper
python3 archive_articles.py report --sample 1000
python3 cleanup_non_music.py dry-run --sample 2000 --out /tmp/cleanup-report.json
```

### 2. Export archive (safe write to local disk)

```bash
mkdir -p ../archives
python3 archive_articles.py export --out ../archives/articles-$(date +%Y%m%d) --limit 500
# After confidence, full corpus:
# python3 archive_articles.py export --out ../archives/articles-$(date +%Y%m%d)-full --all
python3 archive_articles.py verify --archive ../archives/articles-YYYYMMDD
```

### 3. Restore pilot (required before any mass delete)

```bash
export ARTICLES_PB_ADMIN_EMAIL=...
export ARTICLES_PB_ADMIN_PASSWORD=...
python3 archive_articles.py restore-pilot \
  --archive ../archives/articles-YYYYMMDD \
  --collection articles_restore_pilot
```

Confirm: restored count matches exported deletable ids (holdback excluded).

### 4. Holdout / human review

- Spot-check `cleanup-report.json` and archive JSONL titles  
- Music retention: sample known music ids must **not** appear as delete candidates  
- Curated non-music appear only as holdback, never auto-delete  

### 5. Mass delete (destructive)

```bash
python3 cleanup_non_music.py execute \
  --archive ../archives/articles-YYYYMMDD \
  --limit 100 \
  --i-understand
# Then full after pilot delete batch OK:
# python3 cleanup_non_music.py execute --archive ../archives/articles-YYYYMMDD --i-understand
```

Audit log: `delete_audit.json` in archive dir.

### 6. Ingest bleed-stop (already in code)

- `music_classifier.py` + `discovery_allowlist.py`  
- Discovery paths call `discovery_may_ingest` (domain allowlist fail-closed)  
- Seed list: `scraper/config/music_domain_allowlist.txt`  
- Deploy scraper host with updated files  

### 7. Web feed (already deployed)

- Client demotes majors, hides discovery noise labels, caps majors in first 25  
- Hard-refresh if SW caches old JS  

### 8. Observe

- 3 cold loads of `/` and `/list`: zero non-music in first 50 rows  
- ≤2 uncurated major-wire sources in first 25  

## Rollback

Re-import from archive JSONL into `articles` via restore tooling (or manual PB import). Keep archives offline and backed up.
