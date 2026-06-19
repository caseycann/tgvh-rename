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


_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_NUMBER_WORDS = {**_ONES, **_TENS}


def _normalize_spoken_numbers(text: str) -> str:
    """Whisper inconsistently converts spelled-out numbers to digits —
    'shot four' sometimes stays as words instead of becoming 'shot 4'. This
    rewrites any number word/compound (e.g. 'twenty three') into digits so
    parsing doesn't silently miss those fields."""
    tokens = text.split(" ")
    out = []
    i = 0
    while i < len(tokens):
        raw = tokens[i]
        core_word = re.sub(r"[^A-Za-z]", "", raw).lower()
        trailing = re.sub(r"^[A-Za-z]*", "", raw)
        if core_word in _NUMBER_WORDS:
            value = _NUMBER_WORDS[core_word]
            consumed = 1
            if core_word in _TENS and i + 1 < len(tokens):
                next_core = re.sub(r"[^A-Za-z]", "", tokens[i + 1]).lower()
                if next_core in _ONES:
                    value += _ONES[next_core]
                    consumed = 2
                    trailing = re.sub(r"^[A-Za-z]*", "", tokens[i + 1])
            out.append(str(value) + trailing)
            i += consumed
        else:
            out.append(raw)
            i += 1
    return " ".join(out)


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
    normalized = _normalize_spoken_numbers(text)
    result = {
        "scene": None, "shot": None, "take": None,
        "scene_inferred": False, "raw_transcript": text,
    }

    scene_match = re.search(r"scene\s*[:#-]?\s*([0-9]+(?:[\s-]+[0-9])*[a-z]?)", normalized, re.IGNORECASE)
    if scene_match:
        result["scene"] = _normalize_digit_group(scene_match.group(1))

    shot_match = re.search(r"shot\s*[:#-]?\s*([0-9]+(?:[\s-]+[0-9])*[a-z]?)", normalized, re.IGNORECASE)
    if shot_match:
        result["shot"] = _normalize_digit_group(shot_match.group(1))

    take_match = re.search(r"take\s*[:#-]?\s*([0-9]+(?:[\s-]+[0-9])*[a-z]?)", normalized, re.IGNORECASE)
    if take_match:
        result["take"] = _normalize_digit_group(take_match.group(1))

    # Sometimes the word "scene" itself gets dropped/mumbled in transcription
    # but the number is still there at the very start, immediately ahead of
    # "shot"/"take" — fall back to treating a leading bare number as the
    # scene guess, flagged as inferred so the UI can show it's less certain.
    if result["scene"] is None:
        leading_match = re.match(r"^\s*([0-9]+[a-z]?)\b", normalized)
        if leading_match and re.search(r"\b(shot|take)\b", normalized, re.IGNORECASE):
            result["scene"] = leading_match.group(1)
            result["scene_inferred"] = True

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
