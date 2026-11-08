"""Renderer submission must isolate failures and keep credentials out of args."""

import pytest

from autopoc.executive_job import build_renderer_job


def job(**overrides):
    return build_renderer_job(
        run_id="run-original",
        revision="a" * 64,
        image="quay.io/example/renderer@sha256:" + "b" * 64,
        input_id="input-drive-id",
        input_sha256="c" * 64,
        recovery_id="recovery-drive-id",
        recovery_sha256="d" * 64,
        namespace="autopoc-test",
        **overrides,
    )


def test_renderer_is_bounded_and_cannot_mutate_workloads():
    manifest = job()
    pod = manifest["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert pod["automountServiceAccountToken"] is False
    assert pod["serviceAccountName"] == "autopoc-executive-renderer"
    assert pod["restartPolicy"] == "Never"
    assert manifest["spec"]["backoffLimit"] == 0
    assert manifest["spec"]["activeDeadlineSeconds"] > 0
    assert "memory" in container["resources"]["limits"]
    assert "ephemeral-storage" in container["resources"]["limits"]
    assert pod["volumes"][0]["emptyDir"]["sizeLimit"]
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"] == {"drop": ["ALL"]}
    assert "credentials.json" not in " ".join(container["args"])
    assert "runAsUser" not in pod["securityContext"]


def test_resume_targets_same_job_without_recreating_work():
    assert job()["metadata"]["name"] == job()["metadata"]["name"]
    changed = build_renderer_job(
        "another-run",
        "a" * 64,
        "quay.io/example/renderer@sha256:" + "b" * 64,
        "input-drive-id",
        "c" * 64,
        "recovery-drive-id",
        "autopoc-test",
        recovery_sha256="d" * 64,
    )
    assert changed["metadata"]["name"] != job()["metadata"]["name"]


@pytest.mark.parametrize("values", [{"deadline": 0}, {"deadline": 999999}])
def test_invalid_resource_profile_is_rejected(values):
    with pytest.raises(ValueError):
        job(**values)


def test_mutable_or_injected_image_cannot_be_submitted():
    with pytest.raises(ValueError):
        build_renderer_job(
            "run",
            "a" * 64,
            "quay.io/org/renderer:latest",
            "input",
            "b" * 64,
            "recovery",
            "autopoc-test",
            recovery_sha256="d" * 64,
        )
