#!/usr/bin/env python3
"""
miny-ven scraper management CLI.

Commands:
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
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

from cryptography.fernet import Fernet


APP_DIR = Path.home() / ".minyven-cli"
CONFIG_PATH = APP_DIR / "config.toml"
SECRETS_PATH = APP_DIR / "secrets.enc"
KEY_PATH = APP_DIR / "key.bin"
CACHE_DIR = APP_DIR / "cache"
STATUS_CACHE_PATH = CACHE_DIR / "status.json"
BACKUP_DIR = APP_DIR / "backups"

RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
BLUE = "\033[34m"
BOLD = "\033[1m"
RESET = "\033[0m"

DEFAULT_CONFIG: Dict[str, Any] = {
    "vm": {
        "host": "y0-minynet.exe.xyz",
        "user": "exedev",
        "port": 22,
        "remote_base": "~/miny-ven",
    },
    "paths": {
        "scraper": "~/miny-ven/scraper",
        "logs": "~/miny-ven/logs",
        "artifacts": "~/miny-ven/scraper/artifacts",
        "remote_env": "~/miny-ven/scraper/.env",
        "librarium_config": "~/.config/librarium/config.json",
        "backups": "~/miny-ven/backups",
    },
    "firestore": {
        "project_id": "miny-ven",
        "stale_after_hours": 3,
    },
    "monitoring": {
        "exa_daily_quota": 10,
        "perplexity_per_min_quota": 20,
        "brave_daily_quota": 2000,
    },
    "notifications": {
        "slack_webhook": "",
        "telegram_webhook": "",
    },
    "cron": {
        "line": "",
        "marker": "miny run",
    },
}

SENSITIVE_KEYS = {
    "FIREBASE_API_KEY",
    "PERPLEXITY_API_KEY",
    "DEEPSEEK_API_KEY",
    "EXA_API_KEY",
    "BRAVE_API_KEY",
    "GEMINI_API_KEY",
    "FIREBASE_SERVICE_ACCOUNT_B64",
}

ENV_TO_CONFIG = {
    "MINY_VM_HOST": ("vm", "host"),
    "MINY_VM_USER": ("vm", "user"),
    "MINY_VM_PORT": ("vm", "port"),
    "MINY_FIRESTORE_PROJECT": ("firestore", "project_id"),
    "MINY_FIRESTORE_STALE_HOURS": ("firestore", "stale_after_hours"),
    "MINY_SLACK_WEBHOOK": ("notifications", "slack_webhook"),
    "MINY_TELEGRAM_WEBHOOK": ("notifications", "telegram_webhook"),
}


@dataclass
class CommandResult:
    code: int
    stdout: str
    stderr: str


def ensure_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def deep_copy_default() -> Dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_CONFIG))


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], val)
        else:
            base[key] = val
    return base


def load_config() -> Dict[str, Any]:
    cfg = deep_copy_default()
    if CONFIG_PATH.exists() and tomllib is not None:
        with CONFIG_PATH.open("rb") as fh:
            loaded = tomllib.load(fh)
        deep_merge(cfg, loaded)

    for env_key, config_path in ENV_TO_CONFIG.items():
        env_val = os.getenv(env_key)
        if env_val is None:
            continue
        section, key = config_path
        if isinstance(cfg[section].get(key), int):
            try:
                cfg[section][key] = int(env_val)
            except ValueError:
                pass
        else:
            cfg[section][key] = env_val

    return cfg


def format_toml(cfg: Dict[str, Any]) -> str:
    lines = ["# miny-ven scraper CLI config", ""]
    for section in ["vm", "paths", "firestore", "monitoring", "notifications", "cron"]:
        lines.append(f"[{section}]")
        for key, value in cfg.get(section, {}).items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, int):
                rendered = str(value)
            else:
                escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
                rendered = f'"{escaped}"'
            lines.append(f"{key} = {rendered}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_config(cfg: Dict[str, Any]) -> None:
    ensure_dirs()
    CONFIG_PATH.write_text(format_toml(cfg), encoding="utf-8")


def _get_key() -> bytes:
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    ensure_dirs()
    KEY_PATH.write_bytes(key)
    try:
        os.chmod(KEY_PATH, 0o600)
    except OSError:
        pass
    return key


def load_secrets() -> Dict[str, str]:
    if not SECRETS_PATH.exists():
        return {}
    fernet = Fernet(_get_key())
    raw = fernet.decrypt(SECRETS_PATH.read_bytes())
    return json.loads(raw.decode("utf-8"))


def save_secrets(secrets: Dict[str, str]) -> None:
    ensure_dirs()
    fernet = Fernet(_get_key())
    raw = json.dumps(secrets, sort_keys=True).encode("utf-8")
    enc = fernet.encrypt(raw)
    SECRETS_PATH.write_bytes(enc)
    try:
        os.chmod(SECRETS_PATH, 0o600)
    except OSError:
        pass


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def color_line(line: str) -> str:
    lower = line.lower()
    if any(token in lower for token in ["error", "traceback", "failed", "✗"]):
        return f"{RED}{line}{RESET}"
    if any(token in lower for token in ["warn", "warning", "⚠"]):
        return f"{YELLOW}{line}{RESET}"
    if any(token in lower for token in ["ok", "complete", "success", "✓"]):
        return f"{GREEN}{line}{RESET}"
    return line


def remote_target(cfg: Dict[str, Any]) -> str:
    return f"{cfg['vm']['user']}@{cfg['vm']['host']}"


def remote_norm(path_value: str, cfg: Optional[Dict[str, Any]] = None) -> str:
    vm_user = "exedev"
    if cfg:
        vm_user = str(cfg.get("vm", {}).get("user", vm_user))
    if path_value.startswith("~/"):
        return f"/home/{vm_user}/" + path_value[2:]
    return path_value


def build_cron_line(cfg: Dict[str, Any]) -> str:
    if cfg.get("cron", {}).get("line"):
        return str(cfg["cron"]["line"])
    vm_user = str(cfg.get("vm", {}).get("user", "exedev"))
    return (
        "5 * * * * /usr/bin/flock -n "
        f"/home/{vm_user}/miny-ven/scraper/.rss_scraper.lock "
        f"/bin/bash -lc 'MINY_LOCAL_MODE=1 /home/{vm_user}/bin/miny run'"
    )


def is_local_mode() -> bool:
    return os.getenv("MINY_LOCAL_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def run_cmd(
    args: list[str], capture: bool = True, check: bool = False
) -> CommandResult:
    proc = subprocess.run(args, capture_output=capture, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "command failed")
    return CommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")


def run_ssh(cfg: Dict[str, Any], command: str, check: bool = False) -> CommandResult:
    if is_local_mode():
        return run_cmd(["bash", "-lc", command], capture=True, check=check)
    port = str(cfg["vm"]["port"])
    args = [
        "ssh",
        "-p",
        port,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=12",
        remote_target(cfg),
        f"bash -lc {shlex.quote(command)}",
    ]
    return run_cmd(args, capture=True, check=check)


def run_ssh_stream(cfg: Dict[str, Any], command: str) -> int:
    if is_local_mode():
        proc = subprocess.Popen(
            ["bash", "-lc", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(color_line(line.rstrip("\n")))
        return proc.wait()
    port = str(cfg["vm"]["port"])
    args = [
        "ssh",
        "-p",
        port,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=12",
        remote_target(cfg),
        f"bash -lc {shlex.quote(command)}",
    ]
    proc = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(color_line(line.rstrip("\n")))
    return proc.wait()


def run_rsync(
    cfg: Dict[str, Any], local: Path, remote: str, extra: Optional[list[str]] = None
) -> CommandResult:
    port = str(cfg["vm"]["port"])
    args = ["rsync", "-az", "--delete"]
    if extra:
        args.extend(extra)
    args.extend(
        [
            "-e",
            f"ssh -p {port}",
            f"{str(local).rstrip('/')}/",
            f"{remote_target(cfg)}:{remote}",
        ]
    )
    return run_cmd(args, capture=True)


def run_scp(cfg: Dict[str, Any], local: Path, remote: str) -> CommandResult:
    port = str(cfg["vm"]["port"])
    args = ["scp", "-P", port, str(local), f"{remote_target(cfg)}:{remote}"]
    return run_cmd(args, capture=True)


def parse_period(value: str) -> timedelta:
    m = re.fullmatch(r"(\d+)([smhd])", value.strip().lower())
    if not m:
        raise ValueError("Invalid period. Use forms like 30m, 12h, 7d")
    qty = int(m.group(1))
    unit = m.group(2)
    if unit == "s":
        return timedelta(seconds=qty)
    if unit == "m":
        return timedelta(minutes=qty)
    if unit == "h":
        return timedelta(hours=qty)
    return timedelta(days=qty)


def cache_status(payload: Dict[str, Any]) -> None:
    ensure_dirs()
    STATUS_CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_cached_status() -> Optional[Dict[str, Any]]:
    if not STATUS_CACHE_PATH.exists():
        return None
    try:
        return json.loads(STATUS_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def fire_latest_timestamp(
    cfg: Dict[str, Any], firebase_api_key: str
) -> Tuple[Optional[datetime], str]:
    project_id = cfg["firestore"]["project_id"]
    url = (
        f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/"
        f"documents:runQuery?key={firebase_api_key}"
    )
    query = {
        "structuredQuery": {
            "from": [{"collectionId": "articles"}],
            "orderBy": [
                {"field": {"fieldPath": "fetched_at"}, "direction": "DESCENDING"}
            ],
            "limit": 1,
            "select": {"fields": [{"fieldPath": "fetched_at"}, {"fieldPath": "title"}]},
        }
    }
    data = json.dumps(query).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "minyven-cli/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return None, f"Firestore HTTP {exc.code}: {detail[:180]}"
    except Exception as exc:
        return None, f"Firestore error: {exc}"

    for row in payload:
        doc = row.get("document")
        if not doc:
            continue
        ts = doc.get("fields", {}).get("fetched_at", {}).get("stringValue")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt, "ok"
        except ValueError:
            continue
    return None, "No fetched_at timestamp returned"


def get_remote_env_value(cfg: Dict[str, Any], key: str) -> Optional[str]:
    env_path = remote_norm(cfg["paths"]["remote_env"], cfg)
    cmd = f"test -f {shlex.quote(env_path)} && grep -E '^{re.escape(key)}=' {shlex.quote(env_path)} || true"
    res = run_ssh(cfg, cmd)
    if res.code != 0:
        return None
    line = res.stdout.strip()
    if "=" not in line:
        return None
    return line.split("=", 1)[1]


def best_firebase_api_key(
    cfg: Dict[str, Any], secrets: Dict[str, str]
) -> Optional[str]:
    return (
        os.getenv("FIREBASE_API_KEY")
        or secrets.get("FIREBASE_API_KEY")
        or get_remote_env_value(cfg, "FIREBASE_API_KEY")
    )


def snapshot_remote_configs(cfg: Dict[str, Any]) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = BACKUP_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    env_path = remote_norm(cfg["paths"]["remote_env"], cfg)
    lib_path = remote_norm(cfg["paths"]["librarium_config"], cfg)

    env_res = run_ssh(
        cfg, f"test -f {shlex.quote(env_path)} && cat {shlex.quote(env_path)} || true"
    )
    if env_res.stdout.strip():
        (out_dir / "remote.env").write_text(env_res.stdout, encoding="utf-8")

    lib_res = run_ssh(
        cfg, f"test -f {shlex.quote(lib_path)} && cat {shlex.quote(lib_path)} || true"
    )
    if lib_res.stdout.strip():
        (out_dir / "librarium-config.json").write_text(lib_res.stdout, encoding="utf-8")

    if not any(out_dir.iterdir()):
        out_dir.rmdir()
        return

    git_dir = BACKUP_DIR
    if not (git_dir / ".git").exists():
        run_cmd(["git", "-C", str(git_dir), "init"], capture=True)
    run_cmd(["git", "-C", str(git_dir), "add", "."], capture=True)
    run_cmd(
        ["git", "-C", str(git_dir), "commit", "-m", f"backup: {ts}"],
        capture=True,
    )


def print_status_payload(payload: Dict[str, Any]) -> None:
    vm_ok = payload.get("vm_ok", False)
    cron_ok = payload.get("cron_ok", False)
    fire = payload.get("firestore", {})
    age_hours = fire.get("age_hours")
    stale = fire.get("stale")

    vm_label = f"{GREEN}OK{RESET}" if vm_ok else f"{RED}DOWN{RESET}"
    cron_label = f"{GREEN}ACTIVE{RESET}" if cron_ok else f"{RED}MISSING{RESET}"
    fire_label = "unknown"
    if age_hours is not None:
        color = RED if stale else GREEN
        fire_label = f"{color}{age_hours:.2f}h{RESET}"

    print(f"VM:        {vm_label} ({payload.get('vm_host')})")
    print(f"Cron:      {cron_label}")
    print(f"Firestore: {fire_label}")
    if fire.get("latest"):
        print(f"Latest:    {fire['latest']}")
    if payload.get("disk"):
        print(f"Disk:      {payload['disk']}")
    if payload.get("memory"):
        print(f"Memory:    {payload['memory']}")
    if fire.get("detail") and fire.get("status") != "ok":
        print(f"Detail:    {fire['detail']}")


def send_notification(url: str, message: str) -> None:
    body = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15):
        return


def cmd_run(cfg: Dict[str, Any], args: argparse.Namespace) -> int:
    if args.dry_run:
        return cmd_test(cfg, args)
    log_dir = remote_norm(cfg["paths"]["logs"], cfg)
    scraper_dir = remote_norm(cfg["paths"]["scraper"], cfg)
    command = (
        f"mkdir -p {shlex.quote(log_dir)} && "
        f"cd {shlex.quote(scraper_dir)} && "
        "python3 rss_scraper.py 2>&1 | tee -a "
        f"{shlex.quote(log_dir)}/rss-$(date +%Y%m%d).log"
    )
    print(f"{BOLD}Triggering scraper run...{RESET}")
    return run_ssh_stream(cfg, command)


def _find_latest_log_file(cfg: Dict[str, Any]) -> Optional[str]:
    log_dir = remote_norm(cfg["paths"]["logs"], cfg)
    res = run_ssh(
        cfg, f"ls -1t {shlex.quote(log_dir)}/rss-*.log 2>/dev/null | head -n 1"
    )
    if res.code != 0:
        return None
    value = res.stdout.strip()
    return value or None


def cmd_logs(cfg: Dict[str, Any], args: argparse.Namespace) -> int:
    latest = _find_latest_log_file(cfg)
    if not latest:
        print("No log files found on VM.")
        return 1

    if args.follow:
        print(f"Following: {latest}")
        return run_ssh_stream(cfg, f"tail -n {args.lines} -F {shlex.quote(latest)}")

    res = run_ssh(cfg, f"tail -n {args.lines} {shlex.quote(latest)}")
    if res.code != 0:
        print(res.stderr.strip() or "Unable to read logs")
        return res.code
    for line in res.stdout.splitlines():
        print(color_line(line))
    return 0


def collect_status(cfg: Dict[str, Any], secrets: Dict[str, str]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "vm_host": cfg["vm"]["host"],
        "vm_ok": False,
        "cron_ok": False,
        "disk": "",
        "memory": "",
        "firestore": {
            "status": "unknown",
            "latest": None,
            "age_hours": None,
            "stale": None,
            "detail": "",
        },
    }

    ping = run_ssh(cfg, "echo vm-ok")
    payload["vm_ok"] = ping.code == 0 and "vm-ok" in ping.stdout

    if payload["vm_ok"]:
        marker = cfg["cron"]["marker"]
        cron_res = run_ssh(
            cfg,
            f"crontab -l 2>/dev/null | grep -v '^#' | grep -q {shlex.quote(marker)}",
        )
        payload["cron_ok"] = cron_res.code == 0

        disk_res = run_ssh(cfg, "df -h / | tail -n 1")
        if disk_res.code == 0:
            payload["disk"] = " ".join(disk_res.stdout.split())

        mem_res = run_ssh(
            cfg,
            "if command -v free >/dev/null 2>&1; then free -m | sed -n '2p'; else vm_stat; fi",
        )
        if mem_res.code == 0:
            payload["memory"] = " ".join(mem_res.stdout.split())[:220]

    api_key = best_firebase_api_key(cfg, secrets)
    if not api_key:
        payload["firestore"]["status"] = "missing_key"
        payload["firestore"]["detail"] = (
            "No FIREBASE_API_KEY available locally or on VM"
        )
    else:
        latest, detail = fire_latest_timestamp(cfg, api_key)
        if latest is None:
            payload["firestore"]["status"] = "error"
            payload["firestore"]["detail"] = detail
        else:
            now = datetime.now(timezone.utc)
            age = now - latest
            age_hours = age.total_seconds() / 3600.0
            stale_after = float(cfg["firestore"]["stale_after_hours"])
            payload["firestore"]["status"] = "ok"
            payload["firestore"]["latest"] = latest.isoformat()
            payload["firestore"]["age_hours"] = age_hours
            payload["firestore"]["stale"] = age_hours > stale_after
            payload["firestore"]["detail"] = "ok"

    return payload


def cmd_status(cfg: Dict[str, Any], args: argparse.Namespace) -> int:
    secrets = load_secrets()

    while True:
        payload = collect_status(cfg, secrets)
        if payload.get("vm_ok"):
            cache_status(payload)
            print_status_payload(payload)
        else:
            cached = read_cached_status()
            print(f"{RED}VM unreachable{RESET}: {cfg['vm']['host']}")
            if cached:
                print(f"Using cached status from {cached.get('checked_at')}")
                print_status_payload(cached)
            else:
                print("No cached status available.")

        fire = payload.get("firestore", {})
        should_alert = fire.get("stale") is True
        if should_alert:
            for channel_key in ["slack_webhook", "telegram_webhook"]:
                url = cfg.get("notifications", {}).get(channel_key)
                if not url:
                    continue
                try:
                    send_notification(
                        url,
                        f"miny-ven alert: Firestore freshness is stale ({fire.get('age_hours', 0):.2f}h old)",
                    )
                    print(f"Sent alert via {channel_key}")
                except Exception as exc:
                    print(f"Alert send failed ({channel_key}): {exc}")

        if not args.watch:
            return 0 if payload.get("vm_ok") else 1
        print("-" * 60)
        time.sleep(30)


def parse_key_val(raw: str) -> Tuple[str, str]:
    if "=" not in raw:
        raise ValueError("Use KEY=VALUE format")
    k, v = raw.split("=", 1)
    k = k.strip()
    if not k:
        raise ValueError("Missing key name")
    return k, v.strip()


def merge_env_text(existing: str, updates: Dict[str, str]) -> str:
    lines = existing.splitlines()
    seen = set()
    out = []
    for line in lines:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if not m:
            out.append(line)
            continue
        key = m.group(1)
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    return "\n".join(out).rstrip() + "\n"


def put_remote_file(cfg: Dict[str, Any], remote_path: str, text: str) -> None:
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    try:
        remote_path = remote_norm(remote_path, cfg)
        mkdir_cmd = f"mkdir -p {shlex.quote(str(Path(remote_path).parent))}"
        run_ssh(cfg, mkdir_cmd)
        res = run_scp(cfg, tmp_path, remote_path)
        if res.code != 0:
            raise RuntimeError(res.stderr.strip() or "scp failed")
    finally:
        tmp_path.unlink(missing_ok=True)


def cmd_config(cfg: Dict[str, Any], args: argparse.Namespace) -> int:
    secrets = load_secrets()
    changed = False

    if args.set_items:
        for item in args.set_items:
            key, val = parse_key_val(item)
            if val == "" and not os.getenv("CI"):
                val = getpass.getpass(f"Enter value for {key}: ")

            if key in SENSITIVE_KEYS:
                secrets[key] = val
                save_secrets(secrets)
            elif key == "FIREBASE_PROJECT_ID":
                cfg["firestore"]["project_id"] = val
                save_config(cfg)
            elif key == "MINY_VM_HOST":
                cfg["vm"]["host"] = val
                save_config(cfg)
            elif key == "MINY_VM_USER":
                cfg["vm"]["user"] = val
                save_config(cfg)
            else:
                cfg.setdefault("custom", {})[key] = val
                save_config(cfg)
            changed = True
            print(f"Set {key}")

        # Update remote .env as part of secrets management
        remote_env = remote_norm(cfg["paths"]["remote_env"], cfg)
        res = run_ssh(
            cfg,
            f"test -f {shlex.quote(remote_env)} && cat {shlex.quote(remote_env)} || true",
        )
        existing = res.stdout if res.code == 0 else ""
        updates = {k: v for k, v in secrets.items() if k in SENSITIVE_KEYS}
        updates["FIREBASE_PROJECT_ID"] = cfg["firestore"]["project_id"]
        merged = merge_env_text(existing, updates)
        put_remote_file(cfg, remote_env, merged)
        print(f"Updated remote env: {remote_env}")

    if args.show or not changed:
        print(f"Config: {CONFIG_PATH}")
        print(f"VM: {cfg['vm']['user']}@{cfg['vm']['host']}:{cfg['vm']['port']}")
        print(f"Firestore project: {cfg['firestore']['project_id']}")
        print("Stored secrets:")
        for key in sorted(secrets.keys()):
            print(f"  {key}={mask_secret(secrets[key])}")
        if not secrets:
            print("  (none)")

    return 0


def deploy_code(cfg: Dict[str, Any]) -> int:
    local_scraper = Path(__file__).resolve().parent
    remote_scraper = cfg["paths"]["scraper"]
    backups = remote_norm(cfg["paths"]["backups"], cfg)

    backup_cmd = (
        f"mkdir -p {shlex.quote(backups)} && "
        "ts=$(date +%Y%m%dT%H%M%S) && "
        f"tar -czf {shlex.quote(backups)}/scraper-$ts.tar.gz -C ~/miny-ven scraper >/dev/null 2>&1 && "
        f"echo $ts > {shlex.quote(backups)}/latest-good.txt"
    )
    run_ssh(cfg, backup_cmd)

    excludes = [
        "--exclude",
        ".env",
        "--exclude",
        "__pycache__",
        "--exclude",
        "artifacts",
        "--exclude",
        ".pytest_cache",
        "--exclude",
        "tests/__pycache__",
    ]
    res = run_rsync(cfg, local_scraper, remote_scraper, excludes)
    if res.code != 0:
        print(res.stderr.strip() or "rsync failed")
        return res.code
    print("Code deployed via rsync.")
    return 0


def deploy_config(cfg: Dict[str, Any]) -> int:
    snapshot_remote_configs(cfg)
    secrets = load_secrets()
    remote_env = remote_norm(cfg["paths"]["remote_env"], cfg)
    env_res = run_ssh(
        cfg,
        f"test -f {shlex.quote(remote_env)} && cat {shlex.quote(remote_env)} || true",
    )
    existing = env_res.stdout if env_res.code == 0 else ""

    updates = {k: v for k, v in secrets.items() if k in SENSITIVE_KEYS}
    updates["FIREBASE_PROJECT_ID"] = cfg["firestore"]["project_id"]
    merged = merge_env_text(existing, updates)
    put_remote_file(cfg, remote_env, merged)
    print(f"Deployed remote env: {remote_env}")

    local_lib = Path.home() / ".config/librarium/config.json"
    if local_lib.exists():
        remote_lib = remote_norm(cfg["paths"]["librarium_config"], cfg)
        run_ssh(cfg, f"mkdir -p {shlex.quote(str(Path(remote_lib).parent))}")
        scp_res = run_scp(cfg, local_lib, remote_lib)
        if scp_res.code != 0:
            print(f"Librarium config deploy failed: {scp_res.stderr.strip()}")
            return scp_res.code
        print(f"Deployed librarium config: {remote_lib}")
    else:
        print("Local librarium config missing; skipped.")

    return 0


def cmd_deploy(cfg: Dict[str, Any], args: argparse.Namespace) -> int:
    mode_code = args.code
    mode_config = args.config
    mode_all = args.all
    if not (mode_code or mode_config or mode_all):
        mode_all = True

    rc = 0
    if mode_code or mode_all:
        rc = deploy_code(cfg)
        if rc != 0:
            return rc
    if mode_config or mode_all:
        rc = deploy_config(cfg)
        if rc != 0:
            return rc
    return rc


def cmd_test(cfg: Dict[str, Any], _args: argparse.Namespace) -> int:
    scraper_dir = remote_norm(cfg["paths"]["scraper"], cfg)
    command = (
        f"cd {shlex.quote(scraper_dir)} && "
        "python3 - <<'PY'\n"
        "import rss_scraper\n"
        "scraper = rss_scraper.RSSScraper()\n"
        "scraper.save_to_firebase = lambda article: True\n"
        "scraper.archive_stale_articles = lambda: 0\n"
        "scraper.run()\n"
        "print('SMOKE_TEST_OK')\n"
        "PY"
    )
    print(f"{BOLD}Running smoke test (no Firestore writes)...{RESET}")
    return run_ssh_stream(cfg, command)


def cmd_rollback(cfg: Dict[str, Any], _args: argparse.Namespace) -> int:
    backups = remote_norm(cfg["paths"]["backups"], cfg)
    command = (
        "set -e; "
        f"latest=$(ls -1t {shlex.quote(backups)}/scraper-*.tar.gz 2>/dev/null | head -n 1); "
        "if [ -z \"$latest\" ]; then echo 'No backup found'; exit 1; fi; "
        "tmp_env=$(mktemp); "
        "if [ -f ~/miny-ven/scraper/.env ]; then cp ~/miny-ven/scraper/.env $tmp_env; fi; "
        'tar -xzf "$latest" -C ~/miny-ven; '
        "if [ -f $tmp_env ]; then mv $tmp_env ~/miny-ven/scraper/.env; fi; "
        "echo Rolled back using $latest"
    )
    res = run_ssh(cfg, command)
    if res.code != 0:
        print(res.stderr.strip() or res.stdout.strip() or "Rollback failed")
        return res.code
    print(res.stdout.strip())
    return 0


def cmd_metrics(cfg: Dict[str, Any], args: argparse.Namespace) -> int:
    delta = parse_period(args.period)
    since_epoch = int((datetime.now(timezone.utc) - delta).timestamp())
    artifacts = remote_norm(cfg["paths"]["artifacts"], cfg)
    monitor = cfg["monitoring"]

    py = (
        "import json, os, glob\n"
        f"since={since_epoch}\n"
        f"art_dir={json.dumps(artifacts)}\n"
        "summaries=glob.glob(os.path.join(os.path.expanduser(art_dir),'summary_*.json'))\n"
        "events=glob.glob(os.path.join(os.path.expanduser(art_dir),'events_*.jsonl'))\n"
        "run_count=0\n"
        "articles=0\n"
        "fetched=0\n"
        "errors=0\n"
        "exa_items=0\n"
        "librarium_items=0\n"
        "for p in summaries:\n"
        "  if int(os.path.getmtime(p)) < since: continue\n"
        "  try:\n"
        "    d=json.load(open(p))\n"
        "  except Exception:\n"
        "    continue\n"
        "  run_count += 1\n"
        "  articles += int(d.get('total_processed',0) or 0)\n"
        "  fetched += int(d.get('total_fetched_items',0) or 0)\n"
        "  ss=d.get('source_stats',{})\n"
        "  exa_items += int((ss.get('exa_discovery') or {}).get('items_found',0) or 0)\n"
        "  librarium_items += int((ss.get('librarium_discovery') or {}).get('items_found',0) or 0)\n"
        "for p in events:\n"
        "  if int(os.path.getmtime(p)) < since: continue\n"
        "  try:\n"
        "    with open(p) as fh:\n"
        "      for line in fh:\n"
        "        line=line.strip()\n"
        "        if not line: continue\n"
        "        try:\n"
        "          e=json.loads(line)\n"
        "        except Exception:\n"
        "          continue\n"
        "        if str(e.get('level','')).lower()=='error':\n"
        "          errors += 1\n"
        "  except Exception:\n"
        "    pass\n"
        "print(json.dumps({'runs':run_count,'articles':articles,'fetched':fetched,'errors':errors,'exa_items':exa_items,'librarium_items':librarium_items}))\n"
    )

    res = run_ssh(cfg, f"python3 - <<'PY'\n{py}PY")
    if res.code != 0:
        print(res.stderr.strip() or "Failed to fetch metrics")
        return res.code
    try:
        data = json.loads(res.stdout.strip() or "{}")
    except json.JSONDecodeError:
        print("Failed to parse metrics output")
        return 1

    runs = int(data.get("runs", 0))
    articles = int(data.get("articles", 0))
    errors = int(data.get("errors", 0))
    days = max(delta.total_seconds() / 86400.0, 1 / 24)

    exa_calls_est = runs
    brave_calls_est = runs * 5
    perplexity_calls_est = max(articles, runs)

    exa_quota = float(monitor["exa_daily_quota"]) * days
    brave_quota = float(monitor["brave_daily_quota"]) * days
    perplexity_quota = float(monitor["perplexity_per_min_quota"]) * 60.0 * 24.0 * days

    print(f"Period: {args.period}")
    print(f"Runs: {runs}")
    print(f"Articles added: {articles}")
    print(f"Errors: {errors}")
    print("API usage (estimated):")
    print(
        f"  Exa:        {exa_calls_est}/{exa_quota:.1f} ({(exa_calls_est / exa_quota * 100) if exa_quota else 0:.1f}%)"
    )
    print(
        f"  Brave:      {brave_calls_est}/{brave_quota:.1f} ({(brave_calls_est / brave_quota * 100) if brave_quota else 0:.2f}%)"
    )
    print(
        f"  Perplexity: {perplexity_calls_est}/{perplexity_quota:.1f} "
        f"({(perplexity_calls_est / perplexity_quota * 100) if perplexity_quota else 0:.4f}%)"
    )
    return 0


def cmd_cron(cfg: Dict[str, Any], args: argparse.Namespace) -> int:
    marker = cfg["cron"]["marker"]
    cron_line = build_cron_line(cfg)

    if args.disable:
        command = f"(crontab -l 2>/dev/null | grep -v {shlex.quote(marker)} || true) | crontab -"
        res = run_ssh(cfg, command)
        if res.code != 0:
            print(res.stderr.strip() or "Failed to disable cron")
            return res.code
        print("Cron disabled.")
        return 0

    if args.enable:
        command = (
            f"(crontab -l 2>/dev/null | grep -v {shlex.quote(marker)} || true; "
            f"printf '%s\n' {shlex.quote(cron_line)}) | crontab -"
        )
        res = run_ssh(cfg, command)
        if res.code != 0:
            print(res.stderr.strip() or "Failed to enable cron")
            return res.code
        print("Cron enabled.")
        return 0

    res = run_ssh(cfg, "crontab -l 2>/dev/null || true")
    if res.code != 0:
        print(res.stderr.strip() or "Unable to list cron")
        return res.code
    text = res.stdout.strip() or "(empty)"
    print(text)
    return 0


def cmd_alert(cfg: Dict[str, Any], args: argparse.Namespace) -> int:
    url = args.url
    if args.slack:
        cfg["notifications"]["slack_webhook"] = url
        save_config(cfg)
        channel = "slack"
    elif args.telegram:
        cfg["notifications"]["telegram_webhook"] = url
        save_config(cfg)
        channel = "telegram"
    else:
        print("Choose --slack or --telegram")
        return 1

    try:
        send_notification(url, "miny-ven alert channel configured")
        print(f"{channel} alert configured and test message sent.")
        return 0
    except Exception as exc:
        print(f"Alert configuration saved, but test send failed: {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="miny", description="miny-ven scraper management CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Trigger scraper now")
    p_run.add_argument("--dry-run", action="store_true", help="Run smoke test mode")
    p_run.set_defaults(func=cmd_run)

    p_logs = sub.add_parser("logs", help="Tail latest logs")
    p_logs.add_argument(
        "--follow", action="store_true", help="Follow logs in real-time"
    )
    p_logs.add_argument("--lines", type=int, default=50, help="How many lines to show")
    p_logs.set_defaults(func=cmd_logs)

    p_status = sub.add_parser("status", help="Health check")
    p_status.add_argument(
        "--watch", action="store_true", help="Refresh status continuously"
    )
    p_status.set_defaults(func=cmd_status)

    p_config = sub.add_parser("config", help="View/update secrets and settings")
    p_config.add_argument("--show", action="store_true", help="Show current config")
    p_config.add_argument(
        "--set", dest="set_items", action="append", help="Set KEY=VALUE"
    )
    p_config.set_defaults(func=cmd_config)

    p_deploy = sub.add_parser("deploy", help="Deploy code/config to VM")
    p_deploy.add_argument("--code", action="store_true", help="Deploy scraper code")
    p_deploy.add_argument(
        "--config", action="store_true", help="Deploy env + librarium config"
    )
    p_deploy.add_argument(
        "--all", action="store_true", help="Deploy both code and config"
    )
    p_deploy.set_defaults(func=cmd_deploy)

    p_test = sub.add_parser("test", help="Run smoke test without Firestore writes")
    p_test.set_defaults(func=cmd_test)

    p_rollback = sub.add_parser("rollback", help="Rollback to last known good backup")
    p_rollback.set_defaults(func=cmd_rollback)

    p_metrics = sub.add_parser("metrics", help="Show scraper metrics")
    p_metrics.add_argument(
        "--period", default="24h", help="Time window, e.g. 12h, 24h, 7d"
    )
    p_metrics.set_defaults(func=cmd_metrics)

    p_cron = sub.add_parser("cron", help="Manage cron job")
    p_cron.add_argument("--list", action="store_true", help="List cron entries")
    p_cron.add_argument("--disable", action="store_true", help="Disable scraper cron")
    p_cron.add_argument("--enable", action="store_true", help="Enable scraper cron")
    p_cron.set_defaults(func=cmd_cron)

    p_alert = sub.add_parser("alert", help="Configure alert webhook")
    p_alert.add_argument(
        "--slack", action="store_true", help="Store URL as Slack webhook"
    )
    p_alert.add_argument(
        "--telegram", action="store_true", help="Store URL as Telegram webhook"
    )
    p_alert.add_argument("url", help="Webhook URL")
    p_alert.set_defaults(func=cmd_alert)

    return parser


def main() -> int:
    ensure_dirs()
    cfg = load_config()
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(cfg, args))
    except ValueError as exc:
        print(f"Error: {exc}")
        return 2
    except KeyboardInterrupt:
        print("Interrupted")
        return 130
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
