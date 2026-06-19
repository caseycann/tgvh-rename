#!/usr/bin/env python3
"""
DIT footage/audio renaming tool.

Renames camera/sound files into Location_Scene_Shot_Take.ext inside a
YYYYMMDD/Footage and YYYYMMDD/Audio folder pair.

Three modes:
  live   - rename the most-recently-modified file(s) right after a take, no Airtable needed
  batch  - CSV-driven rename, for days with no live logging (DIT watches footage back)
  pull   - fetch the day's takes logged to Airtable by the AD/director, match to files, rename

No media is ever uploaded anywhere. `pull` only sends/receives small JSON
records to/from Airtable; all file I/O is local.
"""

import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".mxf", ".mov", ".mp4", ".r3d", ".braw", ".ari",
    ".wav", ".bwf",
}

LOG_FILENAME = "rename_log.csv"
BATCH_CSV_FILENAME = "batch_rename.csv"

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME", "Footage")


def pad(value, width=2):
    s = str(value)
    return s.zfill(width) if s.isdigit() else s


def build_basename(location, scene, shot, take):
    return f"{location}_{pad(scene)}_{pad(shot)}_{pad(take)}"


def today_folder_name():
    return date.today().strftime("%Y%m%d")


def resolve_root(root_arg):
    if root_arg:
        root = Path(root_arg).resolve()
    else:
        root = Path.cwd() / today_folder_name()
    if not root.exists():
        sys.exit(f"Root folder not found: {root}")
    return root


def media_files(folder: Path):
    if not folder.exists():
        return []
    return sorted(
        (f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS),
        key=lambda f: f.stat().st_mtime,
    )


def most_recent_file(folder: Path):
    files = media_files(folder)
    return files[-1] if files else None


def ensure_log(root: Path):
    log_path = root / LOG_FILENAME
    if not log_path.exists():
        with open(log_path, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp", "original_path", "new_path", "mode"])
    return log_path


def append_log(root: Path, original: Path, new: Path, mode: str):
    log_path = ensure_log(root)
    with open(log_path, "a", newline="") as f:
        csv.writer(f).writerow([datetime.now().isoformat(timespec="seconds"), str(original), str(new), mode])


def preview_and_confirm(renames):
    """renames: list of (Path original, Path new). Prints preview, asks y/n."""
    if not renames:
        print("Nothing to rename.")
        return False
    print("\nProposed renames:")
    for original, new in renames:
        print(f"  {original.name}  ->  {new.name}")
    answer = input("\nProceed? [y/N] ").strip().lower()
    return answer == "y"


def safe_rename(original: Path, new: Path):
    if new.exists():
        print(f"  SKIPPED (target exists): {new.name}")
        return False
    original.rename(new)
    print(f"  Renamed: {original.name} -> {new.name}")
    return True


def execute_renames(root: Path, renames, mode: str):
    count = 0
    for original, new in renames:
        if safe_rename(original, new):
            append_log(root, original, new, mode)
            count += 1
    print(f"\n{count}/{len(renames)} files renamed.")


# ---------------------------------------------------------------------------
# live mode
# ---------------------------------------------------------------------------

def cmd_live(args):
    root = resolve_root(args.root)
    footage_dir = root / "Footage"
    audio_dir = root / "Audio"

    location = input("Location: ").strip()
    scene = input("Scene: ").strip()
    shot = input("Shot: ").strip()
    take = input("Take: ").strip()
    basename = build_basename(location, scene, shot, take)

    renames = []
    footage_file = most_recent_file(footage_dir)
    if footage_file:
        renames.append((footage_file, footage_dir / f"{basename}{footage_file.suffix.lower()}"))
    else:
        print(f"  (no footage file found in {footage_dir})")

    audio_file = most_recent_file(audio_dir)
    if audio_file:
        renames.append((audio_file, audio_dir / f"{basename}{audio_file.suffix.lower()}"))
    else:
        print(f"  (no audio file found in {audio_dir})")

    if preview_and_confirm(renames):
        execute_renames(root, renames, "live")


# ---------------------------------------------------------------------------
# batch mode
# ---------------------------------------------------------------------------

def write_batch_template(csv_path: Path, footage_dir: Path, audio_dir: Path):
    rows = []
    for folder in (footage_dir, audio_dir):
        for f in media_files(folder):
            rows.append([str(f.relative_to(csv_path.parent)), "", "", "", ""])
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["original_path", "location", "scene", "shot", "take"])
        writer.writerows(rows)
    print(f"Created template: {csv_path}")
    print("Fill in location/scene/shot/take for each row, then re-run `batch`.")


