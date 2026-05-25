# HTML Preview Generation Guide

Convert a finalized blog post into a branded HTML preview using the template at `assets/blog-template.html`.

## Process

1. Read `assets/blog-template.html`
2. Extract metadata from `final.md`
3. Convert markdown body to HTML
4. Replace all `{{PLACEHOLDER}}` tokens
5. Write to `blog-preview.html`

## Placeholders

| Placeholder | Source |
|---|---|
| `{{TITLE}}` | H2 heading (first heading in body) |
| `{{SUBTITLE}}` | Line after the title (bold/italic text) |
| `{{META_DESCRIPTION}}` | From seo.md or generate 150-160 char summary |
| `{{PRODUCT_LABEL}}` | "Red Hat OpenShift AI" (or primary product) |
| `{{AUTHOR}}` | From qualifying summary or default |
| `{{DATE}}` | Current month/year |
| `{{READ_TIME}}` | ceil(word_count / 200) min read |
| `{{YEAR}}` | Current year |
| `{{BREADCRUMBS}}` | Red Hat Developer Blog > AI/ML > Topic |
| `{{BODY_CONTENT}}` | Converted HTML |

## Markdown to HTML Conversion

| Markdown | HTML |
|---|---|
| `## Heading` | `<h2>Heading</h2>` |
| `### Heading` | `<h3>Heading</h3>` |
| Paragraph | `<p>Paragraph</p>` |
| `**bold**` | `<strong>bold</strong>` |
| `*italic*` | `<em>italic</em>` |
| `[text](url)` | `<a href="url">text</a>` |
| Bullet list | `<ul><li>...</li></ul>` |
| Numbered list | `<ol><li>...</li></ol>` |
| Code block | `<pre><code>...</code></pre>` |

## Image Placeholders

Convert `--------------------` delimited blocks to:
```html
<div class="image-placeholder">
  <div class="ph-icon"><svg>...</svg></div>
  <div class="ph-title">Image N: description</div>
  <div class="ph-alt">Alt text</div>
</div>
```

## Read Time
```
read_time = ceil(word_count / 200)
```
Count body words only (exclude metadata, prompts, rationale).
