"""Tests for Google Docs tools."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


from autopoc.tools.google_docs_tools import (
    GoogleDocsService,
    create_google_docs_service,
    extract_blog_metadata,
)


class TestGoogleDocsService:
    """Test GoogleDocsService class."""

    def test_init(self):
        """Test service initialization."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"type": "service_account", "project_id": "test"}')
            creds_path = f.name

        service = GoogleDocsService(creds_path)
        assert service.credentials_path == creds_path

        # Clean up
        Path(creds_path).unlink()

    @patch("autopoc.tools.google_docs_tools.service_account")
    @patch("autopoc.tools.google_docs_tools.build")
    def test_service_property(self, mock_build, mock_service_account):
        """Test service property creates the API service."""
        mock_creds = MagicMock()
        mock_service_account.Credentials.from_service_account_file.return_value = mock_creds
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"type": "service_account"}')
            creds_path = f.name

        service = GoogleDocsService(creds_path)

        # First call should create service
        result = service.service
        assert result == mock_service

        # Second call should return cached service
        result2 = service.service
        assert result2 == mock_service
        assert mock_build.call_count == 1

        # Clean up
        Path(creds_path).unlink()

    @patch.object(GoogleDocsService, "service")
    @patch.object(GoogleDocsService, "drive_service")
    def test_create_document(self, mock_drive_service, mock_service):
        """Test document creation."""
        # Mock the docs service
        mock_docs_create = MagicMock()
        mock_docs_create.execute.return_value = {"documentId": "test_doc_id"}
        mock_service.documents.return_value.create.return_value = mock_docs_create

        # Mock the drive service
        mock_drive_get = MagicMock()
        mock_drive_get.execute.return_value = {"parents": ["old_parent"]}
        mock_drive_service.files.return_value.get.return_value = mock_drive_get

        mock_drive_update = MagicMock()
        mock_drive_update.execute.return_value = {}
        mock_drive_service.files.return_value.update.return_value = mock_drive_update

        service = GoogleDocsService("/fake/path")

        # Test without parent folder
        doc_id = service.create_document("Test Document")
        assert doc_id == "test_doc_id"

        # Test with parent folder
        doc_id = service.create_document("Test Document", "parent_folder_id")
        assert doc_id == "test_doc_id"

        # Verify supportsAllDrives is passed for Shared Drive compatibility
        mock_drive_service.files.return_value.get.assert_called_with(
            fileId="test_doc_id", fields="parents", supportsAllDrives=True
        )
        mock_drive_service.files.return_value.update.assert_called_with(
            fileId="test_doc_id",
            addParents="parent_folder_id",
            removeParents="old_parent",
            fields="id, parents",
            supportsAllDrives=True,
        )

    def test_markdown_to_docs_requests(self):
        """Test markdown conversion to docs requests."""
        service = GoogleDocsService("/fake/path")

        markdown = """# Header 1

This is a paragraph.

## Header 2

Another paragraph with **bold** and *italic* text.

```python
code block
```"""

        requests = service.markdown_to_docs_requests(markdown)

        # Should have multiple requests for different content types
        assert len(requests) > 0

        # Check that we have insertText requests
        insert_requests = [r for r in requests if "insertText" in r]
        assert len(insert_requests) > 0

        # Check that we have formatting requests
        format_requests = [r for r in requests if "updateParagraphStyle" in r]
        assert len(format_requests) > 0

    @patch.object(GoogleDocsService, "service")
    def test_insert_template_table(self, mock_service):
        """Test template table insertion."""
        mock_batch_update = MagicMock()
        mock_batch_update.execute.return_value = {}
        mock_service.documents.return_value.batchUpdate.return_value = mock_batch_update

        service = GoogleDocsService("/fake/path")

        table_data = {"Title": "Test Blog Post", "Author": "Test Author"}

        service.insert_template_table("test_doc_id", table_data)

        # Should have called batchUpdate
        mock_batch_update.execute.assert_called_once()

    @patch.object(GoogleDocsService, "create_document")
    @patch.object(GoogleDocsService, "insert_template_table")
    @patch.object(GoogleDocsService, "service")
    def test_upload_blog_as_doc(self, mock_service, mock_insert_table, mock_create_doc):
        """Test full blog upload workflow."""
        # Setup mocks
        mock_create_doc.return_value = "test_doc_id"

        mock_batch_update = MagicMock()
        mock_batch_update.execute.return_value = {}
        mock_service.documents.return_value.batchUpdate.return_value = mock_batch_update

        # Create temporary markdown file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test Blog\n\nThis is a test blog post.")
            md_path = f.name

        service = GoogleDocsService("/fake/path")

        table_data = {"Title": "Test", "Author": "Test Author"}

        doc_url = service.upload_blog_as_doc(
            markdown_path=md_path, doc_title="Test Blog Post", table_data=table_data
        )

        assert doc_url == "https://docs.google.com/document/d/test_doc_id/edit"

        # Verify methods were called
        mock_create_doc.assert_called_once()
        mock_insert_table.assert_called_once()

        # Clean up
        Path(md_path).unlink()


def test_create_google_docs_service():
    """Test service factory function."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write('{"type": "service_account"}')
        creds_path = f.name

    service = create_google_docs_service(creds_path)
    assert isinstance(service, GoogleDocsService)
    assert service.credentials_path == creds_path

    # Clean up
    Path(creds_path).unlink()


def test_extract_blog_metadata():
    """Test blog metadata extraction."""
    markdown = """# Deploying FastAPI on OpenShift AI

This blog post shows how to deploy a FastAPI application on OpenShift AI using AutoPoC.

## Introduction

FastAPI is a modern web framework for building APIs with Python.

**Key benefits:**
- Fast performance
- Easy to use
- Great documentation"""

    metadata = extract_blog_metadata(markdown)

    assert metadata["Title"] == "Deploying FastAPI on OpenShift AI"
    assert metadata["Type"] == "Developer Blog Post"
    assert metadata["Status"] == "Draft"
    assert metadata["Author"] == "AutoPoC System"
    assert "FastAPI application" in metadata["Description"]
    assert metadata["Tags"] == "OpenShift AI, PoC, Deployment"


def test_extract_blog_metadata_no_title():
    """Test metadata extraction when no title is found."""
    markdown = "Just some content without a proper title."

    metadata = extract_blog_metadata(markdown)

    assert metadata["Title"] == "Blog Post"
    assert metadata["Description"] == "Just some content without a proper title."


def test_extract_blog_metadata_long_description():
    """Test metadata extraction with long description."""
    long_text = "A" * 300  # 300 character string
    markdown = f"# Test Title\n\n{long_text}"

    metadata = extract_blog_metadata(markdown)

    assert metadata["Title"] == "Test Title"
    assert len(metadata["Description"]) <= 203  # 200 chars + "..."
    assert metadata["Description"].endswith("...")
