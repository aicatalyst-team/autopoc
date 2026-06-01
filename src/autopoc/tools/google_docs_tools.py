"""Google Docs tools for converting markdown to Google Docs.

This module provides functionality to:
1. Convert markdown content to Google Docs format
2. Create a new Google Doc with a specific table template
3. Upload blog posts as Google Docs
"""

import re
from pathlib import Path
from typing import Any

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleDocsService:
    """Service for interacting with Google Docs API."""

    def __init__(self, credentials_path: str):
        """Initialize Google Docs service with service account credentials.

        Args:
            credentials_path: Path to service account JSON credentials file
        """
        self.credentials_path = credentials_path
        self._service = None
        self._drive_service = None

    @property
    def service(self):
        """Get or create the Google Docs API service."""
        if self._service is None:
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=[
                        "https://www.googleapis.com/auth/documents",
                        "https://www.googleapis.com/auth/drive.file",
                    ],
                )
                self._service = build("docs", "v1", credentials=credentials)
            except Exception as e:
                raise GoogleAuthError(f"Failed to initialize Google Docs service: {e}")
        return self._service

    @property
    def drive_service(self):
        """Get or create the Google Drive API service."""
        if self._drive_service is None:
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=[
                        "https://www.googleapis.com/auth/documents",
                        "https://www.googleapis.com/auth/drive.file",
                    ],
                )
                self._drive_service = build("drive", "v3", credentials=credentials)
            except Exception as e:
                raise GoogleAuthError(f"Failed to initialize Google Drive service: {e}")
        return self._drive_service

    def create_document(self, title: str, parent_folder_id: str | None = None) -> str:
        """Create a new Google Doc.

        Args:
            title: Title for the new document
            parent_folder_id: Optional parent folder ID to create doc in

        Returns:
            Document ID of the created document
        """
        try:
            # Create the document
            document = {"title": title}
            doc = self.service.documents().create(body=document).execute()
            doc_id = doc.get("documentId")

            # Move to parent folder if specified
            if parent_folder_id:
                # Get the current file
                file = self.drive_service.files().get(fileId=doc_id, fields="parents").execute()
                previous_parents = ",".join(file.get("parents"))

                # Move to new parent
                self.drive_service.files().update(
                    fileId=doc_id,
                    addParents=parent_folder_id,
                    removeParents=previous_parents,
                    fields="id, parents",
                ).execute()

            return doc_id
        except HttpError as e:
            raise RuntimeError(f"Failed to create Google Doc: {e}")

    def get_template_structure(self, template_doc_id: str) -> dict[str, Any]:
        """Get the structure of a template document.

        Args:
            template_doc_id: Document ID of the template

        Returns:
            Dictionary containing template structure information
        """
        try:
            doc = self.service.documents().get(documentId=template_doc_id).execute()

            # Extract table structure and styling information
            template_info = {
                "title": doc.get("title", ""),
                "body": doc.get("body", {}),
                "document_style": doc.get("documentStyle", {}),
                "tables": [],
            }

            # Find tables in the document
            body = doc.get("body", {})
            content = body.get("content", [])

            for element in content:
                if "table" in element:
                    table = element["table"]
                    table_info = {
                        "rows": table.get("rows", 0),
                        "columns": table.get("columns", 0),
                        "table_style": table.get("tableStyle", {}),
                        "table_rows": [],
                    }

                    # Extract row structure
                    for row in table.get("tableRows", []):
                        row_info = {"cells": []}
                        for cell in row.get("tableCells", []):
                            cell_content = []
                            for content_elem in cell.get("content", []):
                                if "paragraph" in content_elem:
                                    paragraph = content_elem["paragraph"]
                                    elements = paragraph.get("elements", [])
                                    text_parts = []
                                    for elem in elements:
                                        text_run = elem.get("textRun")
                                        if text_run:
                                            text_parts.append(text_run.get("content", ""))
                                    cell_content.append("".join(text_parts))
                            row_info["cells"].append(cell_content)
                        table_info["table_rows"].append(row_info)

                    template_info["tables"].append(table_info)

            return template_info
        except HttpError as e:
            raise RuntimeError(f"Failed to get template structure: {e}")

    def markdown_to_docs_requests(self, markdown_content: str) -> list[dict[str, Any]]:
        """Convert markdown content to Google Docs API requests.

        Args:
            markdown_content: Markdown content to convert

        Returns:
            List of requests to insert into Google Doc
        """
        requests = []
        current_index = 1  # Start after document title

        # Split content into lines for processing
        lines = markdown_content.split("\n")

        for line in lines:
            line = line.rstrip()

            if not line:
                # Empty line - insert paragraph break
                requests.append(
                    {"insertText": {"location": {"index": current_index}, "text": "\n"}}
                )
                current_index += 1
                continue

            # Handle headers
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                text = line.lstrip("#").strip()

                # Insert header text
                requests.append(
                    {"insertText": {"location": {"index": current_index}, "text": text + "\n"}}
                )

                # Apply header formatting
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {
                                "startIndex": current_index,
                                "endIndex": current_index + len(text),
                            },
                            "paragraphStyle": {"namedStyleType": f"HEADING_{min(level, 6)}"},
                            "fields": "namedStyleType",
                        }
                    }
                )

                current_index += len(text) + 1

            # Handle code blocks
            elif line.startswith("```"):
                # This is a simplified handling - in a full implementation
                # you'd need to handle the entire code block
                requests.append(
                    {"insertText": {"location": {"index": current_index}, "text": line + "\n"}}
                )
                current_index += len(line) + 1

            # Handle regular paragraphs
            else:
                # Convert basic markdown formatting
                text = self._convert_inline_formatting(line)

                requests.append(
                    {"insertText": {"location": {"index": current_index}, "text": text + "\n"}}
                )

                # Apply formatting for bold/italic if needed
                # This is simplified - would need more complex parsing for mixed formatting
                current_index += len(text) + 1

        return requests

    def _convert_inline_formatting(self, text: str) -> str:
        """Convert basic inline markdown formatting to plain text.

        Note: This is a simplified conversion. For full formatting support,
        you would need to track formatting ranges and apply them separately.

        Args:
            text: Text with markdown formatting

        Returns:
            Plain text (formatting info would be applied separately)
        """
        # Remove markdown formatting for now - in a full implementation
        # you'd track these ranges and apply formatting via API
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # Bold
        text = re.sub(r"\*(.*?)\*", r"\1", text)  # Italic
        text = re.sub(r"`(.*?)`", r"\1", text)  # Code
        return text

    def insert_template_table(self, doc_id: str, table_data: dict[str, str]) -> None:
        """Insert a template table at the beginning of the document.

        Args:
            doc_id: Google Doc ID
            table_data: Dictionary with table field values
        """
        try:
            # Define the table structure based on the template
            # This creates a 2-column table with key-value pairs
            table_requests = []

            # Insert table
            table_requests.append(
                {"insertTable": {"location": {"index": 1}, "rows": len(table_data), "columns": 2}}
            )

            # Add content to table cells
            row_index = 0
            for key, value in table_data.items():
                # Insert key in first column
                table_requests.append(
                    {
                        "insertText": {
                            "location": {
                                "index": 3 + row_index * 4
                            },  # Simplified index calculation
                            "text": key,
                        }
                    }
                )

                # Insert value in second column
                table_requests.append(
                    {
                        "insertText": {
                            "location": {
                                "index": 5 + row_index * 4
                            },  # Simplified index calculation
                            "text": str(value),
                        }
                    }
                )

                row_index += 1

            # Execute all table requests
            self.service.documents().batchUpdate(
                documentId=doc_id, body={"requests": table_requests}
            ).execute()

        except HttpError as e:
            raise RuntimeError(f"Failed to insert template table: {e}")

    def upload_blog_as_doc(
        self,
        markdown_path: str,
        doc_title: str,
        parent_folder_id: str | None = None,
        table_data: dict[str, str] | None = None,
    ) -> str:
        """Upload a markdown blog post as a Google Doc.

        Args:
            markdown_path: Path to markdown file
            doc_title: Title for the Google Doc
            parent_folder_id: Optional parent folder ID
            table_data: Optional table data to insert at top

        Returns:
            Google Doc URL
        """
        try:
            # Read markdown content
            markdown_content = Path(markdown_path).read_text(encoding="utf-8")

            # Create new document
            doc_id = self.create_document(doc_title, parent_folder_id)

            # Insert template table if provided
            if table_data:
                self.insert_template_table(doc_id, table_data)

                # Add some space after table
                self.service.documents().batchUpdate(
                    documentId=doc_id,
                    body={
                        "requests": [
                            {
                                "insertText": {
                                    "location": {"index": -1},  # End of document
                                    "text": "\n\n",
                                }
                            }
                        ]
                    },
                ).execute()

            # Convert markdown to doc requests
            requests = self.markdown_to_docs_requests(markdown_content)

            # Apply content to document in batches (API has limits)
            batch_size = 50
            for i in range(0, len(requests), batch_size):
                batch = requests[i : i + batch_size]
                self.service.documents().batchUpdate(
                    documentId=doc_id, body={"requests": batch}
                ).execute()

            # Return document URL
            return f"https://docs.google.com/document/d/{doc_id}/edit"

        except Exception as e:
            raise RuntimeError(f"Failed to upload blog as Google Doc: {e}")


