#!/usr/bin/env python3
"""
Example of using the Google Docs integration CLI tool.

This script demonstrates how to use the external CLI tool for uploading blog posts
to Google Docs (now separate from the blog-create skill).
"""

import tempfile
from pathlib import Path

from autopoc.config import load_config
from autopoc.tools.google_docs_tools import create_google_docs_service, extract_blog_metadata


def example_blog_to_google_docs():
    """Example of converting a blog post to Google Docs using the CLI tool."""
    
    # Example blog post content
    blog_content = """# Deploying FastAPI on OpenShift AI

This blog post demonstrates how to deploy a FastAPI application on Red Hat OpenShift AI using the AutoPoC pipeline.

## What is FastAPI?

FastAPI is a modern, fast (high-performance), web framework for building APIs with Python 3.7+ based on standard Python type hints.

### Key Benefits

- **Fast**: Very high performance, on par with NodeJS and Go
- **Fast to code**: Increase the speed to develop features by about 200% to 300%
- **Fewer bugs**: Reduce about 40% of human (developer) induced errors
- **Intuitive**: Great editor support with autocompletion

## Deployment Process

Our AutoPoC system automates the entire deployment process:

1. **Repository Analysis**: Clone and analyze the FastAPI repository
2. **Containerization**: Generate UBI-based Dockerfiles
3. **Build**: Create container images using Podman or OpenShift builds  
4. **Deploy**: Generate Kubernetes manifests and deploy to cluster
5. **Test**: Run validation tests to verify deployment

```python
# Example FastAPI application
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}
```

## Results

The deployment was successful with the following metrics:
- Build time: 45 seconds
- Deployment time: 30 seconds
- Health check: PASSED
- API response time: < 100ms

## Try It Yourself

You can reproduce this deployment using AutoPoC:

```bash
autopoc --name fastapi-demo --repo https://github.com/example/fastapi-app
```

For more information, visit the [AutoPoC documentation](https://example.com/autopoc).
"""

    # Create a temporary markdown file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(blog_content)
        md_path = f.name

    try:
        # Load configuration
        config = load_config()
        
        if not config.sheet_credentials:
            print("❌ Google Docs integration not configured")
            print("Set AUTOPOC_SHEET_CREDENTIALS in your .env file to enable this feature")
            return
            
        print("✅ Google service account credentials found")
        
        # Extract metadata for the template table
        table_data = extract_blog_metadata(blog_content)
        print(f"📊 Extracted metadata: {table_data}")
        
        # Create Google Docs service
        try:
            docs_service = create_google_docs_service(config.sheet_credentials)
            print("✅ Google Docs service initialized")
        except Exception as e:
            print(f"❌ Failed to initialize Google Docs service: {e}")
            return
            
        # Upload to Google Docs using CLI tool
        try:
            import subprocess
            
            result = subprocess.run([
                "python", "-m", "autopoc.cli_tools", 
                "google-docs-upload", md_path,
                "--project-name", "example-project"
            ], capture_output=True, text=True, cwd="/home/egeiger/src/autopoc/feature/create-blog-google-doc")
            
            if result.returncode == 0:
                import json
                output = json.loads(result.stdout)
                print(f"🎉 Blog post uploaded successfully!")
                print(f"📄 Google Docs URL: {output['doc_url']}")
                print(f"📋 Document Title: {output['doc_title']}")
            else:
                print(f"❌ Failed to upload: {result.stderr}")
            
        except Exception as e:
            print(f"❌ Failed to run CLI tool: {e}")
            
    finally:
        # Clean up temporary file
        Path(md_path).unlink()


if __name__ == "__main__":
    example_blog_to_google_docs()