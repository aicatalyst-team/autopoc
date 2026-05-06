"""Strategy loader for RHOAI fitness evaluation.

Reads the strategy configuration, active strategy profile, and strategy
baseline YAML files from the ``data/`` directory.  These files define
the scoring dimensions, capability labels, enrichment/duplication
criteria, and relationship rules used by the evaluate agent.

The ``data/`` directory is resolved relative to the project root (two
levels above ``src/autopoc/tools/``).
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# data/ lives at the project root, alongside src/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"


def _resolve_data_dir() -> Path:
    """Return the path to the ``data/`` directory.

    Checks the standard project-root location first.  Falls back to
    ``DATA_DIR`` environment variable for deployed / relocated installs.

    Raises:
        FileNotFoundError: If the data directory cannot be found.
    """
    import os

    override = os.environ.get("AUTOPOC_DATA_DIR")
    if override:
        p = Path(override)
        if p.is_dir():
            return p

    if _DATA_DIR.is_dir():
        return _DATA_DIR

    raise FileNotFoundError(
        f"Strategy data directory not found at {_DATA_DIR}.  "
        "Set AUTOPOC_DATA_DIR to point to the data/ directory."
    )


def load_strategy_config() -> dict[str, Any]:
    """Read ``data/strategy_config.yaml`` and return the parsed dict.

    Returns:
        Dict with at least an ``active_strategy`` key.

    Raises:
        FileNotFoundError: If the config file is missing.
        ValueError: If ``active_strategy`` key is absent.
    """
    data_dir = _resolve_data_dir()
    config_path = data_dir / "strategy_config.yaml"

    if not config_path.is_file():
        raise FileNotFoundError(
            f"Strategy config not found: {config_path}.  Ensure data/strategy_config.yaml exists."
        )

    with open(config_path) as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict) or "active_strategy" not in config:
        raise ValueError(
            f"strategy_config.yaml must contain an 'active_strategy' key.  Got: {config!r}"
        )

    return config


def load_strategy(name: str | None = None) -> dict[str, Any]:
    """Load a strategy profile by name.

    If *name* is ``None``, reads the active strategy from
    ``strategy_config.yaml``.

    Args:
        name: Strategy name (e.g. ``"redhat-ai-2026"``).  Resolves to
            ``data/strategies/{name}.yaml``.

    Returns:
        Parsed strategy dict with keys like ``impact_dimensions``,
        ``feasibility_dimensions``, ``rerank``, etc.

    Raises:
        FileNotFoundError: If the strategy file is missing.
    """
    if name is None:
        config = load_strategy_config()
        name = config["active_strategy"]

    data_dir = _resolve_data_dir()
    strategy_path = data_dir / "strategies" / f"{name}.yaml"

    if not strategy_path.is_file():
        raise FileNotFoundError(
            f"Strategy profile not found: {strategy_path}.  "
            f"Available strategies: {_list_strategies(data_dir)}"
        )

    with open(strategy_path) as f:
        strategy = yaml.safe_load(f)

    logger.info(
        "Loaded strategy '%s' (v%s)", strategy.get("name", name), strategy.get("version", "?")
    )
    return strategy


def load_strategy_baseline(path: str | None = None) -> dict[str, Any]:
    """Load the strategy baseline YAML.

    The baseline contains strategy areas, capability labels,
    enrichment/duplication criteria, core products, and relationship
    rules.

    Args:
        path: Explicit path to the baseline file.  If ``None``, loads
            ``data/strategy-baseline.yaml``.

    Returns:
        Parsed baseline dict.

    Raises:
        FileNotFoundError: If the baseline file is missing.
    """
    if path is None:
        data_dir = _resolve_data_dir()
        baseline_path = data_dir / "strategy-baseline.yaml"
    else:
        # Resolve relative to data dir if not absolute
        p = Path(path)
        if not p.is_absolute():
            data_dir = _resolve_data_dir()
            # path may be "data/strategy-baseline.yaml" — strip leading data/
            if p.parts and p.parts[0] == "data":
                p = Path(*p.parts[1:])
            baseline_path = data_dir / p
        else:
            baseline_path = p

    if not baseline_path.is_file():
        raise FileNotFoundError(
            f"Strategy baseline not found: {baseline_path}.  "
            "Ensure data/strategy-baseline.yaml exists."
        )

    with open(baseline_path) as f:
        baseline = yaml.safe_load(f)

    logger.info(
        "Loaded strategy baseline (v%s): %d strategy areas, %d core products",
        baseline.get("version", "?"),
        len(baseline.get("strategy_areas", [])),
        len(baseline.get("core_products", [])),
    )
    return baseline


def get_scoring_dimensions(strategy: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract impact dimensions from a strategy profile.

    Each dimension dict has at least ``name`` and ``weight`` keys.

    Args:
        strategy: Parsed strategy dict (from :func:`load_strategy`).

    Returns:
        List of dimension dicts.

    Raises:
        ValueError: If no ``impact_dimensions`` key is found.
    """
    dims = strategy.get("impact_dimensions")
    if dims is None:
        raise ValueError(
            f"Strategy has no 'impact_dimensions'.  Keys found: {sorted(strategy.keys())}"
        )
    return dims


def compute_max_score(strategy: dict[str, Any]) -> int:
    """Compute the maximum possible evaluation score.

    For equal-weight dimensions summing to 100::

        max_per_dim = 100 // num_dimensions

    This assumes the standard convention where total score is 100 and
    each dimension gets an equal share.

    Args:
        strategy: Parsed strategy dict.

    Returns:
        Total maximum score (typically 100).
    """
    dims = get_scoring_dimensions(strategy)
    num_dims = len(dims)
    if num_dims == 0:
        return 0

    max_per_dim = 100 // num_dims
    return max_per_dim * num_dims


def get_max_per_dimension(strategy: dict[str, Any]) -> int:
    """Return the maximum score for a single dimension.

    Args:
        strategy: Parsed strategy dict.

    Returns:
        Max score per dimension (e.g. 20 for 5 dimensions).
    """
    dims = get_scoring_dimensions(strategy)
    if not dims:
        return 0
    return 100 // len(dims)


def _list_strategies(data_dir: Path) -> list[str]:
    """List available strategy names from the strategies/ directory."""
    strategies_dir = data_dir / "strategies"
    if not strategies_dir.is_dir():
        return []
    return sorted(p.stem for p in strategies_dir.glob("*.yaml"))
