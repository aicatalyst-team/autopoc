"""Sealed-format render budgets and publication ceilings; never environment-driven."""

from __future__ import annotations

import hashlib
import json
import re


def render_policy(verified: dict) -> dict:
    """Derive a durable policy only from verified sealed content."""
    narrated = verified["versions"]["template"] == 3
    scenes = verified["scenes"]
    raw = json.dumps(
        scenes["timing_policy"] if narrated else scenes, sort_keys=True, separators=(",", ":")
    ).encode()
    return {
        "profile": "kokoro-v3" if narrated else "silent-v2",
        "narration": "kokoro" if narrated else "none",
        "render_timeout_seconds": 3000 if narrated else 600,
        "job_deadline_seconds": 3120 if narrated else 600,
        "scene_policy_sha256": hashlib.sha256(raw).hexdigest(),
    }


def saved_policy(checkpoint: dict, verified: dict | None = None) -> dict | None:
    """Legacy descriptors retain their bytes; new ones must match sealed policy."""
    policy = checkpoint.get("render_policy")
    if policy is None:
        if verified is not None and verified["versions"]["template"] == 3:
            raise ValueError("Narrated inputs require a saved render policy")
        return None
    if not isinstance(policy, dict) or policy.get("profile") not in ("silent-v2", "kokoro-v3"):
        raise ValueError("Invalid saved render policy")
    narrated = policy["profile"] == "kokoro-v3"
    expected = {
        "profile": "kokoro-v3" if narrated else "silent-v2",
        "narration": "kokoro" if narrated else "none",
        "render_timeout_seconds": 3000 if narrated else 600,
        "job_deadline_seconds": 3120 if narrated else 600,
        "scene_policy_sha256": policy.get("scene_policy_sha256"),
    }
    if (
        policy != expected
        or not isinstance(expected["scene_policy_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected["scene_policy_sha256"])
    ):
        raise ValueError("Invalid saved render policy")
    if verified is not None and policy != render_policy(verified):
        raise ValueError("Saved policy differs from sealed format")
    return policy


def artifact_limit(checkpoint: dict, kind: str) -> int:
    """Bounds are selected from the verified format, never a receipt's size."""
    policy = saved_policy(checkpoint)
    if policy and policy["profile"] == "kokoro-v3":
        return {"source": 512 * 1024**2, "video": 1024**3}.get(kind, 256 * 1024**2)
    return 256 * 1024**2
