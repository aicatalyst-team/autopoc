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

## Where the pins came from

The pinned sizes and SHA-256 values are those of the files downloaded from
`hexgrad/Kokoro-82M` at revision `f3ff3571791e39611d31c381e3a41a3af07b4987`
during the local audition on 8 November 2026, recorded into `manifest.json`
and used to produce the auditioned audio. Every later build verifies against
those committed values, and `prepare-kokoro-assets.py` reads the manifest
rather than generating expected hashes from whatever it fetches, so a
substituted upstream file fails the build.

What this establishes is continuity: the bytes in every image are the bytes
that were auditioned. It is not an upstream signature check, a reproducible
rebuild of the weights, and not an assessment of model safety or licensing
beyond the notices in `LICENSES.md`. Upstream publishes no signature for these
files, so an independent attestation would require a separate trusted copy;
none was obtained. Record any future verification with its date and method
here instead of implying one happened.

Update models through a new reviewed manifest, generated dependency lock and
image digest, followed by offline/OCP acceptance. Never download or install an
asset during rendering or silently substitute a different voice/model.

See `LICENSES.md` and `licenses/` for source/license provenance. Build-time
distribution notices are additionally retained beside the installed model and
included in editable source/recovery packaging.
