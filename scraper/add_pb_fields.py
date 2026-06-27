#!/usr/bin/env python3
"""add_pb_fields.py — Add new fields to articles + entities collections in PocketBase."""
import json, os, urllib.request
from pathlib import Path

ENV_FILE = Path("/home/exedev/miny-ven/scraper/.env")
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

PB_URL = os.getenv("ARTICLES_PB_URL", "https://miny-database.exe.xyz")
PB_EMAIL = os.getenv("ARTICLES_PB_ADMIN_EMAIL", "admin@miny-ven.local")
PB_PASSWORD = os.getenv("ARTICLES_PB_ADMIN_PASSWORD", "")


def auth():
    data = json.dumps({"identity": PB_EMAIL, "password": PB_PASSWORD}).encode()
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/_superusers/auth-with-password",
        data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["token"]


def get_collection(token, name):
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/{name}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def patch_collection(token, name, collection_data):
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/{name}",
        data=json.dumps(collection_data).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def main():
    token = auth()
    print(f"Authenticated to {PB_URL}")

    articles_new = [
        {"name": "curated_at", "type": "date", "required": False},
        {"name": "entity_ids", "type": "json", "required": False},
        {"name": "entity_rc_url", "type": "text", "required": False},
    ]
    entities_new = [
        {"name": "city", "type": "text", "required": False},
        {"name": "last_seen", "type": "date", "required": False},
        {"name": "rc_profile_url", "type": "text", "required": False},
        {"name": "rc_bio", "type": "text", "required": False},
        {"name": "rc_socials", "type": "json", "required": False},
        {"name": "rc_genres", "type": "json", "required": False},
        {"name": "rc_enriched", "type": "bool", "required": False},
        {"name": "rc_enriched_at", "type": "date", "required": False},
    ]

    for coll_name, new_fields in [("articles", articles_new), ("entities", entities_new)]:
        coll = get_collection(token, coll_name)
        existing = {f["name"] for f in coll["fields"]}
        added = []
        for nf in new_fields:
            if nf["name"] not in existing:
                coll["fields"].append(nf)
                added.append(nf["name"])
        if added:
            patch_collection(token, coll_name, coll)
            print(f"  {coll_name}: added {added}")
        else:
            print(f"  {coll_name}: all fields already present")

    print("Done.")


if __name__ == "__main__":
    main()