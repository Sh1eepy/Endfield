# -*- coding: utf-8 -*-
"""Validate two collector snapshots and report stable-ID content changes."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sys


def entry_id(entry):
    item = entry.get("item") or {}
    for key in ("id", "gameEntryId", "itemId", "wikiItemId"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def entry_name(entry):
    item = entry.get("item") or {}
    return str(item.get("name") or (item.get("brief") or {}).get("name") or "")


def summarize(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    catalog = data.get("catalog") or []
    meta = data.get("meta") or {}
    ids = [entry_id(entry) for entry in catalog]
    counts = collections.Counter(ids)
    errors = []
    missing_ids = sum(not value for value in ids)
    duplicates = sorted(value for value, count in counts.items() if value and count > 1)
    details = sum(isinstance(entry.get("detail"), dict) for entry in catalog)
    detail_without_item = sum(
        isinstance(entry.get("detail"), dict) and not isinstance(entry["detail"].get("item"), dict)
        for entry in catalog
    )
    if int(meta.get("total_catalog_entries", -1)) != len(catalog):
        errors.append("meta_total_mismatch")
    if int(meta.get("detail_success", -1)) != details:
        errors.append("meta_detail_success_mismatch")
    if int(meta.get("detail_failed", -1)) != len(catalog) - details:
        errors.append("meta_detail_failed_mismatch")
    if details != len(catalog):
        errors.append(f"missing_details:{len(catalog) - details}")
    if detail_without_item:
        errors.append(f"detail_without_item:{detail_without_item}")
    if missing_ids:
        errors.append(f"missing_ids:{missing_ids}")
    if duplicates:
        errors.append(f"duplicate_ids:{len(duplicates)}")
    entries = {}
    for entry in catalog:
        stable_id = entry_id(entry)
        if not stable_id:
            continue
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        entries[stable_id] = {
            "name": entry_name(entry),
            "main_type": str(entry.get("mainTypeName") or ""),
            "sub_type": str(entry.get("subTypeName") or ""),
            "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        }
    return {
        "path": os.path.abspath(path),
        "meta": meta,
        "catalog_entries": len(catalog),
        "details": details,
        "validation_errors": errors,
        "categories": dict(sorted(collections.Counter(
            str(entry.get("subTypeName") or "") for entry in catalog
        ).items())),
        "entries": entries,
    }


def compare(old_path, new_path):
    old = summarize(old_path)
    new = summarize(new_path)
    old_entries, new_entries = old.pop("entries"), new.pop("entries")
    old_ids, new_ids = set(old_entries), set(new_entries)
    common = old_ids & new_ids
    changed = sorted(stable_id for stable_id in common
                     if old_entries[stable_id]["sha256"] != new_entries[stable_id]["sha256"])
    category_names = set(old["categories"]) | set(new["categories"])
    return {
        "old": old,
        "new": new,
        "delta": {
            "added": [{"item_id": stable_id, **new_entries[stable_id]}
                      for stable_id in sorted(new_ids - old_ids)],
            "deleted": [{"item_id": stable_id, **old_entries[stable_id]}
                        for stable_id in sorted(old_ids - new_ids)],
            "changed": [{"item_id": stable_id,
                         "old": old_entries[stable_id], "new": new_entries[stable_id]}
                        for stable_id in changed],
            "renamed": [{"item_id": stable_id, "old": old_entries[stable_id]["name"],
                         "new": new_entries[stable_id]["name"]}
                        for stable_id in changed
                        if old_entries[stable_id]["name"] != new_entries[stable_id]["name"]],
            "moved": [{"item_id": stable_id,
                       "old": old_entries[stable_id]["sub_type"],
                       "new": new_entries[stable_id]["sub_type"]}
                      for stable_id in changed
                      if old_entries[stable_id]["sub_type"] != new_entries[stable_id]["sub_type"]],
            "category_counts": {
                name: {"old": old["categories"].get(name, 0),
                       "new": new["categories"].get(name, 0),
                       "delta": new["categories"].get(name, 0) - old["categories"].get(name, 0)}
                for name in sorted(category_names)
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description="校验并比较两个 WIKI 全量采集快照")
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = compare(args.old, args.new)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    delta = result["delta"]
    print(json.dumps({
        "old_entries": result["old"]["catalog_entries"],
        "new_entries": result["new"]["catalog_entries"],
        "added": len(delta["added"]),
        "deleted": len(delta["deleted"]),
        "changed": len(delta["changed"]),
        "renamed": len(delta["renamed"]),
        "moved": len(delta["moved"]),
        "validation_errors": result["new"]["validation_errors"],
    }, ensure_ascii=False, indent=2))
    if result["new"]["validation_errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    main()
