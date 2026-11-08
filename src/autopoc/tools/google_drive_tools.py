"""Google Drive file upload tool.

Uploads binary files (videos, images, etc.) to Google Drive using the
Google Drive API v3 with resumable upload support.

Uses the same service account credentials as the Google Docs upload tool.
No additional OAuth scopes are required — the existing `drive.file` scope
covers binary file uploads.
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import re
import tempfile
from pathlib import Path

from google.auth.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

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

    def __init__(self, credentials_path: str = "", *, credentials: Credentials | None = None):
        self.credentials_path = credentials_path
        self._credentials = credentials
        self._service = None

    @property
    def service(self):
        """Lazily initialize the Google Drive API service."""
        if self._service is None:
            credentials = self._credentials
            if credentials is None:
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
        file_id: str | None = None,
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
        if file_id:
            file_metadata["id"] = file_id
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
        # supportsAllDrives is required when uploading to Shared Drives.
        # Service accounts have no personal Drive quota, so all uploads
        # must target a Shared Drive folder.
        file = (
            self.service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink, size, mimeType",
                supportsAllDrives=True,
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

    def allocate_file_id(self) -> str:
        """Reserve an ID; callers must durably checkpoint it before uploading."""
        return self.service.files().generateIds(count=1, space="drive").execute()["ids"][0]

    def read_json(self, file_id: str) -> dict | None:
        """Read a bounded renderer journal object; a missing slot is still pending."""
        try:
            metadata = (
                self.service.files()
                .get(fileId=file_id, fields="size", supportsAllDrives=True)
                .execute()
            )
            size = int(metadata.get("size", -1))
            if not 0 <= size <= 1024 * 1024:
                raise ValueError("Journal object exceeds allowed size")
            raw = self.service.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
        except HttpError as exc:
            if exc.resp.status == 404:
                return None
            raise
        if not isinstance(raw, bytes) or len(raw) != size:
            raise ValueError("Journal object size mismatch")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TypeError("Expected a journal object")
        return value

    def download_file(
        self,
        file_id: str,
        destination: Path,
        expected_sha256: str,
        *,
        max_bytes: int = 256 * 1024 * 1024,
    ) -> Path:
        """Retrieve privately and expose only bytes matching the durable intent."""
        destination = Path(destination).absolute()
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256) or any(
            p.is_symlink() for p in (destination, *destination.parents)
        ):
            raise ValueError("Invalid download destination or integrity reference")
        if destination.exists():
            with destination.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() == expected_sha256:
                    return destination
            raise ValueError("Existing destination has different integrity identity")
        metadata = (
            self.service.files()
            .get(fileId=file_id, fields="size", supportsAllDrives=True)
            .execute()
        )
        size = int(metadata.get("size", -1))
        if not 0 <= size <= max_bytes:
            raise ValueError("Download exceeds allowed size")
        destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                request = self.service.files().get_media(fileId=file_id, supportsAllDrives=True)
                downloader = MediaIoBaseDownload(stream, request, chunksize=1024 * 1024)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                    if stream.tell() > size or stream.tell() > max_bytes:
                        raise ValueError("Download exceeds declared size")
                stream.flush()
                os.fsync(stream.fileno())
                with temporary.open("rb") as downloaded:
                    actual = hashlib.file_digest(downloaded, "sha256").hexdigest()
                if stream.tell() != size or actual != expected_sha256:
                    raise ValueError("Download integrity mismatch")
                os.link(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        return destination

    def upload_file_once(self, file_path: str, file_id: str, folder_id: str) -> dict:
        """Reconcile a caller-owned upload intent without creating duplicate files.

        MD5 is the Drive binary integrity field, not a security decision. The
        caller's durable intent also retains SHA-256 and the reserved file ID.
        """
        path = Path(file_path)
        if not path.is_file() or not file_id or not folder_id:
            raise ValueError("A file, reserved file ID and destination folder are required")
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "md5").hexdigest()
        with path.open("rb") as stream:
            sha256 = hashlib.file_digest(stream, "sha256").hexdigest()

        def retrieve() -> dict | None:
            try:
                metadata = (
                    self.service.files()
                    .get(
                        fileId=file_id,
                        fields="id,name,size,md5Checksum,parents,webViewLink,mimeType",
                        supportsAllDrives=True,
                    )
                    .execute()
                )
            except HttpError as exc:
                if exc.resp.status == 404:
                    return None
                raise
            if (
                metadata.get("md5Checksum") != checksum
                or int(metadata.get("size", -1)) != path.stat().st_size
                or folder_id not in metadata.get("parents", [])
            ):
                raise ValueError("Reserved Drive file has different content or destination")
            return {
                "file_id": metadata["id"],
                "file_name": metadata.get("name", path.name),
                "size_bytes": int(metadata["size"]),
                "mime_type": metadata.get("mimeType", "application/octet-stream"),
                "web_view_link": metadata.get("webViewLink", ""),
                "sha256": sha256,
            }

        existing = retrieve()
        if existing:
            return existing
        try:
            self.upload_file(
                str(path),
                folder_id=folder_id,
                file_id=file_id,
                mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            )
        except (HttpError, OSError):
            # A timeout/409 may mean the server completed the original upload.
            recovered = retrieve()
            if recovered:
                return recovered
            raise RuntimeError("Drive upload incomplete; retry the saved upload intent") from None
        verified = retrieve()
        if verified is None:
            raise RuntimeError("Drive upload could not be verified; retain the upload intent")
        return verified


def create_google_drive_service(credentials_path: str) -> GoogleDriveService:
    """Factory function for creating a GoogleDriveService.

    Args:
        credentials_path: Path to the Google service account credentials JSON.

    Returns:
        Configured GoogleDriveService instance.
    """
    return GoogleDriveService(credentials_path)
