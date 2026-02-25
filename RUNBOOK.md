# miny-ven Scraper VM Runbook

VM: `y0-minynet.exe.xyz`  
User: `exedev`

## Quick Commands (run on VM)

```bash
MINY_LOCAL_MODE=1 /home/exedev/bin/miny status
MINY_LOCAL_MODE=1 /home/exedev/bin/miny run
MINY_LOCAL_MODE=1 /home/exedev/bin/miny logs --follow
MINY_LOCAL_MODE=1 /home/exedev/bin/miny metrics --period=24h
MINY_LOCAL_MODE=1 /home/exedev/bin/miny rollback
```

## Cron

Current scraper cron (hourly at `:05`):

```cron
5 * * * * /usr/bin/flock -n /home/exedev/miny-ven/scraper/.rss_scraper.lock /bin/bash -lc 'MINY_LOCAL_MODE=1 /home/exedev/bin/miny run'
```

Useful checks:

```bash
crontab -l
MINY_LOCAL_MODE=1 /home/exedev/bin/miny cron --list
```

## Paths

- Scraper code: `/home/exedev/miny-ven/scraper/`
- Logs: `/home/exedev/miny-ven/logs/rss-YYYYMMDD.log`
- Artifacts: `/home/exedev/miny-ven/scraper/artifacts/`
- Env file: `/home/exedev/miny-ven/scraper/.env`
- Librarium config: `/home/exedev/.config/librarium/config.json`

## Troubleshooting

1. VM unreachable
   - `ssh exedev@y0-minynet.exe.xyz`
   - `MINY_LOCAL_MODE=1 /home/exedev/bin/miny status`

2. No fresh Firestore data
   - `MINY_LOCAL_MODE=1 /home/exedev/bin/miny logs --lines=120`
   - `MINY_LOCAL_MODE=1 /home/exedev/bin/miny run`

3. Cron not active
   - `MINY_LOCAL_MODE=1 /home/exedev/bin/miny cron --enable`
   - verify with `crontab -l`

4. Bad deploy / quick recovery
   - `MINY_LOCAL_MODE=1 /home/exedev/bin/miny rollback`
   - then `MINY_LOCAL_MODE=1 /home/exedev/bin/miny status`
