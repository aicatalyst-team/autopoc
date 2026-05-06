"""Tests for the strategy loader module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from autopoc.tools.strategy import (
    _resolve_data_dir,
    compute_max_score,
    get_max_per_dimension,
    get_scoring_dimensions,
    load_strategy,
    load_strategy_baseline,
    load_strategy_config,
)


class TestResolveDataDir:
    def test_finds_default_data_dir(self) -> None:
        data_dir = _resolve_data_dir()
        assert data_dir.is_dir()
        assert (data_dir / "strategy_config.yaml").is_file()

    def test_respects_env_override(self, tmp_path: Path) -> None:
        # Create a minimal data dir
        (tmp_path / "strategy_config.yaml").write_text('active_strategy: "test"')
        with patch.dict(os.environ, {"AUTOPOC_DATA_DIR": str(tmp_path)}):
            data_dir = _resolve_data_dir()
        assert data_dir == tmp_path

    def test_env_override_falls_back_if_missing(self) -> None:
        with patch.dict(os.environ, {"AUTOPOC_DATA_DIR": "/nonexistent/path"}):
            # Should fall back to default data dir (which exists)
            data_dir = _resolve_data_dir()
            assert data_dir.is_dir()


class TestLoadStrategyConfig:
    def test_loads_config(self) -> None:
        config = load_strategy_config()
        assert "active_strategy" in config
        assert isinstance(config["active_strategy"], str)
        assert config["active_strategy"] == "redhat-ai-2026"

    def test_missing_config_file(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"AUTOPOC_DATA_DIR": str(tmp_path)}):
            # tmp_path exists but has no strategy_config.yaml
            (tmp_path / "dummy").write_text("")  # ensure dir is valid
            with pytest.raises(FileNotFoundError, match="strategy_config.yaml"):
                load_strategy_config()

    def test_invalid_config_content(self, tmp_path: Path) -> None:
        (tmp_path / "strategy_config.yaml").write_text("wrong_key: value")
        with patch.dict(os.environ, {"AUTOPOC_DATA_DIR": str(tmp_path)}):
            with pytest.raises(ValueError, match="active_strategy"):
                load_strategy_config()


class TestLoadStrategy:
    def test_loads_active_strategy(self) -> None:
        strategy = load_strategy()
        assert "name" in strategy
        assert strategy["name"] == "Red Hat AI 2026"
        assert "impact_dimensions" in strategy
        assert "feasibility_dimensions" in strategy

    def test_loads_specific_strategy(self) -> None:
        strategy = load_strategy("classic")
        assert strategy["name"] == "Classic"
        assert "impact_dimensions" in strategy

    def test_loads_redhat_ai_2026(self) -> None:
        strategy = load_strategy("redhat-ai-2026")
        assert strategy["name"] == "Red Hat AI 2026"
        dims = strategy["impact_dimensions"]
        dim_names = [d["name"] for d in dims]
        assert "audience_value" in dim_names
        assert "strategic_alignment" in dim_names
        assert "strategy_fit" in dim_names
        assert "platform_leverage" in dim_names
        assert "demo_potential" in dim_names

    def test_missing_strategy_file(self) -> None:
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            load_strategy("nonexistent")

    def test_error_message_lists_available(self) -> None:
        with pytest.raises(FileNotFoundError) as exc_info:
            load_strategy("nonexistent")
        # Should list available strategies in error
        error_msg = str(exc_info.value)
        assert "classic" in error_msg or "redhat-ai-2026" in error_msg


class TestLoadStrategyBaseline:
    def test_loads_default_baseline(self) -> None:
        baseline = load_strategy_baseline()
        assert "strategy_areas" in baseline
        assert "core_products" in baseline
        assert "relationship_rules" in baseline
        assert "duplication_guidance" in baseline

    def test_baseline_has_strategy_areas(self) -> None:
        baseline = load_strategy_baseline()
        areas = baseline["strategy_areas"]
        assert len(areas) >= 4
        categories = [a["category"] for a in areas]
        assert "model-inference" in categories
        assert "model-customization" in categories
        assert "agentic-ai" in categories
        assert "management-observability-security" in categories

    def test_baseline_areas_have_capability_labels(self) -> None:
        baseline = load_strategy_baseline()
        for area in baseline["strategy_areas"]:
            assert "capability_labels" in area
            assert len(area["capability_labels"]) > 0
            assert "enrich_if" in area
            assert "duplicate_if" in area

    def test_baseline_has_core_products(self) -> None:
        baseline = load_strategy_baseline()
        products = baseline["core_products"]
        assert len(products) >= 10
        names = [p["name"] for p in products]
        assert "OpenShift AI" in names
        assert "InstructLab" in names

    def test_baseline_has_relationship_rules(self) -> None:
        baseline = load_strategy_baseline()
        rules = baseline["relationship_rules"]
        assert "enriches-existing-capability" in rules
        assert "duplicates-existing-capability" in rules
        assert "misaligned" in rules

    def test_loads_with_relative_path(self) -> None:
        baseline = load_strategy_baseline("data/strategy-baseline.yaml")
        assert "strategy_areas" in baseline

    def test_missing_baseline(self) -> None:
        with pytest.raises(FileNotFoundError, match="strategy-baseline"):
            load_strategy_baseline("/nonexistent/baseline.yaml")


class TestGetScoringDimensions:
    def test_redhat_ai_2026_has_5_dimensions(self) -> None:
        strategy = load_strategy("redhat-ai-2026")
        dims = get_scoring_dimensions(strategy)
        assert len(dims) == 5

    def test_classic_has_3_dimensions(self) -> None:
        strategy = load_strategy("classic")
        dims = get_scoring_dimensions(strategy)
        assert len(dims) == 3

    def test_dimensions_have_required_keys(self) -> None:
        strategy = load_strategy("redhat-ai-2026")
        dims = get_scoring_dimensions(strategy)
        for dim in dims:
            assert "name" in dim
            assert "weight" in dim

    def test_raises_for_missing_dimensions(self) -> None:
        with pytest.raises(ValueError, match="impact_dimensions"):
            get_scoring_dimensions({"name": "empty"})


class TestComputeMaxScore:
    def test_redhat_ai_2026_max_is_100(self) -> None:
        strategy = load_strategy("redhat-ai-2026")
        assert compute_max_score(strategy) == 100

    def test_classic_max_is_99(self) -> None:
        # 3 dimensions: 100 // 3 = 33, 33 * 3 = 99
        strategy = load_strategy("classic")
        assert compute_max_score(strategy) == 99

    def test_empty_dimensions_returns_0(self) -> None:
        assert compute_max_score({"impact_dimensions": []}) == 0


class TestGetMaxPerDimension:
    def test_redhat_ai_2026_max_per_dim_is_20(self) -> None:
        strategy = load_strategy("redhat-ai-2026")
        assert get_max_per_dimension(strategy) == 20

    def test_classic_max_per_dim_is_33(self) -> None:
        strategy = load_strategy("classic")
        assert get_max_per_dimension(strategy) == 33
