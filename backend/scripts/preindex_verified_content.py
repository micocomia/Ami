"""Pre-index verified course content into Azure AI Search via Blob Storage.

Uploads local PDF/PPTX/JSON/text files from ``resources/verified-course-content/``
to the ``ami-course-content`` Blob Storage container (preserving the
``{course_folder}/{category}/{filename}`` path structure), then triggers
``VerifiedContentManager.sync_verified_content()`` which computes a snapshot
hash from blob metadata and re-indexes when changed.

Run locally before deploying:

    conda activate ami-backend && cd backend
    python scripts/preindex_verified_content.py

Add ``--skip-upload`` to re-index without re-uploading (e.g. files already
in blob):

    python scripts/preindex_verified_content.py --skip-upload

Requires ``backend/.env`` with:
    OPENAI_API_KEY=...
    AZURE_SEARCH_ENDPOINT=https://<your-service>.search.windows.net
    AZURE_SEARCH_KEY=<your-admin-key>
    AZURE_STORAGE_CONNECTION_STRING=...
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
    AZURE_DOCUMENT_INTELLIGENCE_KEY=<your-key>
"""

import argparse
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
from base.blob_storage import BlobStorageClient
from base.verified_content_manager import VerifiedContentManager
from base.verified_content_loader import SKIP_FILES, SUPPORTED_EXTENSIONS, CONTENT_CATEGORIES


def upload_course_content(
    blob_client: BlobStorageClient,
    base_dir: str,
    course_content_container: str,
) -> int:
    """Walk ``base_dir`` and upload all supported files to blob storage.

    Preserves the ``{course_folder}/{category}/{filename}`` structure expected
    by ``VerifiedContentManager.index_verified_content()``.

    Returns the number of files uploaded.
    """
    base_path = Path(base_dir).resolve()
    if not base_path.is_dir():
        logger.warning(f"Base directory does not exist: {base_path}")
        return 0

    uploaded = 0
    for course_dir in sorted(base_path.iterdir()):
        if not course_dir.is_dir() or course_dir.name.startswith("."):
            continue

        for category in CONTENT_CATEGORIES:
            category_dir = course_dir / category
            if not category_dir.is_dir():
                continue

            for file_path in sorted(category_dir.rglob("*")):
                if not file_path.is_file():
                    continue
                if file_path.name in SKIP_FILES or file_path.name.startswith("."):
                    continue
                if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue

                # Blob name: {course_folder}/{category}/{filename}
                blob_name = f"{course_dir.name}/{category}/{file_path.name}"

                try:
                    data = file_path.read_bytes()
                    blob_client.upload(
                        course_content_container,
                        blob_name,
                        data,
                        content_type=_content_type(file_path.suffix.lower()),
                    )
                    logger.info(f"Uploaded: {blob_name}")
                    uploaded += 1
                except Exception as e:
                    logger.error(f"Failed to upload '{blob_name}': {e}")

    logger.info(f"Upload complete: {uploaded} file(s) → '{course_content_container}'")
    return uploaded


def _content_type(ext: str) -> str:
    return {
        ".pdf": "application/pdf",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".json": "application/json",
        ".py": "text/x-python",
        ".txt": "text/plain",
        ".md": "text/markdown",
    }.get(ext, "application/octet-stream")


def main():
    parser = argparse.ArgumentParser(description="Pre-index verified course content")
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip uploading local files; re-index using blobs already in storage",
    )
    parser.add_argument(
        "--base-dir",
        default="resources/verified-course-content",
        help="Local directory of verified course files (default: resources/verified-course-content)",
    )
    args = parser.parse_args()

    config = load_config()
    blob_cfg = config.get("blob_storage", {}) if hasattr(config, "get") else {}
    conn_str = (
        (blob_cfg.get("connection_string", "") if hasattr(blob_cfg, "get") else "")
        or os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
    )
    if not conn_str:
        logger.error("AZURE_STORAGE_CONNECTION_STRING is not set. Cannot upload or sync.")
        sys.exit(1)

    blob_client = BlobStorageClient(conn_str)
    course_content_container = (
        (blob_cfg.get("course_content_container", "ami-course-content") if hasattr(blob_cfg, "get") else "ami-course-content")
    )

    if not args.skip_upload:
        logger.info(f"Uploading files from '{args.base_dir}' → '{course_content_container}' ...")
        n_uploaded = upload_course_content(blob_client, args.base_dir, course_content_container)
        if n_uploaded == 0:
            logger.warning("No files were uploaded. Check that --base-dir contains course content.")

    logger.info("Initializing VerifiedContentManager ...")
    manager = VerifiedContentManager.from_config(config)

    logger.info("Starting sync (force=True) ...")
    result = manager.sync_verified_content(force=True)

    logger.info(f"Pre-index complete: {result}")
    if result.get("reindexed"):
        logger.info(
            f"Indexed {result.get('collection_count', '?')} documents into "
            f"'{manager.collection_name}'. Snapshot hash: {result.get('snapshot_hash', '?')}"
        )
    else:
        logger.info("No re-indexing needed (content unchanged).")


if __name__ == "__main__":
    main()
