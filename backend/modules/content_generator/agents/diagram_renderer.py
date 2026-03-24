"""Render diagram code blocks (mermaid, plantuml, graphviz) to SVG via Kroki API,
upload to Azure Blob Storage, and replace code blocks with image references."""

import re
import uuid
from typing import Optional

KROKI_URL = "https://kroki.io"
SUPPORTED_TYPES = ["mermaid", "plantuml", "graphviz"]
_PATTERN = re.compile(
    r'```(' + '|'.join(SUPPORTED_TYPES) + r')\s*(.*?)\s*```',
    re.DOTALL | re.IGNORECASE,
)

_blob_client: Optional[object] = None
_diagrams_container: str = "ami-diagrams"


def _get_blob_client():
    global _blob_client
    if _blob_client is None:
        from base.blob_storage import BlobStorageClient
        _blob_client = BlobStorageClient.from_env()
    return _blob_client


def render_diagrams_in_markdown(text: str, base_url: str = "") -> str:
    """Find diagram code blocks and replace with rendered SVG image references.
    Falls back to the original block if the Kroki call fails (graceful degradation)."""
    import requests

    if not _PATTERN.search(text):
        return text   # fast path: no diagram blocks

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
            blob_url = _get_blob_client().upload(
                _diagrams_container, filename, resp.content, content_type="image/svg+xml"
            )
            return f"![Rendered diagram]({blob_url})"
        except Exception:
            return match.group(0)   # keep original block on failure

    return _PATTERN.sub(replace_block, text)
