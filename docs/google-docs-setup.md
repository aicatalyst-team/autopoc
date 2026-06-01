# Google Docs Integration Setup

The AutoPoC blog-create skill can automatically upload generated blog posts to Google Docs with a standardized template table. This feature is optional and requires Google service account credentials.

## Prerequisites

1. Google Cloud Project with Docs and Drive APIs enabled
2. Service account with appropriate permissions
3. Target Google Drive folder (optional)

## Setup Steps

### 1. Enable APIs

In your Google Cloud Console:

1. Go to APIs & Services > Library
2. Enable "Google Docs API"
3. Enable "Google Drive API"

### 2. Create Service Account

1. Go to IAM & Admin > Service Accounts
2. Click "Create Service Account"
3. Name: `autopoc-blog-docs`
4. Description: `AutoPoC blog post upload to Google Docs`
5. Click "Create and Continue"
6. No additional roles needed (we'll grant permissions directly to folders)
7. Click "Done"

### 3. Generate Credentials

1. Click on your new service account
2. Go to the "Keys" tab
3. Click "Add Key" > "Create new key"
4. Choose "JSON" format
5. Download the credentials file
6. Store it securely (e.g., `/path/to/autopoc-blog-docs-credentials.json`)

### 4. Configure Folder Permissions

1. Create a Google Drive folder for blog posts (optional but recommended)
2. Right-click the folder > Share
3. Add the service account email (from the JSON file) as an Editor
4. Copy the folder ID from the URL:
   ```
   https://drive.google.com/drive/folders/1ABC-DEF-GHI-FOLDER-ID-HERE
   ```

### 5. Environment Configuration

Add to your `.env` file:

```bash
# Google Docs integration (optional)
GOOGLE_DOCS_CREDENTIALS=/path/to/autopoc-blog-docs-credentials.json
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
- `GOOGLE_DOCS_CREDENTIALS` is not set
- Credentials file doesn't exist or is invalid
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