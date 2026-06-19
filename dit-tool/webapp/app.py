"""
Local web UI for the DIT rename tool — run on whoever's laptop is doing the
renaming (DIT or AD), open http://localhost:5050 in a browser. No files are
ever uploaded; this process and the browser tab are both on the same
machine, talking over localhost only. Airtable calls (small JSON records)
are the only network traffic — never media.
"""

import os
import sys
import urllib.parse
import urllib.request
import json as jsonlib
from pathlib import Path

from flask import Flask, jsonify, request, render_template

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core
import slate_transcribe

app = Flask(__name__)

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME", "Footage")


def error_response(message, status=400):
    return jsonify({"error": message}), status


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/folder-status", methods=["POST"])
def folder_status():
    body = request.get_json(force=True)
    root_arg = body.get("root", "")
    try:
        root = core.resolve_root(root_arg)
    except core.RenameToolError as e:
        return error_response(str(e))

    footage = core.media_files(root / "Footage")
    audio = core.media_files(root / "Audio")
    try:
        iso_date = core.folder_date_to_iso(root)
    except core.RenameToolError:
        iso_date = None

    return jsonify({
        "root": str(root),
        "footage_count": len(footage),
        "audio_count": len(audio),
        "date_iso": iso_date,
    })


def airtable_records(table, fields):
    params = []
    for f in fields:
        params.append(("fields[]", f))
    params.append(("pageSize", "100"))
    records = []
    offset = None
    while True:
        p = list(params)
        if offset:
            p.append(("offset", offset))
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(table)}?{urllib.parse.urlencode(p)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {AIRTABLE_API_KEY}"})
        with urllib.request.urlopen(req) as resp:
            data = jsonlib.loads(resp.read())
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


@app.route("/api/options")
def options():
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        return error_response("AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set in the environment.")
    try:
        location_records = airtable_records("Physical Locations", ["Name", "Nickname"])
        scene_records = airtable_records("Scenes", ["Scene Number"])
    except Exception as e:
        return error_response(f"Airtable request failed: {e}", 502)

    locations = sorted(
        (
            {"id": r["id"], "label": r["fields"].get("Nickname") or r["fields"].get("Name") or "(unnamed)"}
            for r in location_records
        ),
        key=lambda x: x["label"],
    )
    scenes = []
    for r in scene_records:
        raw = r["fields"].get("Scene Number", "")
        label = raw[6:].strip() if raw.lower().startswith("scene") else raw.strip()
        if label:
            scenes.append({"id": r["id"], "label": label})
    scenes.sort(key=lambda x: x["label"])

    return jsonify({"locations": locations, "scenes": scenes})


@app.route("/api/live/context", methods=["POST"])
def live_context():
    body = request.get_json(force=True)
    try:
        root = core.resolve_root(body.get("root", ""))
    except core.RenameToolError as e:
        return error_response(str(e))

    footage_file = core.most_recent_file(root / "Footage")
    audio_file = core.most_recent_file(root / "Audio")
    return jsonify({
        "footage_file": footage_file.name if footage_file else None,
        "audio_file": audio_file.name if audio_file else None,
    })


def renames_to_json(renames):
    return [{"original": str(o), "new_name": n.name} for o, n in renames]


@app.route("/api/live/preview", methods=["POST"])
def live_preview_route():
    body = request.get_json(force=True)
    try:
        root = core.resolve_root(body.get("root", ""))
    except core.RenameToolError as e:
        return error_response(str(e))

    renames, notes = core.live_preview(
        root, body.get("location", ""), body.get("scene", ""), body.get("shot", ""), body.get("take", "")
    )
    return jsonify({"renames": renames_to_json(renames), "notes": notes})


@app.route("/api/pull/preview", methods=["POST"])
def pull_preview_route():
    body = request.get_json(force=True)
    try:
        root = core.resolve_root(body.get("root", ""))
        renames, warnings, take_count = core.pull_preview(
            root, AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME
        )
    except core.RenameToolError as e:
        return error_response(str(e))

    return jsonify({"renames": renames_to_json(renames), "warnings": warnings, "take_count": take_count})


@app.route("/api/batch/template", methods=["POST"])
def batch_template_route():
    body = request.get_json(force=True)
    try:
        root = core.resolve_root(body.get("root", ""))
    except core.RenameToolError as e:
        return error_response(str(e))

    rows = core.batch_template_rows(root)
    return jsonify({"rows": rows})


@app.route("/api/batch/preview", methods=["POST"])
def batch_preview_route():
    body = request.get_json(force=True)
    try:
        root = core.resolve_root(body.get("root", ""))
    except core.RenameToolError as e:
        return error_response(str(e))

    rows = body.get("rows", [])
    core.write_batch_csv(root, rows)  # audit trail, same as CLI
    renames, warnings = core.batch_rows_to_renames(root, rows)
    return jsonify({"renames": renames_to_json(renames), "warnings": warnings})


@app.route("/api/transcribe", methods=["POST"])
def transcribe_route():
    body = request.get_json(force=True)
    try:
        root = core.resolve_root(body.get("root", ""))
    except core.RenameToolError as e:
        return error_response(str(e))

    relative_path = body.get("relative_path", "")
    target = root / relative_path
    if not target.exists():
        return error_response(f"File not found: {relative_path}")

    start_s = float(body.get("start_s", 0))
    duration_s = float(body.get("duration_s", slate_transcribe.DEFAULT_DURATION_S))

    try:
        suggestion = slate_transcribe.suggest_for_file(target, start_s, duration_s)
    except core.RenameToolError as e:
        return error_response(str(e), 502)

    return jsonify(suggestion)


@app.route("/api/execute", methods=["POST"])
def execute_route():
    body = request.get_json(force=True)
    try:
        root = core.resolve_root(body.get("root", ""))
    except core.RenameToolError as e:
        return error_response(str(e))

    mode = body.get("mode", "unknown")
    pairs = [(Path(item["original"]), Path(item["original"]).parent / item["new_name"]) for item in body.get("renames", [])]
    results = core.execute_renames(root, pairs, mode)
    return jsonify({
        "results": [
            {"original": str(o), "new": str(n), "success": s, "message": m}
            for o, n, s, m in results
        ]
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"DIT rename tool running at http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
