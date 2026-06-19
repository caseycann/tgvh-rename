#!/usr/bin/env python3
"""
DIT footage/audio renaming tool (CLI).

Renames camera/sound files into Location_Scene_Shot_Take.ext inside a
YYYYMMDD/Footage and YYYYMMDD/Audio folder pair.

Three modes:
  live   - rename the most-recently-modified file(s) right after a take, no Airtable needed
  batch  - CSV-driven rename, for days with no live logging (DIT watches footage back)
  pull   - fetch the day's takes logged to Airtable by the AD/director, match to files, rename

No media is ever uploaded anywhere. `pull` only sends/receives small JSON
records to/from Airtable; all file I/O is local.

A local web UI is also available — see webapp/app.py — for anyone who'd
rather not use the command line.
"""

import argparse
import os
import sys

import core

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME", "Footage")


def preview_and_confirm(renames):
    if not renames:
        print("Nothing to rename.")
        return False
    print("\nProposed renames:")
    for original, new in renames:
        print(f"  {original.name}  ->  {new.name}")
    answer = input("\nProceed? [y/N] ").strip().lower()
    return answer == "y"


def run_renames(root, renames, mode):
    results = core.execute_renames(root, renames, mode)
    for _, _, _, message in results:
        print(f"  {message}")
    count = sum(1 for _, _, success, _ in results if success)
    print(f"\n{count}/{len(results)} files renamed.")


def cmd_live(args):
    root = core.resolve_root(args.root)
    location = input("Location: ").strip()
    scene = input("Scene: ").strip()
    shot = input("Shot: ").strip()
    take = input("Take: ").strip()

    renames, notes = core.live_preview(root, location, scene, shot, take)
    for note in notes:
        print(f"  ({note})")

    if preview_and_confirm(renames):
        run_renames(root, renames, "live")


def cmd_batch(args):
    root = core.resolve_root(args.root)
    csv_path = root / core.BATCH_CSV_FILENAME

    if not csv_path.exists():
        rows = core.batch_template_rows(root)
        core.write_batch_csv(root, rows)
        print(f"Created template: {csv_path}")
        print("Fill in location/scene/shot/take for each row, then re-run `batch`.")
        return

    rows = core.read_batch_csv(root)
    renames, warnings = core.batch_rows_to_renames(root, rows)
    for warning in warnings:
        print(f"  WARNING: {warning}")

    if preview_and_confirm(renames):
        run_renames(root, renames, "batch")


def cmd_pull(args):
    root = core.resolve_root(args.root)
    iso_date = core.folder_date_to_iso(root)
    print(f"Fetching takes logged for {iso_date} from Airtable...")

    try:
        renames, warnings, take_count = core.pull_preview(
            root, AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME
        )
    except core.RenameToolError as e:
        sys.exit(str(e))

    print(f"Found {take_count} logged take(s).")
    for warning in warnings:
        print(f"\nWARNING: {warning}")

    if preview_and_confirm(renames):
        run_renames(root, renames, "pull")


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="Path to the YYYYMMDD date folder (defaults to ./<today>)")

    parser = argparse.ArgumentParser(description="Rename footage/audio files for a shoot day.")
    sub = parser.add_subparsers(dest="mode", required=True)

    sub.add_parser("live", parents=[common], help="Rename the most recently modified file(s) right after a take")
    sub.add_parser("batch", parents=[common], help="CSV-driven rename (creates a template on first run)")
    sub.add_parser("pull", parents=[common], help="Fetch today's logged takes from Airtable and rename to match")

    args = parser.parse_args()
    try:
        {"live": cmd_live, "batch": cmd_batch, "pull": cmd_pull}[args.mode](args)
    except core.RenameToolError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
