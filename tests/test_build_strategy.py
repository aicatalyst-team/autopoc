"""Tests for the build strategy abstraction."""

from unittest.mock import MagicMock, patch

import pytest

from autopoc.tools.build_strategy import (
    OpenShiftBuildStrategy,
    PodmanBuildStrategy,
    get_build_strategy,
)


class TestGetBuildStrategy:
    """Tests for the strategy factory function."""

    def test_podman_strategy(self):
        config = MagicMock()
        config.build_strategy = "podman"
        strategy = get_build_strategy(config)
        assert isinstance(strategy, PodmanBuildStrategy)

    def test_openshift_strategy(self):
        config = MagicMock()
        config.build_strategy = "openshift"
        config.openshift_namespace_prefix = "poc"
        with patch("shutil.which", return_value="/usr/bin/oc"):
            strategy = get_build_strategy(config)
        assert isinstance(strategy, OpenShiftBuildStrategy)
        assert strategy.namespace == "poc-builds"

    def test_invalid_strategy(self):
        config = MagicMock()
        config.build_strategy = "docker"
        with pytest.raises(ValueError, match="Unknown build strategy: 'docker'"):
            get_build_strategy(config)

    def test_default_strategy(self):
        """If config has no build_strategy attr, defaults to podman."""
        config = MagicMock(spec=[])  # no attributes
        strategy = get_build_strategy(config)
        assert isinstance(strategy, PodmanBuildStrategy)


class TestPodmanBuildStrategy:
    """Tests for PodmanBuildStrategy."""

    @patch("autopoc.tools.podman_tools.podman_login")
    def test_login(self, mock_login):
        mock_login.return_value = "Login succeeded"
        strategy = PodmanBuildStrategy()
        result = strategy.login("quay.io", "user", "pass")
        assert result == "Login succeeded"
        mock_login.assert_called_once_with(
            registry="quay.io",
            username="user",
            password="pass",
            tls_verify=True,
        )

    @patch("autopoc.tools.podman_tools.podman_login")
    def test_login_no_tls(self, mock_login):
        mock_login.return_value = "Login succeeded"
        strategy = PodmanBuildStrategy()
        strategy.login("localhost:8080", "user", "pass", tls_verify=False)
        mock_login.assert_called_once_with(
            registry="localhost:8080",
            username="user",
            password="pass",
            tls_verify=False,
        )