def cmd_batch(args):
    root = resolve_root(args.root)
    footage_dir = root / "Footage"
    audio_dir = root / "Audio"
    csv_path = root / BATCH_CSV_FILENAME

    if not csv_path.exists():
        write_batch_template(csv_path, footage_dir, audio_dir)
        return

    renames = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            original_path = row.get("original_path", "").strip()
            location = row.get("location", "").strip()
            scene = row.get("scene", "").strip()
            shot = row.get("shot", "").strip()
            take = row.get("take", "").strip()
            if not original_path or not (location and scene and shot and take):
                continue
            original = root / original_path
            if not original.exists():
                print(f"  WARNING: file not found, skipping: {original_path}")
                continue
            basename = build_basename(location, scene, shot, take)
            new = original.parent / f"{basename}{original.suffix.lower()}"
            renames.append((original, new))

    if preview_and_confirm(renames):
        execute_renames(root, renames, "batch")


# ---------------------------------------------------------------------------
# pull mode (Airtable)
# ---------------------------------------------------------------------------

def airtable_get(path, params):
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        sys.exit("AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set in the environment for `pull`.")
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(path)}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {AIRTABLE_API_KEY}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Airtable request failed ({e.code}): {e.read().decode()}")


def fetch_takes_for_date(iso_date: str):
    records = []
    offset = None
    while True:
        params = {
            "filterByFormula": f"DATETIME_FORMAT({{Date}}, 'YYYY-MM-DD') = '{iso_date}'",
            "sort[0][field]": "Logged At",
            "sort[0][direction]": "asc",
        }
        if offset:
            params["offset"] = offset
        data = airtable_get(AIRTABLE_TABLE_NAME, params)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def folder_date_to_iso(root: Path):
    match = re.match(r"^(\d{4})(\d{2})(\d{2})", root.name)
    if not match:
        sys.exit(f"Could not parse a YYYYMMDD date from folder name: {root.name}")
    y, m, d = match.groups()
    return f"{y}-{m}-{d}"


def pair_files_to_takes(files, records):
    """Zip files and Airtable records in chronological order. Returns (pairs, mismatch)."""
    n = min(len(files), len(records))
    pairs = list(zip(files[:n], records[:n]))
    mismatch = len(files) != len(records)
    return pairs, mismatch


def cmd_pull(args):
    root = resolve_root(args.root)
    footage_dir = root / "Footage"
    audio_dir = root / "Audio"
    iso_date = folder_date_to_iso(root)

    print(f"Fetching takes logged for {iso_date} from Airtable...")
    records = fetch_takes_for_date(iso_date)
    if not records:
        sys.exit(f"No Airtable rows found for {iso_date}.")
    print(f"Found {len(records)} logged take(s).")

    renames = []
    for folder in (footage_dir, audio_dir):
        files = media_files(folder)
        pairs, mismatch = pair_files_to_takes(files, records)
        if mismatch:
            print(
                f"\nWARNING: {folder.name} has {len(files)} file(s) but Airtable has "
                f"{len(records)} logged take(s) for {iso_date}. Only pairing the first "
                f"{len(pairs)}; review carefully before confirming, or use `batch` instead."
            )
        for f, record in pairs:
            fields = record.get("fields", {})
            location = fields.get("Location", "")
            scene = fields.get("Scene", "")
            shot = fields.get("Shot", "")
            take = fields.get("Take", "")
            if not (location and scene and shot and take):
                print(f"  WARNING: incomplete Airtable row, skipping: {fields}")
                continue
            basename = build_basename(location, scene, shot, take)
            renames.append((f, f.parent / f"{basename}{f.suffix.lower()}"))

    if preview_and_confirm(renames):
        execute_renames(root, renames, "pull")


# ---------------------------------------------------------------------------

def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="Path to the YYYYMMDD date folder (defaults to ./<today>)")

    parser = argparse.ArgumentParser(description="Rename footage/audio files for a shoot day.")
    sub = parser.add_subparsers(dest="mode", required=True)

    sub.add_parser("live", parents=[common], help="Rename the most recently modified file(s) right after a take")
    sub.add_parser("batch", parents=[common], help="CSV-driven rename (creates a template on first run)")
    sub.add_parser("pull", parents=[common], help="Fetch today's logged takes from Airtable and rename to match")

    args = parser.parse_args()
    {"live": cmd_live, "batch": cmd_batch, "pull": cmd_pull}[args.mode](args)


if __name__ == "__main__":
    main()
