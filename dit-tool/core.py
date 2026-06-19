"""
Shared rename/pairing/Airtable logic for the DIT tool.

No print()/input()/sys.exit() in this module — it's used by both the CLI
(rename_footage.py) and the local web app (webapp/app.py), which need to
present output differently. Functions raise RenameToolError on user-facing
failures; callers decide how to display that.

Nothing here ever writes to or transcodes an original media file's content.
safe_rename() only renames (a directory-entry operation) — it never opens
the file for writing.
"""

import csv
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".mxf", ".mov", ".mp4", ".r3d", ".braw", ".ari",
    ".wav", ".bwf", ".m4a", ".aac", ".caf", ".mp3",
}

LOG_FILENAME = "rename_log.csv"
BATCH_CSV_FILENAME = "batch_rename.csv"


class RenameToolError(Exception):
    """User-facing error: missing folder, bad date, Airtable failure, etc."""


def pad(value, width=2):
    s = str(value)
    return s.zfill(width) if s.isdigit() else s


def build_basename(location, scene, shot, take):
    return f"{location}_{pad(scene)}_{pad(shot)}_{pad(take)}"


def today_folder_name():
    return date.today().strftime("%Y%m%d")


def resolve_root(root_arg, cwd: Path = None):
    cwd = cwd or Path.cwd()
    if root_arg:
        root = Path(root_arg).expanduser().resolve()
    else:
        root = cwd / today_folder_name()
    if not root.exists():
        raise RenameToolError(f"Root folder not found: {root}")
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
        csv.writer(f).writerow(
            [datetime.now().isoformat(timespec="seconds"), str(original), str(new), mode]
        )


def safe_rename(original: Path, new: Path):
    """Renames original -> new. Never opens either file for writing; this is
    a directory-entry rename only, so file content is never touched.
    Returns (success: bool, message: str)."""
    if new.exists():
        return False, f"SKIPPED (target exists): {new.name}"
    original.rename(new)
    return True, f"Renamed: {original.name} -> {new.name}"


def execute_renames(root: Path, renames, mode: str):
    """renames: list of (Path original, Path new). Returns list of (original, new, success, message)."""
    results = []
    for original, new in renames:
        success, message = safe_rename(original, new)
        if success:
            append_log(root, original, new, mode)
        results.append((original, new, success, message))
    return results


# ---------------------------------------------------------------------------
# live mode
# ---------------------------------------------------------------------------

def live_preview(root: Path, location, scene, shot, take):
    footage_dir = root / "Footage"
    audio_dir = root / "Audio"
    basename = build_basename(location, scene, shot, take)

    renames = []
    notes = []
    footage_file = most_recent_file(footage_dir)
    if footage_file:
        renames.append((footage_file, footage_dir / f"{basename}{footage_file.suffix.lower()}"))
    else:
        notes.append(f"No footage file found in {footage_dir}")

    audio_file = most_recent_file(audio_dir)
    if audio_file:
        renames.append((audio_file, audio_dir / f"{basename}{audio_file.suffix.lower()}"))
    else:
        notes.append(f"No audio file found in {audio_dir}")

    return renames, notes


# ---------------------------------------------------------------------------
# batch mode
# ---------------------------------------------------------------------------

def batch_template_rows(root: Path):
    footage_dir = root / "Footage"
    audio_dir = root / "Audio"
    rows = []
    for folder in (footage_dir, audio_dir):
        for f in media_files(folder):
            rows.append({"original_path": str(f.relative_to(root)), "location": "", "scene": "", "shot": "", "take": ""})
    return rows


def write_batch_csv(root: Path, rows):
    csv_path = root / BATCH_CSV_FILENAME
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["original_path", "location", "scene", "shot", "take"], extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


def read_batch_csv(root: Path):
    csv_path = root / BATCH_CSV_FILENAME
    if not csv_path.exists():
        return None
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def batch_rows_to_renames(root: Path, rows):
    """rows: list of dicts with original_path/location/scene/shot/take. Returns (renames, warnings)."""
    renames = []
    warnings = []
    for row in rows:
        original_path = (row.get("original_path") or "").strip()
        location = (row.get("location") or "").strip()
        scene = (row.get("scene") or "").strip()
        shot = (row.get("shot") or "").strip()
        take = (row.get("take") or "").strip()
        if not original_path or not (location and scene and shot and take):
            continue
        original = root / original_path
        if not original.exists():
            warnings.append(f"File not found, skipping: {original_path}")
            continue
        basename = build_basename(location, scene, shot, take)
        new = original.parent / f"{basename}{original.suffix.lower()}"
        renames.append((original, new))
    return renames, warnings


# ---------------------------------------------------------------------------
# pull mode (Airtable)
# ---------------------------------------------------------------------------

def airtable_get(path, params, api_key, base_id):
    if not api_key or not base_id:
        raise RenameToolError("AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set for pull mode.")
    url = f"https://api.airtable.com/v0/{base_id}/{urllib.parse.quote(path)}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RenameToolError(f"Airtable request failed ({e.code}): {e.read().decode()}")


def fetch_takes_for_date(iso_date, api_key, base_id, table_name="Footage"):
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
        data = airtable_get(table_name, params, api_key, base_id)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def folder_date_to_iso(root: Path):
    match = re.match(r"^(\d{4})(\d{2})(\d{2})", root.name)
    if not match:
        raise RenameToolError(f"Could not parse a YYYYMMDD date from folder name: {root.name}")
    y, m, d = match.groups()
    return f"{y}-{m}-{d}"