class TestOpenShiftBuildStrategy:
    """Tests for OpenShiftBuildStrategy."""

    @patch("shutil.which", return_value="/usr/bin/oc")
    def test_init_finds_oc(self, mock_which):
        strategy = OpenShiftBuildStrategy(namespace="test-ns")
        assert strategy._oc == "oc"
        assert strategy.namespace == "test-ns"

    @patch("shutil.which", return_value=None)
    def test_init_no_binary(self, mock_which):
        with pytest.raises(RuntimeError, match="Neither 'oc' nor 'kubectl' found"):
            OpenShiftBuildStrategy()

    @patch("shutil.which", side_effect=lambda x: "/usr/bin/kubectl" if x == "kubectl" else None)
    def test_init_falls_back_to_kubectl(self, mock_which):
        strategy = OpenShiftBuildStrategy()
        assert strategy._oc == "kubectl"

    def test_bc_name_from_tag_simple(self):
        assert OpenShiftBuildStrategy._bc_name_from_tag("quay.io/org/my-app:latest") == "my-app"

    def test_bc_name_from_tag_with_experiment(self):
        assert (
            OpenShiftBuildStrategy._bc_name_from_tag("quay.io/org/my-app:experiment-1") == "my-app"
        )

    def test_bc_name_from_tag_underscores(self):
        assert (
            OpenShiftBuildStrategy._bc_name_from_tag("quay.io/org/my_app_name:latest")
            == "my-app-name"
        )

    def test_bc_name_from_tag_long_name(self):
        long_name = "a" * 100
        result = OpenShiftBuildStrategy._bc_name_from_tag(f"quay.io/org/{long_name}:latest")
        assert len(result) <= 63

    def test_bc_name_from_tag_empty_fallback(self):
        assert OpenShiftBuildStrategy._bc_name_from_tag(":::") == "autopoc-build"

    @patch("shutil.which", return_value="/usr/bin/oc")
    def test_push_is_noop(self, mock_which):
        strategy = OpenShiftBuildStrategy()
        result = strategy.push("quay.io/org/app:latest")
        assert "pushed during the OpenShift build" in result

    @patch("shutil.which", return_value="/usr/bin/oc")
    @patch("subprocess.run")
    def test_login_creates_secret(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        strategy = OpenShiftBuildStrategy(namespace="test-builds")

        result = strategy.login("quay.io", "$oauthtoken", "my-token")

        assert "Registry secret created" in result
        # Should have called: get namespace, create namespace (or get succeeds),
        # delete old secret, create new secret
        assert mock_run.call_count >= 2

    @patch("shutil.which", return_value="/usr/bin/oc")
    @patch("subprocess.run")
    def test_build_creates_buildconfig_and_starts_build(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=0, stdout="Build complete", stderr="")
        strategy = OpenShiftBuildStrategy(namespace="test-builds")

        result = strategy.build(
            context_path="/tmp/repo",
            dockerfile="/tmp/repo/Dockerfile.ubi",
            tag="quay.io/org/app:latest",
        )

        assert "Build complete" in result
        # Should have called: ensure namespace, apply buildconfig, start-build
        assert mock_run.call_count >= 3

    @patch("shutil.which", return_value="/usr/bin/oc")
    @patch("subprocess.run")
    def test_build_raises_on_failure(self, mock_run, mock_which):
        # First calls succeed (namespace check, buildconfig apply), build fails
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if "start-build" in str(args):
                return MagicMock(returncode=1, stdout="", stderr="build error")
            return MagicMock(returncode=0, stdout="ok", stderr="")

        mock_run.side_effect = side_effect
        strategy = OpenShiftBuildStrategy(namespace="test-builds")

        with pytest.raises(RuntimeError, match="OpenShift build failed"):
            strategy.build(
                context_path="/tmp/repo",
                dockerfile="/tmp/repo/Dockerfile.ubi",
                tag="quay.io/org/app:latest",
            )


class TestBuildStrategyConfig:
    """Tests for BUILD_STRATEGY config validation."""

    def test_valid_podman(self):
        """Config accepts build_strategy='podman'."""
        from autopoc.config import AutoPoCConfig

        config = AutoPoCConfig(
            anthropic_api_key="sk-test",
            quay_org="org",
            quay_token="tok",
            openshift_api_url="https://api.test:6443",
            openshift_token="tok",
            gitlab_url="https://gitlab.test",
            gitlab_token="tok",
            gitlab_group="poc",
            build_strategy="podman",
        )
        assert config.build_strategy == "podman"

    def test_valid_openshift(self):
        """Config accepts build_strategy='openshift'."""
        from autopoc.config import AutoPoCConfig

        config = AutoPoCConfig(
            anthropic_api_key="sk-test",
            quay_org="org",
            quay_token="tok",
            openshift_api_url="https://api.test:6443",
            openshift_token="tok",
            gitlab_url="https://gitlab.test",
            gitlab_token="tok",
            gitlab_group="poc",
            build_strategy="openshift",
        )
        assert config.build_strategy == "openshift"

    def test_invalid_strategy(self):
        """Config rejects invalid build_strategy."""
        from pydantic import ValidationError

        from autopoc.config import AutoPoCConfig

        with pytest.raises(ValidationError, match="BUILD_STRATEGY must be"):
            AutoPoCConfig(
                anthropic_api_key="sk-test",
                quay_org="org",
                quay_token="tok",
                openshift_api_url="https://api.test:6443",
                openshift_token="tok",
                gitlab_url="https://gitlab.test",
                gitlab_token="tok",
                gitlab_group="poc",
                build_strategy="docker",
            )

    @patch.dict("os.environ", {}, clear=True)
    def test_default_is_podman(self):
        """Config defaults to build_strategy='podman'."""
        from autopoc.config import AutoPoCConfig

        config = AutoPoCConfig(
            anthropic_api_key="sk-test",
            quay_org="org",
            quay_token="tok",
            openshift_api_url="https://api.test:6443",
            openshift_token="tok",
            gitlab_url="https://gitlab.test",
            gitlab_token="tok",
            gitlab_group="poc",
            _env_file=None,
        )
        assert config.build_strategy == "podman"
