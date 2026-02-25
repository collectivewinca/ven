# miny Scraper Management CLI

CLI for running and operating the remote miny-ven scraper on `y0-minynet.exe.xyz`.

## Quick Start

From `miny-ven/`:

```bash
chmod +x scraper/miny
./scraper/miny --help
```

Optional global alias:

```bash
ln -sf "$PWD/scraper/miny" "$HOME/bin/miny"
```

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

## Notes

- Runtime config is stored in `~/.minyven-cli/config.toml`.
- Encrypted secret values are stored in `~/.minyven-cli/secrets.enc`.
- Remote snapshots of `.env` and `librarium` config are stored in `~/.minyven-cli/backups/`.
- `miny test` and `miny run --dry-run` execute scraper logic without saving to Firestore.
- `miny status` alerts if Firestore freshness exceeds configured threshold (default `3h`).
