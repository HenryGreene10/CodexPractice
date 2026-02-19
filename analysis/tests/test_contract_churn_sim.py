from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.contract_churn_sim import build_customer_shares, load_config, run_simulation


def _config_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "contract_churn_sim_config.json")


def test_customer_shares_sum_to_one() -> None:
    config = load_config(_config_path())
    shares = build_customer_shares(config)
    assert abs(sum(shares) - 1.0) < 1e-12


def test_top2_share_equals_45pct() -> None:
    config = load_config(_config_path())
    shares = build_customer_shares(config)
    assert abs(sum(shares[:2]) - 0.45) < 1e-12


def test_fixed_seed_stable_mean_and_median() -> None:
    config = load_config(_config_path())

    result = run_simulation(
        config=config,
        scenario_name="base",
        runs=2000,
        seed=42,
        threshold_high=1_000_000,
        threshold_low=800_000,
    )

    metrics = result["metrics"]
    assert abs(metrics["mean_ebitda"] - 917_118.6448140444) < 1e-6
    assert abs(metrics["median_ebitda"] - 932_532.6812350436) < 1e-6
    assert abs(metrics["expected_shortfall_vs_baseline"] - 82_888.2102011028) < 1e-6
    assert abs(metrics["prob_hit_gt_100k"] - 0.364) < 1e-12
    assert abs(metrics["prob_hit_gt_200k"] - 0.043) < 1e-12


def test_invalid_runs_rejected() -> None:
    config = load_config(_config_path())
    try:
        run_simulation(
            config=config,
            scenario_name="base",
            runs=0,
            seed=42,
            threshold_high=1_000_000,
            threshold_low=800_000,
        )
        raise AssertionError("Expected ValueError for runs=0")
    except ValueError as exc:
        assert "runs must be > 0" in str(exc)


if __name__ == "__main__":
    test_customer_shares_sum_to_one()
    test_top2_share_equals_45pct()
    test_fixed_seed_stable_mean_and_median()
    test_invalid_runs_rejected()
    print("All tests passed.")
