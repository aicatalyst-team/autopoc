"""Tests for Google Docs CLI tool."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


from autopoc.cli_tools import cmd_google_docs_upload


class TestGoogleDocsUploadCLI:
    """Test the google-docs-upload CLI command."""

    @patch("autopoc.cli_tools._load_config")
    @patch("autopoc.tools.google_docs_tools.create_google_docs_service")
    @patch("autopoc.tools.google_docs_tools.extract_blog_metadata")
    def test_google_docs_upload_success(
        self, mock_extract_metadata, mock_create_service, mock_load_config
    ):
        """Test successful Google Docs upload."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.sheet_credentials = "/fake/credentials.json"
        mock_config.google_docs_folder_id = "fake-folder-id"
        mock_load_config.return_value = mock_config

        mock_extract_metadata.return_value = {
            "Title": "Test Blog Post",
            "Type": "Developer Blog Post",
        }

        mock_service = MagicMock()
        mock_service.upload_blog_as_doc.return_value = (
            "https://docs.google.com/document/d/fake-doc-id"
        )
        mock_create_service.return_value = mock_service

        # Create temporary markdown file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test Blog\n\nThis is a test.")
            md_path = f.name

        # Mock the file existence checks
        with patch("autopoc.cli_tools.Path") as mock_path_class:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = "# Test Blog\n\nThis is a test."
            mock_path_class.return_value = mock_path

            # Create args namespace
            args = MagicMock()
            args.markdown_file = md_path
            args.project_name = "test-project"
            args.credentials = None
            args.folder_id = None

            # Capture stdout
            with patch("builtins.print") as mock_print:
                cmd_google_docs_upload(args)

                # Verify the output
                mock_print.assert_called_once()
                output = mock_print.call_args[0][0]
                result = json.loads(output)

                assert result["success"] is True
                assert result["doc_url"] == "https://docs.google.com/document/d/fake-doc-id"
                assert result["doc_title"] == "[AutoPoC] Test Blog Post Blog Post"

        # Clean up
        Path(md_path).unlink()

    @patch("autopoc.cli_tools._load_config")
    def test_google_docs_upload_no_credentials(self, mock_load_config):
        """Test upload fails gracefully when no credentials available."""
        # Setup mock config with no credentials
        mock_config = MagicMock()
        mock_config.sheet_credentials = None
        mock_load_config.return_value = mock_config

        args = MagicMock()
        args.credentials = None

        # Should exit with error
        with patch("sys.exit") as mock_exit, patch("builtins.print") as mock_print:
            cmd_google_docs_upload(args)
            mock_exit.assert_called_with(1)
            # Check error message was printed to stderr
            mock_print.assert_called()

    @patch("autopoc.cli_tools._load_config")
    def test_google_docs_upload_missing_file(self, mock_load_config):
        """Test upload fails when markdown file doesn't exist."""
        mock_config = MagicMock()
        mock_config.sheet_credentials = "/fake/credentials.json"
        mock_load_config.return_value = mock_config

        with patch("autopoc.cli_tools.Path") as mock_path_class:
            # Mock credentials exist but markdown file doesn't
            def path_exists_side_effect(path):
                mock_path = MagicMock()
                if "credentials.json" in str(path):
                    mock_path.exists.return_value = True
                else:
                    mock_path.exists.return_value = False
                return mock_path

            mock_path_class.side_effect = path_exists_side_effect

            args = MagicMock()
            args.markdown_file = "/nonexistent/file.md"
            args.credentials = None

            with patch("sys.exit") as mock_exit, patch("builtins.print"):
                cmd_google_docs_upload(args)
                mock_exit.assert_called_with(1)

    @patch("autopoc.cli_tools._load_config")
    @patch("autopoc.tools.google_docs_tools.create_google_docs_service")
    def test_google_docs_upload_service_error(self, mock_create_service, mock_load_config):
        """Test upload handles service errors gracefully."""
        mock_config = MagicMock()
        mock_config.sheet_credentials = "/fake/credentials.json"
        mock_load_config.return_value = mock_config

        # Mock service to raise an error
        mock_create_service.side_effect = Exception("API error")

        # Create temporary markdown file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test")
            md_path = f.name

        with patch("autopoc.cli_tools.Path") as mock_path_class:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path_class.return_value = mock_path

            args = MagicMock()
            args.markdown_file = md_path
            args.project_name = "test"
            args.credentials = None
            args.folder_id = None

            with patch("sys.exit") as mock_exit, patch("builtins.print"):
                cmd_google_docs_upload(args)
                mock_exit.assert_called_with(1)

        # Clean up
        Path(md_path).unlink()
