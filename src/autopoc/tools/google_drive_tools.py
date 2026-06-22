"""Google Drive file upload tool.

Uploads binary files (videos, images, etc.) to Google Drive using the
Google Drive API v3 with resumable upload support.

Uses the same service account credentials as the Google Docs upload tool.
No additional OAuth scopes are required — the existing `drive.file` scope
covers binary file uploads.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

# MIME type mapping for common video formats
VIDEO_MIME_TYPES = {
    ".webm": "video/webm",
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
}

# Scopes required for Google Drive file operations.
# drive.file is sufficient for creating and managing files that the app owns.
DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]


class GoogleDriveService:
    """Service for uploading files to Google Drive."""

    def __init__(self, credentials_path: str):
        self.credentials_path = credentials_path
        self._service = None

    @property
    def service(self):
        """Lazily initialize the Google Drive API service."""
        if self._service is None:
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=DRIVE_SCOPES,
            )
            self._service = build("drive", "v3", credentials=credentials)
            logger.debug("Google Drive service initialized")
        return self._service

    def upload_file(
        self,
        file_path: str,
        file_name: str | None = None,
        folder_id: str | None = None,
        mime_type: str | None = None,
    ) -> dict:
        """Upload a file to Google Drive.

        Uses resumable upload for reliability with large files (videos).

        Args:
            file_path: Local path to the file to upload.
            file_name: Name for the file in Google Drive. Defaults to the
                local filename.
            folder_id: Google Drive folder ID to upload to. If None, uploads
                to the service account's root Drive folder.
            mime_type: MIME type of the file. Auto-detected from extension
                if not provided.

        Returns:
            dict with keys: file_id, web_view_link, file_name, size_bytes.

        Raises:
            FileNotFoundError: If the local file doesn't exist.
            ValueError: If MIME type can't be determined.
            googleapiclient.errors.HttpError: On API errors.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Determine file name
        if file_name is None:
            file_name = path.name

        # Determine MIME type
        if mime_type is None:
            mime_type = VIDEO_MIME_TYPES.get(path.suffix.lower())
            if mime_type is None:
                mime_type, _ = mimetypes.guess_type(str(path))
            if mime_type is None:
                raise ValueError(
                    f"Cannot determine MIME type for {path.suffix}. Provide mime_type explicitly."
                )

        # Build file metadata
        file_metadata: dict = {"name": file_name}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        # Create resumable upload
        media = MediaFileUpload(
            str(path),
            mimetype=mime_type,
            resumable=True,
        )

        logger.info(
            "Uploading %s (%s, %.1f MB) to Google Drive",
            file_name,
            mime_type,
            path.stat().st_size / (1024 * 1024),
        )

        # Execute the upload
        file = (
            self.service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink, size, mimeType",
            )
            .execute()
        )

        result = {
            "file_id": file["id"],
            "web_view_link": file.get("webViewLink", ""),
            "file_name": file["name"],
            "size_bytes": int(file.get("size", 0)),
            "mime_type": file.get("mimeType", mime_type),
        }

        logger.info("Upload complete: %s → %s", file_name, result["web_view_link"])
        return result


def create_google_drive_service(credentials_path: str) -> GoogleDriveService:
    """Factory function for creating a GoogleDriveService.

    Args:
        credentials_path: Path to the Google service account credentials JSON.

    Returns:
        Configured GoogleDriveService instance.
    """
    return GoogleDriveService(credentials_path)
