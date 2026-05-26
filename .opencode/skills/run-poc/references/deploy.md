# Deploy Phase Instructions

Generate Kubernetes manifest files in the `kubernetes/` directory. Do NOT apply them -- that's Phase 8's job.

## Manifest Generation Order

1. **`namespace.yaml`** (always first)
2. **`secret.yaml`** (if sensitive env vars exist)
3. **Component manifests** (based on deployment_model):
   - `deployment` + port: `<component>-deployment.yaml` + `<component>-service.yaml`
   - `deployment` + no port: `<component>-deployment.yaml` only
   - `job`: `<component>-<scenario>-job.yaml` (one per test scenario)
4. **`pvc.yaml`** (if persistent storage needed)

## Namespace Manifest

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: poc-{project_name}
  labels:
    app.kubernetes.io/name: {project_name}
    app.kubernetes.io/managed-by: autopoc
```

## Deployment Manifest

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {component}
  namespace: poc-{project_name}
  labels:
    app: {component}
    autopoc.io/project: {project_name}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {component}
  template:
    metadata:
      labels:
        app: {component}
    spec:
      containers:
        - name: {component}
          image: {full_image_ref}
          imagePullPolicy: Always  # for :latest tags
          ports:
            - containerPort: {port}
          env:
            # Non-sensitive vars as plain values
            - name: PORT
              value: "{port}"
            # Sensitive vars from Secret
            - name: API_KEY
              valueFrom:
                secretKeyRef:
                  name: {component}-secrets
                  key: API_KEY
          resources:
            requests:
              memory: "{memory_request}"
              cpu: "{cpu_request}"
            limits:
              memory: "{memory_limit}"
              cpu: "{cpu_limit}"
          readinessProbe:
            httpGet:
              path: /health
              port: {port}
            initialDelaySeconds: 10
            periodSeconds: 5
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
```

## Service Manifest

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {component}
  namespace: poc-{project_name}
  labels:
    app: {component}
    autopoc.io/project: {project_name}
spec:
  type: ClusterIP
  selector:
    app: {component}
  ports:
    - port: {port}
      targetPort: {port}
```

## Job Manifest (for CLI tools)

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: {component}-{scenario_name}
  namespace: poc-{project_name}
spec:
  backoffLimit: 1
  activeDeadlineSeconds: 120
  template:
    spec:
      containers:
        - name: {component}
          image: {full_image_ref}
          imagePullPolicy: Always
          command: [{entrypoint}]
          args: [{scenario_args}]
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
      restartPolicy: Never
```

## Secret Manifest

For env vars containing KEY, TOKEN, SECRET, PASSWORD, CREDENTIAL, or with value `"required"`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: {component}-secrets
  namespace: poc-{project_name}
type: Opaque
stringData:
  API_KEY: "placeholder-replace-me"
```

## Resource Sizing

| Profile | Memory Request | CPU Request | Memory Limit | CPU Limit |
|---|---|---|---|---|
| small | 256Mi | 250m | 512Mi | 500m |
| medium | 1Gi | 500m | 2Gi | 1000m |
| large | 4Gi | 2000m | 8Gi | 4000m |
| gpu | 8Gi | 4000m | 16Gi | 8000m |

## LLM Proxy (OGX) Handling

When `infrastructure.needs_llm_api` is true:
1. Run: `python -m autopoc.tools.llm_proxy '<env_vars_json>'`
2. Use the resolved env vars in the manifest
3. If OGX is configured, `OPENAI_API_KEY` will be `"none"` and `OPENAI_BASE_URL` will point to the internal OGX service -- these are NOT secrets, use plain `env:` values

## Security Context (OpenShift)

**NEVER set** in manifests:
- `runAsUser` (OpenShift assigns random UID)
- `fsGroup` (OpenShift assigns supplemental groups)
- `runAsNonRoot: true` at pod level (some sidecars need root then drop privileges)

**ALWAYS set** at container level:
```yaml
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

## ImagePullPolicy Rules

- Images tagged `:latest` -> `imagePullPolicy: Always`
- Images with `localhost:` or `127.0.0.1:` -> `imagePullPolicy: Never` (local E2E)
- Images with specific version tag -> `imagePullPolicy: IfNotPresent`

## Handling Deploy Retry

When re-entering this phase after an apply failure (check `errors` in state):
- Read the error from the previous apply attempt
- Fix the specific manifest issue
- If the same manifests would be generated (no-progress), consider escalating to container fix
