# miny-ven Scraper Ops

Operational control layer for the miny-ven music news scraper running on `y0-minynet.exe.xyz`.

## Purpose

Provide one CLI (`miny`) to run, monitor, deploy, and recover the existing scraper without changing `rss_scraper.py` pipeline logic.

## Runtime Model

- Scraper code: `/home/exedev/miny-ven/scraper/`
- Scheduler: VM cron (hourly at `:05`)
- Command entrypoint: `/home/exedev/bin/miny`
- Data store: Firestore (`articles`, `articles_archive`)

## Commands

```bash
miny run [--dry-run]
miny logs [--follow] [--lines=50]
miny status [--watch]
miny config [--show] [--set KEY=VAL]
miny deploy [--code|--config|--all]
miny test
miny rollback
miny metrics [--period=24h]
miny cron [--list|--disable|--enable]
miny alert [--slack|--telegram] URL
```

## What It Manages

- Remote execution over SSH
- Log tailing with error/warning highlighting
- Firestore freshness checks (default stale threshold: 3h)
- Deploy sync (code + config), preserving `.env`
- Encrypted local secret storage in `~/.minyven-cli/`
- Cron lifecycle (`enable`, `disable`, `list`)
- Backup/rollback workflow for quick recovery

## Recommended Daily Flow

```bash
miny status
miny metrics --period=24h
miny logs --lines=80
```

For incidents:

```bash
miny rollback
miny status
```