def pair_files_to_takes(files, records):
    """Zip files and Airtable records in chronological order. Returns (pairs, mismatch)."""
    n = min(len(files), len(records))
    pairs = list(zip(files[:n], records[:n]))
    mismatch = len(files) != len(records)
    return pairs, mismatch


def pull_preview(root: Path, api_key, base_id, table_name="Footage"):
    """Returns (renames, warnings, take_count)."""
    footage_dir = root / "Footage"
    audio_dir = root / "Audio"
    iso_date = folder_date_to_iso(root)

    records = fetch_takes_for_date(iso_date, api_key, base_id, table_name)
    if not records:
        raise RenameToolError(f"No Airtable rows found for {iso_date}.")

    renames = []
    warnings = []
    for folder in (footage_dir, audio_dir):
        files = media_files(folder)
        pairs, mismatch = pair_files_to_takes(files, records)
        if mismatch:
            warnings.append(
                f"{folder.name} has {len(files)} file(s) but Airtable has {len(records)} "
                f"logged take(s) for {iso_date}. Only pairing the first {len(pairs)}; review "
                f"carefully before confirming, or use batch mode instead."
            )
        for f, record in pairs:
            fields = record.get("fields", {})
            basename = fields.get("Name", "")
            if not basename:
                warnings.append(f"Row has no Name field, skipping (record {record.get('id')})")
                continue
            renames.append((f, f.parent / f"{basename}{f.suffix.lower()}"))

    return renames, warnings, len(records)


# ---------------------------------------------------------------------------
# Airtable sync — link a renamed file back to a Footage row after the fact
# ---------------------------------------------------------------------------

def _escape_formula_string(value: str) -> str:
    return value.replace("'", "\\'")


def airtable_post(table, fields, api_key, base_id, typecast=True):
    url = f"https://api.airtable.com/v0/{base_id}/{urllib.parse.quote(table)}"
    body = json.dumps({"fields": fields, "typecast": typecast}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RenameToolError(f"Airtable create failed ({e.code}): {e.read().decode()}")


def airtable_patch(table, record_id, fields, api_key, base_id, typecast=True):
    url = f"https://api.airtable.com/v0/{base_id}/{urllib.parse.quote(table)}/{record_id}"
    body = json.dumps({"fields": fields, "typecast": typecast}).encode()
    req = urllib.request.Request(
        url, data=body, method="PATCH",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RenameToolError(f"Airtable update failed ({e.code}): {e.read().decode()}")


def find_records_by_name(basename, api_key, base_id, table_name="Footage"):
    """Returns every record whose Name matches `basename` — usually 0 or 1,
    but callers must check for >1 (pre-existing duplicate) rather than just
    grabbing the first, since silently picking one would hide the problem."""
    params = {"filterByFormula": f"{{Name}} = '{_escape_formula_string(basename)}'", "maxRecords": "10"}
    data = airtable_get(table_name, params, api_key, base_id)
    return data.get("records", [])


def sync_take_to_airtable(basename, date_iso, location_id, scene_id, shot, take, sync_sound,
                           api_key, base_id, table_name="Footage"):
    """Looks up `basename` in the Footage table by Name *before* making any
    change, so any duplicate found here necessarily predates this rename —
    this tool never creates two rows for the same take itself (footage and
    audio of one take are deduped to a single sync call by the caller).

    - 0 matches: creates a new row, Source = 'Ingested'.
    - 1 match (AD already live-logged it): only sets Source = 'Live logged'
      (plus Sync Sound, see below) — nothing else on that row is touched.
    - >1 matches: a pre-existing duplicate. Does not touch any of them;
      returns action='duplicate' so the caller can warn instead of guessing
      which row is the "real" one.

    `sync_sound`: True when both a footage file and an audio file were
    renamed to this basename in this batch — checks the Sync Sound box.
    Never explicitly unchecked, so a manually-set value elsewhere is never
    clobbered when only one media type is present this run.

    Returns: {basename, action: 'matched'|'created'|'duplicate'|'skipped'|'error', ...}
    """
    if not api_key or not base_id:
        return {"basename": basename, "action": "skipped", "error": "Airtable not configured"}

    try:
        matches = find_records_by_name(basename, api_key, base_id, table_name)

        if len(matches) > 1:
            return {
                "basename": basename, "action": "duplicate",
                "record_ids": [m["id"] for m in matches],
            }

        if len(matches) == 1:
            fields = {"Source": "Live logged"}
            if sync_sound:
                fields["Sync Sound"] = True
            airtable_patch(table_name, matches[0]["id"], fields, api_key, base_id)
            return {"basename": basename, "action": "matched", "record_id": matches[0]["id"]}

        fields = {"Name": basename, "Source": "Ingested"}
        if date_iso:
            fields["Date"] = date_iso
        if location_id:
            fields["Physical Locations"] = [location_id]
        if scene_id:
            fields["Scene"] = [scene_id]
        if shot:
            fields["Shot"] = str(shot)
        if take:
            fields["Take"] = int(take)
        if sync_sound:
            fields["Sync Sound"] = True
        created = airtable_post(table_name, fields, api_key, base_id)
        return {"basename": basename, "action": "created", "record_id": created["id"]}
    except RenameToolError as e:
        return {"basename": basename, "action": "error", "error": str(e)}
