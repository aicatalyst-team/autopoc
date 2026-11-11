# Synthetic generic story examples — schema 3

These fictional examples demonstrate authoring, not real repositories, tests,
deployments, model approvals or accepted media. No network access or PoC replay
was used. No review.json is supplied. All repository/documentation URLs are
illustrative references only. Model manifest hashes in scenes.json are explicit
placeholders, not the identity of a usable renderer. Replace them with tested
image identities and obtain actual independent review before sealing a real run.

- `github-service/`: Parcel Relay, an event forwarding service, six checks over
  two testing pages, all five statuses, a real failed rejection check, interrupted
  cancellation and an error before comparison. Its identity image is a locally
  authored **concept**, never a screenshot or observed trace. Unversioned docs
  describe intended behavior only. No topology is asserted from that image.
- `gitlab-cli/`: Ledger Scan, a local command line tool with no web UI or
  deployment. One check passes and a long-named large-file check is incomplete.
  No imagery is available; identity text remains sufficient.
- `codeberg-library/`: Record Fold, an in-process library. The evidence retains
  only a source excerpt and proposed plan. Its inventory is empty, its source
  revision unavailable and its topology absent. No deployment, success or
  product defect is inferred. A self-hosted credential-free HTTPS repository
  URL has the same contract; no host-specific API is selected.

Each directory contains narrative.json, scene-plan scenes.json, source.md,
evidence-index.json, manifest.json and provenance.json. Every claim cites its
own synthetic source line; each check's spoken purpose/outcome maps to its row.
`evidence-index.json` is a minimal input for the story validator, **not** an
independently verified evidence bundle. In production these inputs come from
`evidence-create` / `evidence-verify`; source excerpts must already be retained
in that verified bundle. Never pass these example indexes off as verified runs.
Provenance records the fictional inputs, source hash, missing capture/revision
and approval status. The asset manifest records exact PNG hash and dimensions.

From the repository root, the following validates actual example data with the
implemented story, scene, check-derivation and visual archive APIs. It performs
no review, synthesis, dispatch or publication, and writes archives only in a
temporary directory:

```python
import json
import tempfile
from pathlib import Path
from autopoc.executive_story import validate_story, validate_scene_plan, derive_checks
from autopoc.executive_visuals import prepare_visuals, verify_visuals

root = Path('.opencode/skills/run-poc/references/executive-story-examples')
with tempfile.TemporaryDirectory() as temporary:
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        read = lambda name: json.loads((directory / name).read_text())
        story, index, scenes = read('narrative.json'), read('evidence-index.json'), read('scenes.json')
        validate_story(story, index, {'source.md': (directory / 'source.md').read_bytes()})
        validate_scene_plan(scenes, story)
        checks = derive_checks(index)
        assert len(checks['results']) == sum(story['results'].values())
        archive = Path(temporary) / (directory.name + '.zip')
        prepare_visuals(directory / 'manifest.json', archive)
        manifest = verify_visuals(archive, run_id=story['run_id'],
                                 claim_ids={c['id'] for c in story['claims']})
        assets = {asset['id'] for asset in manifest['assets']}
        assert all(slide['visual_id'] is None or slide['visual_id'] in assets
                   for slide in story['slides'])
        print(directory.name, len(story['slides']), 'slides:', len(checks['results']), 'checks')
```

Use the project Python environment with `PYTHONPATH=src` when not installed.
Structural validation checks bounds, selectors and relationships; it does not
prove semantic truth. Read the source line, visible claim and mapped speech
alongside each other. The service failure stays failed, the incomplete CLI check
stays incomplete, and the library's empty inventory produces no validation
claim. Text-only model review must limit its assertions to text/manifest/source
provenance. Record actual image inspection separately with the PNG hash and
reviewer identity; release acceptance still requires final-media inspection and
listening. Do not claim browser layout, pronunciation or media acceptance from
these authoring examples.