def create_google_docs_service(credentials_path: str) -> GoogleDocsService:
    """Create a Google Docs service instance.

    Args:
        credentials_path: Path to service account credentials JSON

    Returns:
        GoogleDocsService instance
    """
    return GoogleDocsService(credentials_path)


def extract_blog_metadata(markdown_content: str) -> dict[str, str]:
    """Extract metadata from blog markdown for the template table.

    Args:
        markdown_content: Blog post markdown content

    Returns:
        Dictionary with metadata for template table
    """
    # Extract title (first H1)
    title_match = re.search(r"^#\s+(.+)$", markdown_content, re.MULTILINE)
    title = title_match.group(1) if title_match else "Blog Post"

    # Extract first paragraph as description
    lines = markdown_content.split("\n")
    description = ""
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("```"):
            # Clean up markdown formatting for description
            clean_line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
            clean_line = re.sub(r"\*(.*?)\*", r"\1", clean_line)
            clean_line = re.sub(r"`(.*?)`", r"\1", clean_line)
            description = clean_line[:200] + ("..." if len(clean_line) > 200 else "")
            break

    # Create template table data
    table_data = {
        "Title": title,
        "Type": "Developer Blog Post",
        "Status": "Draft",
        "Author": "AutoPoC System",
        "Description": description,
        "Tags": "OpenShift AI, PoC, Deployment",
    }

    return table_data
