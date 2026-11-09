"""Build a bounded, reproducible renderer Job; no workload credentials in its pod."""

from __future__ import annotations

import hashlib
import re


def build_renderer_job(
    run_id: str,
    revision: str,
    image: str,
    input_id: str,
    input_sha256: str,
    recovery_id: str,
    namespace: str,
    *,
    recovery_sha256: str,
    credentials_secret: str = "autopoc-google-sa",
    deadline: int | None = None,
    profile: str = "silent-v2",
) -> dict:
    """Return an unsubmitted batch/v1 Job; resources are a provisional profile.

    A digest is mandatory so a recovery reference always selects the same code.
    Requests/limits must be measured on the target cluster before rollout.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        raise ValueError("Invalid run identity")
    if not all(
        re.fullmatch(r"[0-9a-f]{64}", value) for value in (revision, input_sha256, recovery_sha256)
    ):
        raise ValueError("Expected SHA-256 identity")
    if not re.fullmatch(r"[a-zA-Z0-9./:_-]+@sha256:[0-9a-f]{64}", image):
        raise ValueError("Renderer image must be pinned by digest")
    if not all(re.fullmatch(r"[A-Za-z0-9_-]{1,200}", v) for v in (input_id, recovery_id)):
        raise ValueError("Invalid artifact identity")
    if not all(
        re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", v) and len(v) <= 63
        for v in (namespace, credentials_secret)
    ):
        raise ValueError("Invalid namespace or Secret name")
    if profile not in ("silent-v2", "kokoro-v3"):
        raise ValueError("Unknown renderer profile")
    narrated = profile == "kokoro-v3"
    # A Job deadline runs from startTime, so scheduling and image pull consume it
    # before rendering begins; the default keeps 600s of headroom over the 3000s
    # process budget. 3120s stays accepted for descriptors sealed before 9 Nov 2026.
    deadline = (3600 if narrated else 600) if deadline is None else deadline
    if type(deadline) is not int or not (3120 if narrated else 30) <= deadline <= (
        3600 if narrated else 1800
    ):
        raise ValueError("Renderer deadline is outside the selected profile")
    suffix = hashlib.sha256(f"{run_id}/{revision}".encode()).hexdigest()[:24]
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": f"autopoc-executive-{suffix}",
            "namespace": namespace,
            "labels": {"app": "autopoc-executive", "autopoc/revision": revision[:63]},
        },
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": deadline,
            "ttlSecondsAfterFinished": 86400,
            "template": {
                "metadata": {"labels": {"app": "autopoc-executive"}},
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "serviceAccountName": "autopoc-executive-renderer",
                    "securityContext": {
                        "runAsNonRoot": True,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "volumes": [
                        {
                            "name": "scratch",
                            "emptyDir": {"sizeLimit": "8Gi" if narrated else "4Gi"},
                        },
                        {"name": "google", "secret": {"secretName": credentials_secret}},
                    ],
                    "containers": [
                        {
                            "name": "renderer",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "args": [
                                "executive-render",
                                "--input-id",
                                input_id,
                                "--input-sha256",
                                input_sha256,
                                "--recovery-id",
                                recovery_id,
                                "--recovery-sha256",
                                recovery_sha256,
                            ]
                            + (["--timeout-seconds", "3000"] if narrated else []),
                            "env": [
                                {"name": "HOME", "value": "/scratch/home"},
                                {"name": "TMPDIR", "value": "/scratch/tmp"},
                                {
                                    "name": "AUTOPOC_SHEET_CREDENTIALS",
                                    "value": "/credentials/credentials.json",
                                },
                            ],
                            "volumeMounts": [
                                {"name": "scratch", "mountPath": "/scratch"},
                                {"name": "google", "mountPath": "/credentials", "readOnly": True},
                            ],
                            "resources": {
                                "requests": {
                                    "cpu": "2" if narrated else "500m",
                                    "memory": "4Gi" if narrated else "1Gi",
                                    "ephemeral-storage": "1Gi",
                                },
                                "limits": {
                                    "cpu": "2",
                                    "memory": "4Gi" if narrated else "3Gi",
                                    "ephemeral-storage": "10Gi" if narrated else "5Gi",
                                },
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]},
                            },
                        }
                    ],
                },
            },
        },
    }
