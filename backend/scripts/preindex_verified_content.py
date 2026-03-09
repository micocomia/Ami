"""Pre-index verified course content into Azure AI Search.

Run this locally before deploying so container startup skips Docling+embedding work:

    conda activate ami-backend && cd backend
    python scripts/preindex_verified_content.py

Requires backend/.env with:
    OPENAI_API_KEY=...
    AZURE_SEARCH_ENDPOINT=https://<your-service>.search.windows.net
    AZURE_SEARCH_KEY=<your-admin-key>

The manifest is saved to data/vectorstore/ami-verified-content_manifest.json.
Commit this file to git (or mount via Azure Files volume) so container restarts
skip re-indexing.
"""

import logging
import os
import sys
from pathlib import Path

# Ensure backend/ is on the import path when running as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("preindex")

from config import load_config
from base.verified_content_manager import VerifiedContentManager


def main():
    config = load_config()
    base_dir = config.get("verified_content", {}).get("base_dir", "resources/verified-course-content")

    logger.info("Initializing VerifiedContentManager from config...")
    manager = VerifiedContentManager.from_config(config)

    logger.info(f"Starting pre-index of verified content from '{base_dir}' (force=True)...")
    result = manager.sync_verified_content(base_dir, force=True)

    logger.info(f"Pre-index complete: {result}")
    if result.get("reindexed"):
        logger.info(
            f"Indexed {result.get('collection_count', '?')} documents into "
            f"'{manager.collection_name}'. Manifest saved to {manager._manifest_path()}"
        )
    else:
        logger.info("No re-indexing needed (content unchanged).")


if __name__ == "__main__":
    main()
