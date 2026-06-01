# Google Docs Integration Setup

The AutoPoC blog-create skill can automatically upload generated blog posts to Google Docs with a standardized template table. This feature is optional and uses the same Google service account credentials as the sheet integration feature.

## Prerequisites

1. Existing Google service account with Sheet, Docs and Drive API access (same as used for sheet integration)
2. Target Google Drive folder (optional)

## Setup Steps

### 1. Verify API Access

Ensure your existing Google service account (used for `AUTOPOC_SHEET_CREDENTIALS`) has access to:
- Google Sheets API (already enabled for sheet integration)  
- Google Docs API (needs to be enabled)
- Google Drive API (needs to be enabled)

In your Google Cloud Console:
1. Go to APIs & Services > Library
2. Enable "Google Docs API" (if not already enabled)
3. Enable "Google Drive API" (if not already enabled)

### 2. No New Service Account Needed

The Google Docs integration reuses the existing service account configured via `AUTOPOC_SHEET_CREDENTIALS`. No additional credentials are needed.

### 3. Configure Folder Permissions

1. Create a Google Drive folder for blog posts (optional but recommended)
2. Right-click the folder > Share
3. Add the service account email (from the existing credentials JSON file used for sheets) as an Editor
4. Copy the folder ID from the URL:
   ```
   https://drive.google.com/drive/folders/1ABC-DEF-GHI-FOLDER-ID-HERE
   ```

### 4. Environment Configuration

Add to your `.env` file (the service account credentials are already configured via `AUTOPOC_SHEET_CREDENTIALS`):

```bash
# Google Docs integration (optional)
# Uses existing AUTOPOC_SHEET_CREDENTIALS for authentication
GOOGLE_DOCS_FOLDER_ID=1ABC-DEF-GHI-FOLDER-ID-HERE  # optional
```

## Usage

When properly configured, the blog-create skill will automatically:

1. Create a new Google Doc for each blog post
2. Insert a metadata table at the top with:
   - Title
   - Type (Developer Blog Post)
   - Status (Draft)
   - Author (AutoPoC System)
   - Description (excerpt)
   - Tags (OpenShift AI, PoC, Deployment)
3. Convert the markdown content to Google Docs format
4. Place the document in the specified folder (if configured)
5. Return the Google Docs URL

## Template Structure

The generated Google Doc includes a standardized table based on the template:
https://docs.google.com/document/d/1my7gbY0USazBvK_J9RWOKw2xtQj85gkenmR-9uQSWf0

| Field | Value |
|-------|-------|
| Title | Extracted from markdown H1 |
| Type | Developer Blog Post |
| Status | Draft |
| Author | AutoPoC System |
| Description | First paragraph excerpt |
| Tags | OpenShift AI, PoC, Deployment |

## Troubleshooting

### Permission Errors

If you get permission errors:
1. Verify the service account email has Editor access to the target folder
2. Check that the APIs are enabled in your Google Cloud project
3. Ensure the credentials file path is correct and readable

### API Errors

If you get Google API errors:
1. Check your credentials file format (should be valid JSON)
2. Verify the service account key is not expired
3. Confirm the folder ID is correct (if specified)

### Feature Not Working

The Google Docs feature is optional and will be skipped if:
- `AUTOPOC_SHEET_CREDENTIALS` is not set
- Credentials file doesn't exist or is invalid
- Service account doesn't have Docs/Drive API access
- API calls fail (errors are logged but don't stop the blog creation process)

Check the logs for error messages starting with "⚠️ Failed to upload to Google Docs".

## Markdown Conversion

The tool converts common markdown elements to Google Docs format:

- **Headers** (H1-H6) → Google Docs heading styles
- **Bold/italic** text → Formatted text
- **Code blocks** → Monospace text
- **Paragraphs** → Standard paragraphs
- **Lists** → Google Docs lists

Note: Complex formatting like tables or inline images may require manual adjustment in the Google Doc.