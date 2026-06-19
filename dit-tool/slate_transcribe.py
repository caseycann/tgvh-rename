"""
Slate transcription — read-only audio scrub for proposing scene/shot/take
when no Airtable log exists for a day.

File integrity guarantee: this module only ever reads from the original
media file. ffmpeg is invoked with the original as `-i` (input) and a fresh
file in the system temp directory as the only output; the original is never
opened for writing, transcoded in place, or modified in any way. The temp
extract is always deleted afterward (even on error).

This is a *suggestion* tool — output is meant for a human to review/edit
before any rename happens, since spoken-slate transcription is inherently
imperfect (mumbled numbers, ambient noise, no slate this take, etc).
"""

import re
import subprocess
import tempfile
from pathlib import Path

from core import RenameToolError

MODEL_NAME = "base.en"
DEFAULT_DURATION_S = 20

_model = None


def get_model():
    """Lazy-loaded singleton — avoids paying model load time unless transcription is actually used."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
    return _model


def extract_audio_snippet(path: Path, start_s: float = 0, duration_s: float = DEFAULT_DURATION_S) -> Path:
    """Extracts a short mono 16kHz WAV snippet from `path` into a system temp
    file using ffmpeg. Read-only on `path` — ffmpeg's -i never writes to its
    input. Caller is responsible for deleting the returned path."""
    fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="slate_scrub_")
    tmp_path = Path(tmp_path)
    import os
    os.close(fd)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_s),
        "-t", str(duration_s),
        "-i", str(path),
        "-vn", "-ar", "16000", "-ac", "1",
        str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tmp_path.unlink(missing_ok=True)
        raise RenameToolError(f"ffmpeg failed to extract audio from {path.name}: {result.stderr[-500:]}")
    return tmp_path


def transcribe_snippet(wav_path: Path) -> str:
    model = get_model()
    segments, _info = model.transcribe(str(wav_path))
    return " ".join(seg.text.strip() for seg in segments).strip()


def _normalize_digit_group(raw: str) -> str:
    """'2-3' or '2 3' (digit-by-digit slate call) -> '23'. Leaves '55b', '23' as-is."""
    raw = raw.strip()
    parts = re.split(r"[\s-]+", raw)
    if len(parts) > 1 and all(re.fullmatch(r"\d", p) for p in parts):
        return "".join(parts)
    return raw.replace(" ", "")


def parse_slate(text: str) -> dict:
    """Best-effort extraction of scene/shot/take from a transcript. Any field
    not found is None — caller should treat this as a suggestion, not fact."""
    result = {"scene": None, "shot": None, "take": None, "raw_transcript": text}

    scene_match = re.search(r"scene\s*[:#-]?\s*([0-9]+(?:[\s-]+[0-9])*[a-z]?)", text, re.IGNORECASE)
    if scene_match:
        result["scene"] = _normalize_digit_group(scene_match.group(1))

    shot_match = re.search(r"shot\s*[:#-]?\s*([0-9]+(?:[\s-]+[0-9])*[a-z]?)", text, re.IGNORECASE)
    if shot_match:
        result["shot"] = _normalize_digit_group(shot_match.group(1))

    take_match = re.search(r"take\s*[:#-]?\s*([0-9]+(?:[\s-]+[0-9])*[a-z]?)", text, re.IGNORECASE)
    if take_match:
        result["take"] = _normalize_digit_group(take_match.group(1))

    return result


def suggest_for_file(path: Path, start_s: float = 0, duration_s: float = DEFAULT_DURATION_S) -> dict:
    """Extracts a snippet, transcribes it, parses for slate info, and always
    cleans up the temp audio file regardless of outcome."""
    snippet_path = extract_audio_snippet(path, start_s, duration_s)
    try:
        text = transcribe_snippet(snippet_path)
    finally:
        snippet_path.unlink(missing_ok=True)
    return parse_slate(text)
