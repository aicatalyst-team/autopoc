# Pinned static FFmpeg

FFmpeg/ffprobe 7.0.2 are copied from the public `mwader/static-ffmpeg` image
pinned by OCI digest in `manifest.json` and Dockerfile.executive. The build
checks each amd64 executable SHA-256 after copying. Binaries stay out of Git.
Retain the upstream version inventory and unmodified FFmpeg GPLv3 license in
the image/source package. Source/build recipes: https://github.com/wader/static-ffmpeg
and https://github.com/FFmpeg/FFmpeg/tree/n7.0.2 .

The previous John Van Sickle moving archive and a supposed version-specific
archive returned content that failed the already approved checksum (the latter
was HTML). Do not replace the expected hash with that response or bypass the
check. The public pinned image avoids relying on a private historical renderer
image in CI and is validated for H.264/AAC and offline decoding during acceptance.
