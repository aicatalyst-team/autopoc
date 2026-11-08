#!/usr/bin/env bash
# Offline acceptance of an already reviewed template-3 sealed input. Never replay PoC tests.
set -euo pipefail
if [[ $# != 3 ]]; then
  echo 'Usage: check-narrated-render.sh IMAGE SEALED_INPUT.zip NEW_OUTPUT_DIRECTORY' >&2
  exit 2
fi
image=$1
input=$(realpath -e "$2")
output=$(realpath -m "$3")
if [[ -L $2 || ! -f $input || -e $output ]]; then
  echo 'Use a regular sealed input and a new output directory.' >&2
  exit 2
fi
mkdir -p "$output/scratch"
# Map an arbitrary nonzero container UID to the current host user, preserving readable outputs.
image_id=$(podman image inspect "$image" --format '{{.Id}}')
image_digest=$(podman image inspect "$image" --format '{{.Digest}}')
printf '%s\n' "$image_id" > "$output/image-id.txt"
printf '%s\n' "$image_digest" > "$output/image-digest.txt"
sha256sum "$input" > "$output/input-sha256.txt"
started=$(date +%s)
set +e
podman run --rm --userns=keep-id:uid=28128,gid=0 --user=28128:0 \
  --network=none --read-only --cpus=2 --memory=4g --pids-limit=512 \
  --cap-drop=ALL --security-opt=no-new-privileges \
  -v "$input:/input/render-inputs.zip:ro,Z" \
  -v "$output/scratch:/scratch:Z" "$image_id" \
  executive-render --inputs /input/render-inputs.zip --output-dir /scratch/output \
  > "$output/renderer-result.json" 2> "$output/container.log"
status=$?
set -e
printf '%s\n' "$(( $(date +%s) - started ))" > "$output/elapsed-seconds.txt"
if [[ -f $output/scratch/output/presentation-manifest.json ]]; then
  sha256sum "$output/scratch/output/presentation-manifest.json" > "$output/manifest-sha256.txt"
fi
if (( status != 0 )); then
  echo "Renderer exited with status $status; inspect retained partial output and private logs." >&2
  exit "$status"
fi
echo "Offline render completed; measured results are in $output/scratch/output/presentation-manifest.json"
