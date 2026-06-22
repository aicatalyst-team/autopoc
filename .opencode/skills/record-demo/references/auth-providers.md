# Authentication Providers

This reference documents the pluggable authentication interface for logging
into the OpenShift Console during demo video recording.

## Architecture

The login function dispatches to a provider-specific implementation based on
the `OPENSHIFT_IDP_NAME` environment variable.

```python
def login_to_console(page, console_url, idp_name, username, password):
    """
    Navigate to the OpenShift Console and authenticate.

    Args:
        page: Playwright Page object.
        console_url: Full URL to the OpenShift Console.
        idp_name: Identity provider button text on the OAuth page.
        username: Login username.
        password: Login password.
    """
```

## Login Flow (All Providers)

Every provider follows the same initial steps:

1. **Navigate** to `console_url`.
2. The console redirects to the **OpenShift OAuth server** at
   `oauth-openshift.apps.<cluster>`.
3. The OAuth page displays a list of configured identity providers as buttons.
4. **Click** the button matching `idp_name`.
5. The browser is redirected to the IDP-specific login page.
6. **Fill credentials** and submit.
7. The IDP redirects back through the OAuth server to the console.
8. The console loads with an authenticated session.

---

## Provider: Keycloak (Default)

**IDP Name:** `keycloak` (configurable via `OPENSHIFT_IDP_NAME`)

### OAuth Page

The OpenShift OAuth page at `/oauth/authorize` lists identity providers.
Each IDP appears as an `<a>` tag with the IDP name as text:

```html
<a href="/oauth/authorize?...&idp=keycloak" class="pf-c-button">keycloak</a>
```

Selector: `a:has-text('keycloak')`

### Keycloak Login Page

After clicking the IDP button, the browser redirects to the Keycloak login
form. The standard Keycloak login page elements:

| Element | Selector | Purpose |
|---------|----------|---------|
| Username field | `#username` | Text input for username |
| Password field | `#password` | Text input for password |
| Login button | `#kc-login` | Submit button |
| Error message | `.kc-feedback-text` or `#input-error` | Displayed on failed login |

These selectors are stable across Keycloak themes (keycloak, keycloak.v2, rh-sso).

### Implementation

```python
def login_keycloak(page, console_url, idp_name, username, password):
    """Log in to OpenShift Console via Keycloak IDP."""

    # Step 1: Navigate to console (triggers OAuth redirect)
    page.goto(console_url, wait_until="networkidle", timeout=30000)

    # Step 2: Wait for OAuth page with IDP buttons
    idp_button = f"a:has-text('{idp_name}')"
    page.wait_for_selector(idp_button, timeout=15000)

    # Step 3: Click the Keycloak IDP button
    page.click(idp_button)

    # Step 4: Wait for Keycloak login form
    page.wait_for_selector("#username", timeout=15000)

    # Step 5: Fill credentials
    page.fill("#username", username)
    page.fill("#password", password)

    # Step 6: Submit
    page.click("#kc-login")

    # Step 7: Wait for redirect back to console
    # The console URL domain should appear in the URL after login.
    from urllib.parse import urlparse
    console_host = urlparse(console_url).hostname
    page.wait_for_url(f"**{console_host}/**", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=30000)
```

### Keycloak Error Handling

```python
# After clicking login, check if we stayed on the Keycloak page (login failed)
try:
    error_element = page.wait_for_selector(
        ".kc-feedback-text, #input-error",
        timeout=3000,
    )
    if error_element:
        error_text = error_element.text_content()
        raise RuntimeError(f"Keycloak login failed: {error_text}")
except TimeoutError:
    pass  # No error — login succeeded and we redirected
```

---

## Provider: htpasswd (Future)

**IDP Name:** `htpasswd` or `my_htpasswd_provider`

The htpasswd provider typically shows a username/password form directly on
the OAuth server page (no redirect to an external IDP).

```python
def login_htpasswd(page, console_url, idp_name, username, password):
    """Log in via htpasswd identity provider."""
    page.goto(console_url, wait_until="networkidle", timeout=30000)

    # Click the htpasswd IDP button
    page.wait_for_selector(f"a:has-text('{idp_name}')", timeout=15000)
    page.click(f"a:has-text('{idp_name}')")

    # The OAuth server shows its own login form (not a redirect).
    # Selectors may vary but typically:
    page.wait_for_selector("#inputUsername, input[name='username']", timeout=15000)
    page.fill("#inputUsername, input[name='username']", username)
    page.fill("#inputPassword, input[name='password']", password)
    page.click("button[type='submit']")

    # Wait for console redirect
    page.wait_for_url(f"**{console_url.split('://', 1)[1]}/**", timeout=30000)
```

---

## Provider: kubeadmin (Future)

**IDP Name:** `kube:admin` (this is the literal text on the OAuth page)

```python
def login_kubeadmin(page, console_url, password):
    """Log in as kubeadmin."""
    page.goto(console_url, wait_until="networkidle", timeout=30000)

    # The kubeadmin option appears as "kube:admin" on the OAuth page
    page.wait_for_selector("a:has-text('kube:admin')", timeout=15000)
    page.click("a:has-text('kube:admin')")

    # kubeadmin uses the htpasswd-style login form
    page.wait_for_selector("#inputUsername, input[name='username']", timeout=15000)
    page.fill("#inputUsername, input[name='username']", "kubeadmin")
    page.fill("#inputPassword, input[name='password']", password)
    page.click("button[type='submit']")

    page.wait_for_url(f"**{console_url.split('://', 1)[1]}/**", timeout=30000)
```

---

## Configuration

| Env Var | Required | Default | Description |
|---------|----------|---------|-------------|
| `OPENSHIFT_IDP_NAME` | No | `keycloak` | Text of the IDP button on the OAuth page |
| `OPENSHIFT_CONSOLE_USERNAME` | Yes | — | Username for the IDP login form |
| `OPENSHIFT_CONSOLE_PASSWORD` | Yes | — | Password for the IDP login form |

These values are sourced from the `autopoc-credentials` Kubernetes Secret.

---

## Testing Authentication

Before recording, you can verify the login works by running:

```bash
# In the container or locally with playwright installed:
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(ignore_https_errors=True)
    page.goto('$CONSOLE_URL')
    page.wait_for_selector(\"a:has-text('$IDP_NAME')\", timeout=15000)
    page.click(\"a:has-text('$IDP_NAME')\")
    page.wait_for_selector('#username', timeout=15000)
    page.fill('#username', '$USERNAME')
    page.fill('#password', '$PASSWORD')
    page.click('#kc-login')
    page.wait_for_load_state('networkidle', timeout=30000)
    print('Login URL:', page.url)
    print('Login successful!' if '$CONSOLE_URL' in page.url else 'Login may have failed')
    browser.close()
"
```

---

## Resilience Notes

- **Timeout values**: All `wait_for_selector` and `wait_for_url` calls include
  explicit timeouts. These are generous (15–30s) to account for slow clusters.

- **Multiple IDP buttons**: If the OAuth page has multiple IDPs, the selector
  `a:has-text('{idp_name}')` matches by text content. Ensure `OPENSHIFT_IDP_NAME`
  exactly matches the button label (case-sensitive).

- **Cookie consent / banners**: Some Keycloak deployments show cookie consent
  dialogs. If this is the case, the LLM should add a step to dismiss the banner
  before filling credentials.

- **Two-factor authentication**: Not supported in this initial implementation.
  If the Keycloak realm requires 2FA, the login will fail. Ensure the automation
  user account has 2FA disabled.
