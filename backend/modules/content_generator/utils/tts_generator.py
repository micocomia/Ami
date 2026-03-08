from __future__ import annotations

from modules.content_generator.agents.tts_generator import (
    AUDIO_DIR,
    BACKEND_ROOT,
    HOST_VOICE,
    VOICES,
    _generate_segments,
    _parse_dialogue_turns,
    _run_generate_segments,
    _strip_markdown,
    generate_tts_audio,
)

__all__ = [
    "VOICES",
    "HOST_VOICE",
    "BACKEND_ROOT",
    "AUDIO_DIR",
    "_strip_markdown",
    "_parse_dialogue_turns",
    "_generate_segments",
    "_run_generate_segments",
    "generate_tts_audio",
]
