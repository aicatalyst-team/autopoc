# Google Docs Template Deployment

The Google Docs template (`google-docs-template.md`) contains proprietary Red Hat content and should not be committed to public repositories. Instead, it should be deployed as a Kubernetes secret and mounted to the application pod.

## Template Location

In the development environment, the template is located at:
```
.opencode/skills/blog-create/templates/google-docs-template.md
```

This file is git-ignored to prevent accidental commits.

## Production Deployment

### 1. Create Kubernetes Secret

Create a secret containing the template:

```bash
kubectl create secret generic blog-template \
  --from-file=google-docs-template.md=.opencode/skills/blog-create/templates/google-docs-template.md \
  --namespace=autopoc
```

### 2. Mount Secret in Pod

Update the deployment to mount the secret as a volume:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: autopoc
spec:
  template:
    spec:
      containers:
      - name: autopoc
        image: autopoc:latest
        volumeMounts:
        - name: blog-template
          mountPath: /app/.opencode/skills/blog-create/templates
          readOnly: true
      volumes:
      - name: blog-template
        secret:
          secretName: blog-template
```

### 3. Verify Mount

The application will look for the template at the mounted path:
```
/app/.opencode/skills/blog-create/templates/google-docs-template.md
```

## Template Content

The template contains:
- Red Hat blog submission form structure
- Editorial review checkpoints
- Publication workflow information
- Internal Red Hat process references

## Security Considerations

1. **Never commit** the template to public Git repositories
2. **Restrict access** to the Kubernetes secret to authorized personnel only
3. **Use RBAC** to control who can read/modify the secret
4. **Audit access** to the template content regularly

## Local Development

For local development:

1. Obtain the template from authorized sources
2. Place it in the git-ignored location
3. The application will use it automatically when configured

## Continuous Integration

CI/CD pipelines should:

1. **Skip template files** during builds
2. **Deploy secrets separately** from application code
3. **Verify template presence** during deployment health checks
4. **Use external secret management** (e.g., HashiCorp Vault) for template storage