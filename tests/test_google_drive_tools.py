"""Tests for Google Drive file upload tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autopoc.tools.google_drive_tools import GoogleDriveService, create_google_drive_service


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
