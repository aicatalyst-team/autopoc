# Offline executive renderer

The Python wrapper accepts only a sealed input ZIP validated by
`autopoc.executive_inputs.verify_inputs`. Reviewed JSON remains data; only the
trusted renderer components generate executable Slidev content. The renderer
never replays PoC tests or visits a workload. Phase 1 video is silent.

From an installed AutoPoC checkout with Node >=22.18, npm dependencies and
Playwright browsers already provisioned:

```sh
export AUTOPOC_RENDERER_ROOT="$PWD/renderer"
export AUTOPOC_RENDER_NODE_MODULES="$PWD/renderer/node_modules"
uv run autopoc-tools executive-render --inputs /absolute/render-inputs.zip --output-dir /absolute/output
```

The final command is also the container argument list after `executive-render`.
For editable source ZIP recovery, use its `render-inputs.zip` as this command's
input. Recovery uses the original digest-pinned renderer image recorded in
`recovery.json`. `render.mjs INPUT_DIR OUTPUT_DIR` is the lower-level Node entry
point; the Python wrapper must validate inputs first. Browser dependencies and
FFmpeg must be present before invoking it. No runtime dependency downloads occur.

Outputs include the editable `executable-source.zip`, browser `static-site.zip`,
`executive-summary.pdf`, silent `executive-summary.mp4`, `executive-summary.md`,
and `presentation-manifest.json`. The source ZIP includes trusted components,
local fonts/licenses, dependency lock, speaker notes, claim references in
`narrative.json`, sealed inputs and recovery metadata. It excludes `node_modules`,
browser captures, frame images and temporary video segments. The browser ZIP
contains the built site at its root and can be served with a local HTTP server.
Opening its HTML directly via `file://` is not the supported browser mode.

Generated artifacts are `generated_unpublished`; uploading and linking are
separate operations. Each packaged artifact is hashed and sized. Matching
complete output is reused only after hash checks; a conflicting or partial
nonempty output directory requires a new destination. Video failure preserves
usable PDF/deck outputs and records `partial`. Input paths and output ancestors
cannot be symlinks. The wrapper has a hard timeout of at most 600 seconds.

Build and publish independently of the worker/recorder images:

```sh
make renderer-image IMAGE_ORG=my-org IMAGE_TAG=reviewed-revision
make renderer-image-push IMAGE_ORG=my-org IMAGE_TAG=reviewed-revision
```

`Dockerfile.executive` targets Linux amd64 on UBI9 Python 3.12, with checksum-pinned
Node 22.22.2 and static FFmpeg 7.0.2 containing `libx264`. The FFmpeg GPLv3 license
and upstream readme remain under `/usr/share/licenses/autopoc-ffmpeg`; consult the
upstream source links in that readme when redistributing. Playwright's matching
Chromium/recording binary and npm's locked dependencies are installed at build
time. Local font and TopoLoop licenses remain in `vendor/`.

Run without a service-account token, with read-only root filesystem, arbitrary
nonzero UID in group 0, and a writable `/scratch` volume. Scratch contains HOME,
TMPDIR and caches; the wrapper uses private temporary directories. Container
resource limits and deadlines belong to the Job, independently of the Python
subprocess timeout. No cluster credentials are required for local rendering.
Remote artifact transfer uses only the separately mounted artifact credential.
Renderer stdout/stderr remain in private `renderer.log` (mode 0600), excluded
from source/site ZIPs and publication metadata. Timeout kills the process group.

Before rollout, build on amd64 and verify a real six-scene render under an
arbitrary UID, read-only root filesystem and the target cluster's limits. A unit
test using the Node boundary does not establish Chromium/UBI compatibility or
resource sizing. Mutable upstream FFmpeg release replacement causes checksum
failure and requires an explicitly reviewed checksum update.
