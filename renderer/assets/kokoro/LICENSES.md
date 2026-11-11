# Speech model and software provenance

- Kokoro code: `hexgrad/kokoro`, package 0.9.4, Apache License 2.0. The unmodified
  package license is retained in `licenses/kokoro-APACHE-2.0.txt`.
- Model/config/Heart voice: `hexgrad/Kokoro-82M` revision
  `f3ff3571791e39611d31c381e3a41a3af07b4987`, published with Apache-2.0 weights.
  The pinned upstream model card is retained as `licenses/model-card.md`.
- English model: Explosion `en_core_web_sm` 3.8.0; explicit upstream wheel,
  hash-locked in renderer requirements; upstream notices remain installed.
- Torch, Misaki, spaCy, NumPy, SoundFile, eSpeak-related components and their
  transitive software retain their own licenses. In particular, phonemizer and
  eSpeak include GPL obligations; this notice does not relicense them as Apache.

The build collects installed wheel license/copyright/notice files under
`/opt/autopoc/speech-assets/licenses/` with a versioned package-notice inventory.
Keep these notices in the image and editable source ZIP, together with the
renderer dependency lock and asset manifest. Original project sources remain
available at the upstream repositories linked in package metadata/model card.
