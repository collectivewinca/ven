#!/usr/bin/env python3
"""
Archive export + restore pilot for PB articles (plan U2).

Examples:
  # Dry-run: classify and print counts (public PB read)
  python3 archive_articles.py report --sample 500

  # Export deletable non-music / discovery noise to JSONL + manifest
  python3 archive_articles.py export --out ../archives/articles-dryrun --limit 200

  # Full export of all classifier-selected rows (may take a while)
  python3 archive_articles.py export --out ../archives/articles-$(date +%Y%m%d) --all

  # Restore pilot into a staging collection (requires admin env)
  python3 archive_articles.py restore-pilot --archive ../archives/articles-dryrun \\
      --collection articles_restore_pilot

Env:
  ARTICLES_PB_URL              default https://miny-database.exe.xyz
  ARTICLES_PB_ADMIN_EMAIL      superuser identity (restore/delete)
  ARTICLES_PB_ADMIN_PASSWORD   superuser password
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# Local imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
from music_classifier import classify, is_deletable_non_music  # noqa: E402

PB_URL = os.getenv("ARTICLES_PB_URL", "https://miny-database.exe.xyz").rstrip("/")
PB_EMAIL = os.getenv("ARTICLES_PB_ADMIN_EMAIL", "")
PB_PASSWORD = os.getenv("ARTICLES_PB_ADMIN_PASSWORD", "")

# Full record for restore fidelity
EXPORT_FIELDS = (
    "id,title,summary,source,source_url,primary_genre,secondary_genres,"
    "artist_names,image_url,image_source,published_at,read_time,share_count,"
    "email_count,bookmark_count,view_count,location,curated,curator,curated_at,"
    "full_content,fetched_at,entity_rc_url,epk_url,epk_status,firebase_id"
)


def _http_json(
    url: str,
    *,
    method: str = "GET",
    token: Optional[str] = None,
    body: Optional[dict] = None,
    timeout: int = 60,
) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {e.code} {url}: {err_body}") from e


def pb_auth() -> str:
    if not PB_EMAIL or not PB_PASSWORD:
        raise RuntimeError(
            "Set ARTICLES_PB_ADMIN_EMAIL and ARTICLES_PB_ADMIN_PASSWORD for auth"
        )
    data = json.dumps({"identity": PB_EMAIL, "password": PB_PASSWORD}).encode()
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/_superusers/auth-with-password",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["token"]


def iter_articles(
    *,
    per_page: int = 200,
    max_pages: Optional[int] = None,
    fields: str = EXPORT_FIELDS,
    token: Optional[str] = None,
    filter_str: str = "",
) -> Iterable[dict]:
    """Yield article records. Public list works without token when rules allow."""
    page = 1
    while True:
        params = {
            "perPage": str(per_page),
            "page": str(page),
            "sort": "-published_at",
            "fields": fields,
        }
        if filter_str:
            params["filter"] = filter_str
        qs = urllib.parse.urlencode(params)
        url = f"{PB_URL}/api/collections/articles/records?{qs}"
        data = _http_json(url, token=token)
        items = data.get("items") or []
        for it in items:
            yield it
        total_pages = int(data.get("totalPages") or 1)
        if page >= total_pages or not items:
            break
        if max_pages is not None and page >= max_pages:
            break
        page += 1
        time.sleep(0.05)


def selection_reason(rec: dict) -> Optional[str]:
    """Return reason string if row should be archived/deleted candidates, else None."""
    curated = bool(rec.get("curated"))
    title = rec.get("title") or ""
    summary = rec.get("summary") or ""
    source = rec.get("source") or ""

    if curated:
        label = classify(title, summary, source, mode="delete")
        if label == "non_music":
            return "curated_holdback_non_music"
        return None

    if is_deletable_non_music(title, summary, source, curated=False):
        label = classify(title, summary, source, mode="delete")
        return f"delete:{label}"
    return None


def cmd_report(args: argparse.Namespace) -> int:
    counts = {
        "scanned": 0,
        "delete_candidates": 0,
        "curated_holdback": 0,
        "kept": 0,
    }
    samples: list[dict] = []
    max_pages = None
    if args.sample:
        # approximate pages from sample / 200
        max_pages = max(1, (args.sample + 199) // 200)

    for rec in iter_articles(max_pages=max_pages, per_page=200):
        counts["scanned"] += 1
        if args.sample and counts["scanned"] > args.sample:
            break
        reason = selection_reason(rec)
        if reason is None:
            counts["kept"] += 1
            continue
        if reason.startswith("curated_"):
            counts["curated_holdback"] += 1
        else:
            counts["delete_candidates"] += 1
        if len(samples) < args.examples:
            samples.append(
                {
                    "id": rec.get("id"),
                    "title": (rec.get("title") or "")[:80],
                    "source": rec.get("source"),
                    "reason": reason,
                }
            )

    print(json.dumps({"counts": counts, "examples": samples}, indent=2))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jsonl_path = out / "articles.jsonl"
    manifest_path = out / "manifest.json"

    selected = 0
    scanned = 0
    holdback = 0
    sha = hashlib.sha256()
    max_pages = None if args.all else max(1, (args.limit + 199) // 200)

    with jsonl_path.open("w", encoding="utf-8") as fh:
        for rec in iter_articles(max_pages=max_pages if not args.all else None, per_page=200):
            scanned += 1
            if not args.all and selected >= args.limit:
                break
            reason = selection_reason(rec)
            if reason is None:
                continue
            if reason.startswith("curated_"):
                holdback += 1
                if not args.include_holdback:
                    continue
            row = {
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
                "record": rec,
            }
            line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
            fh.write(line)
            sha.update(line.encode("utf-8"))
            selected += 1

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pb_url": PB_URL,
        "collection": "articles",
        "scanned": scanned,
        "exported": selected,
        "curated_holdback_seen": holdback,
        "jsonl": str(jsonl_path.name),
        "sha256": sha.hexdigest(),
        "filter": "music_classifier mode=delete non_music + discovery noise",
        "include_holdback": bool(args.include_holdback),
        "all_mode": bool(args.all),
        "limit": None if args.all else args.limit,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print(f"Wrote {jsonl_path} and {manifest_path}")
    return 0


def _strip_system_fields(rec: dict) -> dict:
    skip = {"collectionId", "collectionName", "expand"}
    return {k: v for k, v in rec.items() if k not in skip}


def cmd_restore_pilot(args: argparse.Namespace) -> int:
    archive_dir = Path(args.archive)
    jsonl_path = archive_dir / "articles.jsonl"
    manifest_path = archive_dir / "manifest.json"
    if not jsonl_path.exists() or not manifest_path.exists():
        print("Missing articles.jsonl or manifest.json", file=sys.stderr)
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Verify checksum
    h = hashlib.sha256()
    with jsonl_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != manifest.get("sha256"):
        print(
            f"Checksum mismatch: file={h.hexdigest()} manifest={manifest.get('sha256')}",
            file=sys.stderr,
        )
        return 3

    token = pb_auth()
    collection = args.collection
    restored = 0
    errors = 0
    ids: list[str] = []

    with jsonl_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            rec = _strip_system_fields(row.get("record") or {})
            rid = rec.get("id")
            if not rid:
                errors += 1
                continue
            # POST create with same id when possible
            url = f"{PB_URL}/api/collections/{collection}/records"
            try:
                _http_json(url, method="POST", token=token, body=rec)
                restored += 1
                ids.append(rid)
            except RuntimeError as e:
                # try update if exists
                try:
                    _http_json(
                        f"{PB_URL}/api/collections/{collection}/records/{rid}",
                        method="PATCH",
                        token=token,
                        body={k: v for k, v in rec.items() if k != "id"},
                    )
                    restored += 1
                    ids.append(rid)
                except RuntimeError as e2:
                    errors += 1
                    if errors <= 5:
                        print(f"restore fail {rid}: {e2}", file=sys.stderr)

    result = {
        "restored": restored,
        "errors": errors,
        "manifest_exported": manifest.get("exported"),
        "id_count": len(ids),
        "collection": collection,
        "checksum_ok": True,
    }
    print(json.dumps(result, indent=2))
    if restored == 0 or (manifest.get("exported") and restored < manifest["exported"]):
        return 1 if errors else 0
    return 0 if errors == 0 else 1


def cmd_verify_manifest(args: argparse.Namespace) -> int:
    archive_dir = Path(args.archive)
    jsonl_path = archive_dir / "articles.jsonl"
    manifest_path = archive_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    h = hashlib.sha256()
    n = 0
    with jsonl_path.open("rb") as fh:
        for line in fh:
            if line.strip():
                n += 1
            h.update(line)
    ok = h.hexdigest() == manifest.get("sha256") and n == manifest.get("exported")
    print(
        json.dumps(
            {
                "ok": ok,
                "lines": n,
                "manifest_exported": manifest.get("exported"),
                "sha256_file": h.hexdigest(),
                "sha256_manifest": manifest.get("sha256"),
            },
            indent=2,
        )
    )
    return 0 if ok else 1


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Archive / restore PB articles for cleanup")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("report", help="Classify sample and print counts")
    pr.add_argument("--sample", type=int, default=500)
    pr.add_argument("--examples", type=int, default=15)
    pr.set_defaults(func=cmd_report)

    pe = sub.add_parser("export", help="Export delete candidates to JSONL + manifest")
    pe.add_argument("--out", required=True, help="Output directory")
    pe.add_argument("--limit", type=int, default=200, help="Max rows to export (unless --all)")
    pe.add_argument("--all", action="store_true", help="Scan entire collection")
    pe.add_argument(
        "--include-holdback",
        action="store_true",
        help="Also export curated non_music holdback rows",
    )
    pe.set_defaults(func=cmd_export)

    pp = sub.add_parser("restore-pilot", help="Restore archive into a PB collection")
    pp.add_argument("--archive", required=True, help="Directory with articles.jsonl + manifest.json")
    pp.add_argument(
        "--collection",
        default="articles_restore_pilot",
        help="Target collection (create in PB admin first)",
    )
    pp.set_defaults(func=cmd_restore_pilot)

    pv = sub.add_parser("verify", help="Verify archive checksum + line count")
    pv.add_argument("--archive", required=True)
    pv.set_defaults(func=cmd_verify_manifest)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
