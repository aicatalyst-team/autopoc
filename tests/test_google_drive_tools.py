"""Tests for Google Drive file upload tool."""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from autopoc.tools.google_drive_tools import GoogleDriveService, create_google_drive_service


def test_personal_oauth_upload_uses_explicit_local_credentials(tmp_path):
    """Local publishing can reuse user consent without a service-account key."""
    from google.oauth2.credentials import Credentials

    credentials = Credentials(
        token="test-only", scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    document = tmp_path / "summary.pdf"
    document.write_bytes(b"pdf content")
    with patch("autopoc.tools.google_drive_tools.build") as factory:
        factory.return_value.files.return_value.create.return_value.execute.return_value = {
            "id": "uploaded",
            "name": document.name,
            "size": "11",
            "webViewLink": "https://drive.google.com/file/d/uploaded/view",
        }
        service = GoogleDriveService(credentials=credentials)
        result = service.upload_file(str(document), folder_id="private-folder")
        assert result["file_id"] == "uploaded"
        factory.assert_called_once_with("drive", "v3", credentials=credentials)


def test_retry_reuses_verified_drive_file(tmp_path):
    """A retry after an ambiguous upload must recover the existing object."""
    video = tmp_path / "summary.mp4"
    video.write_bytes(b"recorded presentation")
    service = GoogleDriveService("unused")
    api = MagicMock()
    service._service = api
    api.files.return_value.get.return_value.execute.return_value = {
        "id": "reserved-id",
        "name": video.name,
        "size": str(video.stat().st_size),
        "md5Checksum": hashlib.md5(video.read_bytes()).hexdigest(),
        "parents": ["destination"],
        "webViewLink": "https://drive.google.com/file/d/reserved-id/view",
    }
    result = service.upload_file_once(str(video), "reserved-id", "destination")
    assert result["file_id"] == "reserved-id"
    assert result["sha256"] == hashlib.sha256(video.read_bytes()).hexdigest()
    assert not api.files.return_value.create.called


def test_retry_rejects_wrong_content_at_reserved_id(tmp_path):
    video = tmp_path / "summary.mp4"
    video.write_bytes(b"correct")
    service = GoogleDriveService("unused")
    api = MagicMock()
    service._service = api
    api.files.return_value.get.return_value.execute.return_value = {
        "id": "reserved-id",
        "size": "7",
        "md5Checksum": "wrong",
        "parents": ["folder"],
    }
    with pytest.raises(ValueError, match="content or destination"):
        service.upload_file_once(str(video), "reserved-id", "folder")


def test_unknown_upload_completion_recovers_reserved_object(tmp_path):
    from googleapiclient.errors import HttpError
    from httplib2 import Response

    pdf = tmp_path / "summary.pdf"
    pdf.write_bytes(b"pdf content")
    service = GoogleDriveService("unused")
    api = MagicMock()
    service._service = api
    api.files.return_value.get.return_value.execute.side_effect = [
        HttpError(Response({"status": "404"}), b"not found"),
        {
            "id": "reserved",
            "name": pdf.name,
            "size": "11",
            "md5Checksum": hashlib.md5(pdf.read_bytes()).hexdigest(),
            "parents": ["folder"],
        },
    ]
    api.files.return_value.create.return_value.execute.side_effect = TimeoutError()
    result = service.upload_file_once(str(pdf), "reserved", "folder")
    assert result["file_id"] == "reserved"
    assert api.files.return_value.create.call_args.kwargs["body"]["id"] == "reserved"


def test_download_checks_hash_before_exposing_file(tmp_path):

    data = b"sealed render inputs"
    service = GoogleDriveService("unused")
    service._service = MagicMock()
    service._service.files.return_value.get.return_value.execute.return_value = {
        "size": str(len(data))
    }

    class Downloader:
        def __init__(self, stream, request, chunksize):
            self.stream = stream

        def next_chunk(self):
            self.stream.write(data)
            return None, True

    destination = tmp_path / "inputs.zip"
    with patch("autopoc.tools.google_drive_tools.MediaIoBaseDownload", Downloader):
        service.download_file("id", destination, hashlib.sha256(data).hexdigest())
        assert destination.read_bytes() == data
        with pytest.raises(ValueError, match="integrity"):
            service.download_file("id", tmp_path / "bad.zip", "a" * 64)
    assert not (tmp_path / "bad.zip").exists()


class TestGoogleDriveService:
    """Tests for GoogleDriveService."""

    @patch("autopoc.tools.google_drive_tools.build")
    @patch("autopoc.tools.google_drive_tools.service_account.Credentials.from_service_account_file")
    def test_service_initialization(self, mock_creds, mock_build):
        """Test lazy service initialization."""
        service = GoogleDriveService("/fake/path")
        assert service._service is None

        # Access the property to trigger initialization
        _ = service.service
        mock_creds.assert_called_once()
        mock_build.assert_called_once_with("drive", "v3", credentials=mock_creds.return_value)

    @patch("autopoc.tools.google_drive_tools.build")
    @patch("autopoc.tools.google_drive_tools.service_account.Credentials.from_service_account_file")
    def test_service_cached(self, mock_creds, mock_build):
        """Test that service is initialized only once."""
        service = GoogleDriveService("/fake/path")
        _ = service.service
        _ = service.service
        mock_build.assert_called_once()

    def test_upload_file_not_found(self):
        """Test upload raises FileNotFoundError for missing files."""
        service = GoogleDriveService("/fake/path")
        with pytest.raises(FileNotFoundError):
            service.upload_file("/nonexistent/file.webm")

    def test_upload_unknown_mime_type(self, tmp_path):
        """Test upload raises ValueError for unknown MIME types."""
        test_file = tmp_path / "file.xyz123"
        test_file.write_text("test")
        service = GoogleDriveService("/fake/path")
        with pytest.raises(ValueError, match="Cannot determine MIME type"):
            service.upload_file(str(test_file))

    @patch("autopoc.tools.google_drive_tools.MediaFileUpload")
    @patch.object(GoogleDriveService, "service")
    def test_upload_file_success(self, mock_service, mock_media, tmp_path):
        """Test successful file upload."""
        test_file = tmp_path / "demo.webm"
        test_file.write_bytes(b"\x00" * 1024)

        mock_create = MagicMock()
        mock_create.execute.return_value = {
            "id": "file123",
            "name": "demo.webm",
            "webViewLink": "https://drive.google.com/file/d/file123/view",
            "size": "1024",
            "mimeType": "video/webm",
        }
        mock_service.files.return_value.create.return_value = mock_create

        service = GoogleDriveService("/fake/path")
        result = service.upload_file(str(test_file))

        assert result["file_id"] == "file123"
        assert result["web_view_link"] == "https://drive.google.com/file/d/file123/view"
        assert result["file_name"] == "demo.webm"
        assert result["size_bytes"] == 1024

        # Verify MediaFileUpload used resumable upload
        mock_media.assert_called_once_with(str(test_file), mimetype="video/webm", resumable=True)

    @patch("autopoc.tools.google_drive_tools.MediaFileUpload")
    @patch.object(GoogleDriveService, "service")
    def test_upload_supports_all_drives(self, mock_service, mock_media, tmp_path):
        """Test that supportsAllDrives=True is passed for Shared Drive compatibility."""
        test_file = tmp_path / "demo.webm"
        test_file.write_bytes(b"\x00" * 1024)

        mock_create = MagicMock()
        mock_create.execute.return_value = {
            "id": "file123",
            "name": "demo.webm",
            "webViewLink": "https://drive.google.com/file/d/file123/view",
            "size": "1024",
            "mimeType": "video/webm",
        }
        mock_service.files.return_value.create.return_value = mock_create

        service = GoogleDriveService("/fake/path")
        service.upload_file(str(test_file), folder_id="shared_folder_id")

        # Verify supportsAllDrives is passed
        mock_service.files.return_value.create.assert_called_once()
        call_kwargs = mock_service.files.return_value.create.call_args
        assert call_kwargs.kwargs.get("supportsAllDrives") is True

    @patch("autopoc.tools.google_drive_tools.MediaFileUpload")
    @patch.object(GoogleDriveService, "service")
    def test_upload_with_folder_id(self, mock_service, mock_media, tmp_path):
        """Test upload sets parents when folder_id is provided."""
        test_file = tmp_path / "demo.mp4"
        test_file.write_bytes(b"\x00" * 512)

        mock_create = MagicMock()
        mock_create.execute.return_value = {
            "id": "file456",
            "name": "demo.mp4",
            "size": "512",
            "mimeType": "video/mp4",
        }
        mock_service.files.return_value.create.return_value = mock_create

        service = GoogleDriveService("/fake/path")
        service.upload_file(str(test_file), folder_id="folder_abc")

        call_kwargs = mock_service.files.return_value.create.call_args
        body = call_kwargs.kwargs.get("body") or call_kwargs[1].get("body")
        assert body["parents"] == ["folder_abc"]

    @patch("autopoc.tools.google_drive_tools.MediaFileUpload")
    @patch.object(GoogleDriveService, "service")
    def test_upload_custom_file_name(self, mock_service, mock_media, tmp_path):
        """Test upload uses custom file_name when provided."""
        test_file = tmp_path / "demo.webm"
        test_file.write_bytes(b"\x00" * 256)

        mock_create = MagicMock()
        mock_create.execute.return_value = {
            "id": "file789",
            "name": "Custom Name",
            "size": "256",
            "mimeType": "video/webm",
        }
        mock_service.files.return_value.create.return_value = mock_create

        service = GoogleDriveService("/fake/path")
        result = service.upload_file(str(test_file), file_name="Custom Name")
        assert result["file_name"] == "Custom Name"

    def test_factory_function(self):
        """Test create_google_drive_service factory."""
        service = create_google_drive_service("/fake/path")
        assert isinstance(service, GoogleDriveService)
        assert service.credentials_path == "/fake/path"
