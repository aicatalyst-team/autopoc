# Offline Heart assets

`manifest.json` pins the original model/config/Heart bytes auditioned locally,
including immutable upstream revision, sizes and SHA-256. Model weights are not
stored in Git. `scripts/prepare-kokoro-assets.py` copies a verified build cache or
downloads these exact files while building the renderer image, exposing regular
files under `/opt/autopoc/speech-assets/` only after integrity checks.

The renderer-only hash lock installs CPU Torch, Kokoro/Misaki and the explicit
English spaCy model wheel in `/opt/autopoc/speech-venv`. Runtime verification
checks the reviewed manifest identity and local files before inference. The
adapter passes explicit local model/config/voice paths, validates the packaged
English model and enables offline mode before importing speech libraries.

Update models through a new reviewed manifest, generated dependency lock and
image digest, followed by offline/OCP acceptance. Never download or install an
asset during rendering or silently substitute a different voice/model.

See `LICENSES.md` and `licenses/` for source/license provenance. Build-time
distribution notices are additionally retained beside the installed model and
included in editable source/recovery packaging.
