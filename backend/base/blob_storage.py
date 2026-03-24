import os
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from azure.storage.blob import (
    BlobServiceClient,
    BlobProperties,
    BlobSasPermissions,
    ContentSettings,
    generate_blob_sas,
)
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

logger = logging.getLogger(__name__)


class BlobStorageClient:
    def __init__(self, connection_string: str):
        self._connection_string = connection_string
        self._client = BlobServiceClient.from_connection_string(connection_string)

    def _ensure_container(self, container: str) -> None:
        """Create container if it does not already exist."""
        try:
            self._client.get_container_client(container).create_container()
        except ResourceExistsError:
            pass
        except Exception as e:
            logger.warning(f"Could not ensure container '{container}': {e}")

    def upload(self, container: str, blob_name: str, data: bytes,
               content_type: str = "application/octet-stream") -> str:
        """Upload bytes to a blob container. Creates the container if needed. Returns the blob URL."""
        self._ensure_container(container)
        blob_client = self._client.get_blob_client(container=container, blob=blob_name)
        blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        return blob_client.url

    def download(self, container: str, blob_name: str) -> Optional[bytes]:
        """Download blob as bytes. Returns None if not found."""
        try:
            blob_client = self._client.get_blob_client(container=container, blob=blob_name)
            return blob_client.download_blob().readall()
        except ResourceNotFoundError:
            return None
        except Exception as e:
            logger.warning(f"Blob download failed ({container}/{blob_name}): {e}")
            return None

    def list_blobs(self, container: str) -> List[BlobProperties]:
        """List all blobs in a container. Returns [] if container does not exist or on error."""
        try:
            container_client = self._client.get_container_client(container)
            return list(container_client.list_blobs())
        except ResourceNotFoundError:
            logger.warning(f"Blob container '{container}' does not exist.")
            return []
        except Exception as e:
            logger.warning(f"Failed to list blobs in '{container}': {e}")
            return []

    def generate_sas_url(self, container: str, blob_name: str, expiry_hours: int = 1) -> str:
        """Generate a time-limited SAS URL for a blob.

        Parses AccountName and AccountKey from the connection string.
        Raises ValueError if the connection string does not contain an AccountKey
        (e.g. SAS-based or managed identity connection strings).
        """
        name_match = re.search(r"AccountName=([^;]+)", self._connection_string)
        key_match = re.search(r"AccountKey=([^;]+)", self._connection_string)
        if not name_match or not key_match:
            raise ValueError(
                "generate_sas_url requires a connection string with AccountName and AccountKey. "
                "SAS-based or managed-identity connection strings are not supported."
            )
        account_name = name_match.group(1)
        account_key = key_match.group(1)

        expiry = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
        )
        return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas_token}"

    @staticmethod
    def from_env() -> "BlobStorageClient":
        conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        if not conn_str:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING not set")
        return BlobStorageClient(conn_str)
