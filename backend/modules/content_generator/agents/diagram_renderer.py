"""Render diagram code blocks (mermaid, plantuml, graphviz) to SVG via Kroki API,
store as static files, and replace code blocks with image references."""

import re
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
DIAGRAM_DIR = BACKEND_ROOT / "data" / "diagrams"
KROKI_URL = "https://kroki.io"
SUPPORTED_TYPES = ["mermaid", "plantuml", "graphviz"]
_PATTERN = re.compile(
    r'```(' + '|'.join(SUPPORTED_TYPES) + r')\s*(.*?)\s*```',
    re.DOTALL | re.IGNORECASE,
)


def render_diagrams_in_markdown(text: str, base_url: str = "/static/diagrams") -> str:
    """Find diagram code blocks and replace with rendered SVG image references.
    Falls back to the original block if the Kroki call fails (graceful degradation)."""
    import requests

    if not _PATTERN.search(text):
        return text   # fast path: no diagram blocks

    DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)

    def replace_block(match):
        diagram_type = match.group(1).strip().lower()
        code = match.group(2).strip()
        try:
            resp = requests.post(
                f"{KROKI_URL}/{diagram_type}/svg",
                data=code.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
                timeout=15,
            )
            resp.raise_for_status()
            filename = f"{uuid.uuid4().hex}.svg"
            (DIAGRAM_DIR / filename).write_bytes(resp.content)
            static_url = f"{base_url.rstrip('/')}/{filename}"
            return f"![Rendered diagram]({static_url})"
        except Exception:
            return match.group(0)   # keep original block on failure

    return _PATTERN.sub(replace_block, text)
