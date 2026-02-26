from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

VOICES = ["en-US-JennyNeural", "en-US-GuyNeural"]
HOST_VOICE = VOICES[0]
AUDIO_DIR = Path("data/audio")


def _strip_markdown(text: str) -> str:
    """Remove markdown symbols for clean TTS input."""
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)          # bold
    text = re.sub(r'#{1,6}\s', '', text)                   # headings
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # links
    text = re.sub(r'<[^>]+>', '', text)                    # HTML tags
    text = re.sub(r'[`*_]', '', text)                      # misc
    return text.strip()


def _parse_dialogue_turns(document: str) -> list:
    """Split **[SPEAKER]**: ... turns into (speaker, clean_text) pairs."""
    pattern = re.compile(r'\*\*\[(\w+)\]\*\*:[ \t]*(.*?)(?=\n\*\*\[|\Z)', re.DOTALL)
    turns = pattern.findall(document)
    return [
        (spk.upper(), _strip_markdown(txt.strip()))
        for spk, txt in turns
        if txt.strip()
    ]


async def _generate_segments(turns, tmp_dir: Path, voice_map: dict):
    import edge_tts
    paths = []
    for i, (speaker, text) in enumerate(turns):
        voice = voice_map.get(speaker, HOST_VOICE)
        path = tmp_dir / f"turn_{i:04d}.mp3"
        await edge_tts.Communicate(text, voice).save(str(path))
        paths.append(path)
    return paths


def _run_generate_segments(turns, tmp_dir: Path, voice_map: dict):
    """Run async segment generation from both sync and async call contexts."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_generate_segments(turns, tmp_dir, voice_map))

    from concurrent.futures import ThreadPoolExecutor

    def _runner():
        return asyncio.run(_generate_segments(turns, tmp_dir, voice_map))

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_runner).result()


def generate_tts_audio(document: str) -> str:
    """Parse dialogue turns, generate per-turn MP3s with dual voices,
    concatenate bytes, save to data/audio/, return /static/audio/ URL.

    Args:
        document: Markdown document with **[HOST]**: / **[EXPERT]**: dialogue turns.

    Returns:
        URL string of the form /static/audio/<filename>.mp3
    """
    import tempfile
    import random

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    turns = _parse_dialogue_turns(document)
    if not turns:
        turns = [("HOST", _strip_markdown(document))]

    shuffled = random.sample(VOICES, 2)
    voice_map = {"HOST": shuffled[0], "EXPERT": shuffled[1]}

    filename = f"{uuid.uuid4().hex}.mp3"
    output_path = AUDIO_DIR / filename

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        seg_paths = _run_generate_segments(turns, tmp_dir, voice_map)
        with open(output_path, "wb") as out:
            for seg in seg_paths:
                out.write(seg.read_bytes())

    return f"/static/audio/{filename}"
