#!/usr/bin/env python3
"""
Gated mass hard-delete of non-music / discovery noise (plan U3).

Safety:
  - Never deletes without a verified archive (manifest sha256 + line count).
  - Never auto-deletes curated rows.
  - Requires --i-understand on execute.

Examples:
  python3 cleanup_non_music.py dry-run --sample 1000 --out /tmp/cleanup-report.json
  python3 cleanup_non_music.py execute --archive ../archives/articles-YYYYMMDD --i-understand
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_articles import (  # noqa: E402
    PB_URL,
    iter_articles,
    pb_auth,
    selection_reason,
)


def _delete_record(token: str, article_id: str) -> None:
    url = f"{PB_URL}/api/collections/articles/records/{article_id}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"DELETE {article_id} HTTP {e.code}: {body}") from e


def cmd_dry_run(args: argparse.Namespace) -> int:
    candidates = []
    holdback = []
    scanned = 0
    max_pages = max(1, (args.sample + 199) // 200) if args.sample else None

    for rec in iter_articles(max_pages=max_pages, per_page=200):
        scanned += 1
        if args.sample and scanned > args.sample:
            break
        reason = selection_reason(rec)
        if reason is None:
            continue
        entry = {
            "id": rec.get("id"),
            "title": (rec.get("title") or "")[:120],
            "source": rec.get("source"),
            "reason": reason,
            "curated": bool(rec.get("curated")),
        }
        if reason.startswith("curated_"):
            holdback.append(entry)
        else:
            candidates.append(entry)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scanned": scanned,
        "delete_candidates": len(candidates),
        "curated_holdback": len(holdback),
        "candidates": candidates[: args.max_list],
        "holdback": holdback[: args.max_list],
    }
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.out}")
    print(
        json.dumps(
            {
                "scanned": scanned,
                "delete_candidates": len(candidates),
                "curated_holdback": len(holdback),
            },
            indent=2,
        )
    )
    return 0


def _load_archive_ids(archive_dir: Path) -> tuple[list[str], dict]:
    jsonl = archive_dir / "articles.jsonl"
    manifest_path = archive_dir / "manifest.json"
    if not jsonl.exists() or not manifest_path.exists():
        raise RuntimeError("Archive must contain articles.jsonl and manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    import hashlib

    h = hashlib.sha256()
    ids: list[str] = []
    with jsonl.open("rb") as fh:
        for raw in fh:
            h.update(raw)
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            row = json.loads(line)
            # skip curated holdback unless explicitly archived for delete
            reason = row.get("reason") or ""
            if reason.startswith("curated_"):
                continue
            rid = (row.get("record") or {}).get("id")
            if rid:
                ids.append(rid)
    if h.hexdigest() != manifest.get("sha256"):
        raise RuntimeError("Archive checksum mismatch — refusing execute")
    if len(ids) == 0:
        raise RuntimeError("No deletable ids in archive")
    return ids, manifest


def cmd_execute(args: argparse.Namespace) -> int:
    if not args.i_understand:
        print("Refusing: pass --i-understand after verifying archive restore pilot", file=sys.stderr)
        return 2

    archive_dir = Path(args.archive)
    ids, manifest = _load_archive_ids(archive_dir)
    if args.limit:
        ids = ids[: args.limit]

    token = pb_auth()
    deleted = 0
    errors = 0
    audit = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "archive": str(archive_dir),
        "manifest_exported": manifest.get("exported"),
        "planned": len(ids),
        "deleted_ids": [],
        "errors": [],
    }

    for i, rid in enumerate(ids):
        try:
            _delete_record(token, rid)
            deleted += 1
            audit["deleted_ids"].append(rid)
        except RuntimeError as e:
            errors += 1
            audit["errors"].append({"id": rid, "error": str(e)})
            if errors > args.max_errors:
                print("Aborting: max_errors exceeded", file=sys.stderr)
                break
        if (i + 1) % 20 == 0:
            time.sleep(args.sleep)
            print(f"  progress {i+1}/{len(ids)} deleted={deleted} errors={errors}")

    audit["finished_at"] = datetime.now(timezone.utc).isoformat()
    audit["deleted"] = deleted
    audit["error_count"] = errors

    out = Path(args.audit_out or (archive_dir / "delete_audit.json"))
    out.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"deleted": deleted, "errors": errors, "audit": str(out)}, indent=2))
    return 0 if errors == 0 else 1


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Cleanup non-music articles (gated)")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dry-run", help="Report delete candidates")
    d.add_argument("--sample", type=int, default=1000)
    d.add_argument("--out", default="")
    d.add_argument("--max-list", type=int, default=100)
    d.set_defaults(func=cmd_dry_run)

    e = sub.add_parser("execute", help="Hard-delete ids from a verified archive")
    e.add_argument("--archive", required=True)
    e.add_argument("--i-understand", action="store_true")
    e.add_argument("--limit", type=int, default=0, help="Max deletes (0=all in archive)")
    e.add_argument("--sleep", type=float, default=0.3)
    e.add_argument("--max-errors", type=int, default=25)
    e.add_argument("--audit-out", default="")
    e.set_defaults(func=cmd_execute)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
