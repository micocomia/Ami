"""Motivational message generation for learning session triggers."""
from __future__ import annotations

from typing import Dict, Tuple

_ENCOURAGEMENT_DIM_ORDER: Tuple[str, ...] = (
    "fslsm_processing",
    "fslsm_perception",
    "fslsm_input",
    "fslsm_understanding",
)

_POSTURE_MESSAGES: Tuple[str, ...] = (
    "Take a moment to stretch and refill your water.",
    "Stay hydrated and check your posture — sit tall!",
    "Quick break: roll your shoulders back and take a deep breath.",
)

_ENCOURAGEMENT_MESSAGES: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "fslsm_processing": {
        "low": (   # active
            "Try applying what you just read to a quick example — it'll make the idea stick.",
            "Challenge yourself: can you explain this concept in your own words right now?",
        ),
        "neutral": (
            "You're making steady progress — keep the momentum going!",
            "Great work so far. Stay focused and keep pushing forward.",
        ),
        "high": (  # reflective
            "Take a moment to review your notes — connecting the dots is where real learning happens.",
            "Pause and reflect: what's the most important idea you've encountered today?",
        ),
    },
    "fslsm_perception": {
        "low": (   # sensing
            "Look for a concrete example of this concept — grounding ideas in facts makes them memorable.",
            "Think about where you've seen this in real life. Connecting theory to practice builds mastery.",
        ),
        "neutral": (
            "You're doing great — stay curious and keep exploring!",
            "Solid effort! Every concept you learn is a building block toward your goal.",
        ),
        "high": (  # intuitive
            "See if you can spot the bigger pattern here — intuitive thinkers often unlock insights others miss.",
            "Trust your instincts: what does this idea connect to that you already know?",
        ),
    },
    "fslsm_input": {
        "low": (   # visual
            "Try sketching a quick diagram of what you just learned — a picture is worth a thousand words.",
            "Picture the concept as a flowchart or map. Visual structure can make abstract ideas click.",
        ),
        "neutral": (
            "Keep it up — you're building real knowledge with every session.",
            "Excellent focus! You're on track to reach your learning goal.",
        ),
        "high": (  # verbal
            "Try summarising what you just read in a single clear sentence — writing it out deepens understanding.",
            "Reading through your notes or talking through the concept aloud can really lock it in.",
        ),
    },
    "fslsm_understanding": {
        "low": (   # sequential
            "You're working through this step by step — that methodical approach is exactly how mastery is built.",
            "Stick with the sequence: each step you complete is solid ground for the next.",
        ),
        "neutral": (
            "Fantastic effort — you're making this material your own!",
            "Stay with it — the work you're doing right now is exactly what growth looks like.",
        ),
        "high": (  # global
            "Step back for a second: how does everything you've learned today fit together as a whole?",
            "Global thinkers like you shine when you see the big picture — zoom out and connect the ideas.",
        ),
    },
}


def pick_motivational_message(
    kind: str,
    fslsm_dims: Dict[str, float],
    trigger_index: int,
) -> str:
    """Return a motivational message personalised by FSLSM dimensions.

    Args:
        kind: "posture" or "encouragement".
        fslsm_dims: FSLSM scores in [-1.0, 1.0]. Empty or None -> neutral fallback.
        trigger_index: 0-based per-kind trigger count (trigger_count // 2).
                       Used to cycle through message variants.
    """
    if kind == "posture":
        return _POSTURE_MESSAGES[trigger_index % len(_POSTURE_MESSAGES)]

    dim_key = _ENCOURAGEMENT_DIM_ORDER[trigger_index % len(_ENCOURAGEMENT_DIM_ORDER)]
    score = float((fslsm_dims or {}).get(dim_key, 0.0) or 0.0)

    if score < -0.3:
        band = "low"
    elif score > 0.3:
        band = "high"
    else:
        band = "neutral"

    variants = _ENCOURAGEMENT_MESSAGES[dim_key][band]
    # On the second pass through the same dimension, use the alternate variant.
    variant_index = (trigger_index // len(_ENCOURAGEMENT_DIM_ORDER)) % len(variants)
    return variants[variant_index]
