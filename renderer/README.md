# Offline executive renderer

The Python wrapper accepts only a sealed input ZIP validated by
`autopoc.executive_inputs.verify_inputs`. Reviewed JSON remains data; only the
trusted renderer components generate executable Slidev content. The renderer
never replays PoC tests or visits a workload. Phase 1 video is silent.

New seals use **template revision 2**, the default Red Hat presentation theme:
a red opening, white content slides, local Red Hat Display/Text/Mono fonts and
official corporate artwork. The six evidence-based scenes and their durations
are unchanged. All runtime branding resources and notices are committed under
`assets/redhat/`; generated decks copy them into `public/brand/` for offline use.
Missing or changed assets fail verification. Font/image loading, text bounds,
diagram labels and original logs are checked before PDF export and recording,
including the PDF still and each animation act/log state. Overfull content fails
with a request to shorten reviewed text rather than silently clipping it.

Revision-1 inputs remain verifiable/recoverable but require their original
digest-pinned renderer to render again. The v2 image refuses fresh v1 rendering;
matching complete v1 output can still be reused after integrity checks. Do not
pair a new default v2 seal with the old renderer digest. `executive-seal
--template-version 1` is available only for explicit legacy-image recovery.

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
FFmpeg must provide `libx264`; the renderer image includes both this encoder and
Playwright's separate recording binary.

For real-browser layout/asset regression checks against a built deck, run
`node renderer/check-layout.mjs /absolute/dist /absolute/screenshots` from the
repository with `AUTOPOC_RENDER_NODE_MODULES` configured as above. Set
`AUTOPOC_CHROMIUM_EXECUTABLE` only when using a separately provisioned Chromium.
The check blocks external requests and exercises missing fonts/logos and
oversized claims, titles, counts and diagram labels.

Outputs include the editable `executable-source.zip`, browser `static-site.zip`,
`executive-summary.pdf`, `executive-summary.mp4` (silent template 2, Heart narration template 3), `executive-summary.md`,
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
cannot be symlinks. The wrapper defaults to a 600s budget for silent template 2 and 3000s for narrated template 3. Explicit budgets may be lower, never higher. One shared deadline bounds the complete process sequence.

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

Template 3 performs three sequential stages: prepare/validate deck and PDF, exit
Chromium, generate exact reviewed sentences with offline CPU Kokoro, exit the
speech process, then record the prepared deck and mux audio. Speech runs only
from `/opt/autopoc/speech-venv` with model/config/Heart assets verified against
the reviewed manifest hash. Production downloads happen during image build,
never per video. The worker does not install speech dependencies.

Scene duration is measured PCM length plus 0.35s lead and 0.65s tail, at least
6s, rounded upward to a 30fps frame. Sentence gaps are 0.20s. Default limits are
30 slides, 120s per slide and 900s total; revise and re-review content if it
exceeds those limits. Graph timing scales to this measured interval and remains
illustrative. Timeline, exact transcript, sentence/scene WAVs, dependency locks
and speech identity/licenses stay in the editable source ZIP, excluding model
weights and private diagnostics. Narrated source ZIP/video ceilings are 512MiB
and 1GiB. The same five public artifact kinds remain.

Audio is padded as PCM per scene and concatenated before a single AAC encode;
video segments remain H.264 1280x720/30fps/yuv420p. Every scene and final stream
must match measured duration within 0.25s, and the entire final file must decode.
Speech failure retains validated deck/PDF/source/summary and marks video failed.
No silent fallback is published as a successful narrated video. Private speech
and recording logs remain beside renderer.log and outside public ZIPs.

For stage diagnostics inside the trusted renderer:
```sh
node render.mjs INPUT OUTPUT --stage prepare
# Speech must complete and exit before recording.
node render.mjs INPUT OUTPUT --stage record --timeline SPEECH/timeline.json
```
Run `AUTOPOC_FFMPEG_INTEGRATION=1 node --test audio.test.mjs` to verify real
AAC silence/tone placement around scene cuts, in addition to unit checks.

Narrated acceptance can be repeated against an already reviewed template-3 seal:
```sh
scripts/check-narrated-render.sh IMAGE SEALED_INPUT.zip NEW_OUTPUT_DIRECTORY
```
The script runs the exact local image ID with empty scratch caches, no network,
read-only root, UID28128/group0, 2 CPU and 4GiB memory. It retains image/input
identities, measured runtime, private diagnostics and independent outputs.
Input review and original PoC execution are separate; this script never creates
an approval or reruns PoC tests. The `long` fixture is an intentionally verbose
synthetic encoding stress case, not a recommended stakeholder narrative.

Browser captures use measured media duration rather than a wall-clock guess:
Playwright's first frame can arrive after context creation. Normalize variable
capture frames to 30fps, briefly hold the terminal frame if needed, and trim to
the exact reviewed frame count. Per-scene and final frame totals must match,
preventing cumulative drift across long decks. See the retained genuine WebM
regression fixture and the actual FFmpeg integration tests.
