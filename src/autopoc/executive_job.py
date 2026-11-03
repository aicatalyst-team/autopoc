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
    deadline: int = 600,
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
    if not 30 <= deadline <= 1800:
        raise ValueError("Renderer deadline must be between 30 and 1800 seconds")
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
                        {"name": "scratch", "emptyDir": {"sizeLimit": "4Gi"}},
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
                            ],
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
                                    "cpu": "500m",
                                    "memory": "1Gi",
                                    "ephemeral-storage": "1Gi",
                                },
                                "limits": {"cpu": "2", "memory": "3Gi", "ephemeral-storage": "5Gi"},
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
