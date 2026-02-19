#!/usr/bin/env python3
"""PCBC contract churn Monte Carlo earnings-quality simulator.

This is a decision-support distribution model, not an LBO or full forecast.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Tuple


def load_config(config_path: str) -> Dict:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_customer_shares(config: Dict) -> List[float]:
    allocation = config["model_defaults"]["customer_allocation"]
    top_share_each = allocation["top2_share_each"]
    rest_count = allocation["rest_customer_count"]
    rest_share_total = allocation["rest_share_total"]

    if rest_count <= 0:
        raise ValueError("rest_customer_count must be > 0")

    shares = [top_share_each, top_share_each]
    per_rest = rest_share_total / rest_count
    shares.extend([per_rest] * rest_count)

    total = sum(shares)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"Customer shares must sum to 1.0 (got {total:.12f})")
    return shares


def percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        raise ValueError("Cannot compute percentile on empty list")
    if pct < 0 or pct > 100:
        raise ValueError("pct must be between 0 and 100")

    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    fraction = rank - low
    return sorted_values[low] * (1.0 - fraction) + sorted_values[high] * fraction


def format_currency(value: float) -> str:
    return f"${value:,.0f}"


def validate_scenario_params(scenario_name: str, scenario: Dict) -> None:
    renewal = scenario["renewal_probs"]
    downsizing = scenario["downsizing_factor"]

    for label in ("top2_mean", "rest_mean"):
        val = renewal[label]
        if val < 0 or val > 1:
            raise ValueError(f"{scenario_name}: {label} must be between 0 and 1")

    low = downsizing["low"]
    mode = downsizing["mode"]
    high = downsizing["high"]
    if low <= 0 or mode <= 0 or high <= 0:
        raise ValueError(f"{scenario_name}: downsizing params must be > 0")
    if not (low <= mode <= high):
        raise ValueError(f"{scenario_name}: downsizing must satisfy low <= mode <= high")

    backfill = scenario["backfill_fraction"]
    gm = scenario["gm_contract"]
    drop = scenario["drop_through"]

    if backfill < 0 or backfill > 1:
        raise ValueError(f"{scenario_name}: backfill_fraction must be between 0 and 1")
    if gm < 0 or gm > 1:
        raise ValueError(f"{scenario_name}: gm_contract must be between 0 and 1")
    if drop < 0 or drop > 1:
        raise ValueError(f"{scenario_name}: drop_through must be between 0 and 1")


def run_simulation(
    config: Dict,
    scenario_name: str,
    runs: int,
    seed: int,
    threshold_high: float,
    threshold_low: float,
    scenario_overrides: Dict | None = None,
) -> Dict:
    if runs <= 0:
        raise ValueError("runs must be > 0")
    if threshold_high < 0 or threshold_low < 0:
        raise ValueError("thresholds must be non-negative")

    scenarios = config["scenarios"]
    if scenario_name not in scenarios:
        raise ValueError(f"Unknown scenario '{scenario_name}'. Available: {', '.join(sorted(scenarios))}")

    scenario = deepcopy(scenarios[scenario_name])
    if scenario_overrides:
        for key, value in scenario_overrides.items():
            if key == "renewal_probs_top2_mean":
                scenario["renewal_probs"]["top2_mean"] = value
            elif key == "renewal_probs_rest_mean":
                scenario["renewal_probs"]["rest_mean"] = value
            elif key == "backfill_fraction":
                scenario["backfill_fraction"] = value
            elif key == "gm_contract":
                scenario["gm_contract"] = value
            elif key == "drop_through":
                scenario["drop_through"] = value
            else:
                scenario[key] = value

    validate_scenario_params(scenario_name, scenario)

    anchors = config["anchors"]
    base_contract_rev = anchors["ltm_contract_revenue"]
    base_ebitda = anchors["ltm_ebitda"]
    shares = build_customer_shares(config)

    renewal_top2 = scenario["renewal_probs"]["top2_mean"]
    renewal_rest = scenario["renewal_probs"]["rest_mean"]
    downsizing = scenario["downsizing_factor"]
    gm_contract = scenario["gm_contract"]
    drop_through = scenario["drop_through"]
    backfill_fraction = scenario["backfill_fraction"]

    rng = random.Random(seed)

    ebitda_results: List[float] = []
    contract_results: List[float] = []

    top2_churn_count = 0
    rest_churn_count = 0

    for _ in range(runs):
        kept_revenue = 0.0

        for idx, share in enumerate(shares):
            is_top2 = idx < 2
            renew_prob = renewal_top2 if is_top2 else renewal_rest
            renewed = rng.random() < renew_prob

            if renewed:
                factor = rng.triangular(downsizing["low"], downsizing["high"], downsizing["mode"])
                kept_revenue += base_contract_rev * share * factor
            else:
                if is_top2:
                    top2_churn_count += 1
                else:
                    rest_churn_count += 1

        lost_revenue = max(base_contract_rev - kept_revenue, 0.0)
        backfill_revenue = lost_revenue * backfill_fraction
        simulated_contract_revenue = kept_revenue + backfill_revenue

        delta_contract_revenue = simulated_contract_revenue - base_contract_rev
        delta_gp = delta_contract_revenue * gm_contract
        delta_ebitda = delta_gp * drop_through
        simulated_ebitda = base_ebitda + delta_ebitda

        ebitda_results.append(simulated_ebitda)
        contract_results.append(simulated_contract_revenue)

    sorted_ebitda = sorted(ebitda_results)
    mean_ebitda = statistics.fmean(ebitda_results)
    median_ebitda = statistics.median(ebitda_results)
    p10_ebitda = percentile(sorted_ebitda, 10)
    p5_ebitda = percentile(sorted_ebitda, 5)

    prob_below_high = sum(1 for x in ebitda_results if x < threshold_high) / runs
    prob_below_low = sum(1 for x in ebitda_results if x < threshold_low) / runs

    mean_contract = statistics.fmean(contract_results)
    retained_pct = mean_contract / base_contract_rev

    top2_churn_rate = top2_churn_count / (runs * 2)
    rest_count = len(shares) - 2
    rest_churn_rate = rest_churn_count / (runs * rest_count)

    return {
        "scenario_name": scenario_name,
        "runs": runs,
        "seed": seed,
        "threshold_high": threshold_high,
        "threshold_low": threshold_low,
        "params": scenario,
        "anchors": anchors,
        "metrics": {
            "mean_ebitda": mean_ebitda,
            "median_ebitda": median_ebitda,
            "p10_ebitda": p10_ebitda,
            "p5_ebitda": p5_ebitda,
            "prob_below_high": prob_below_high,
            "prob_below_low": prob_below_low,
            "mean_contract_revenue": mean_contract,
            "retained_pct": retained_pct,
            "top2_churn_rate": top2_churn_rate,
            "rest_churn_rate": rest_churn_rate,
        },
        "raw": {
            "ebitda": ebitda_results,
            "contract_revenue": contract_results,
        },
    }


def print_assumptions(result: Dict) -> None:
    anchors = result["anchors"]
    params = result["params"]

    print("=" * 72)
    print(f"PCBC Contract Churn Monte Carlo | Scenario: {result['scenario_name']}")
    print("=" * 72)
    print("Case anchors:")
    print(
        f"- LTM total revenue: {format_currency(anchors['ltm_total_revenue'])} | "
        f"contract revenue: {format_currency(anchors['ltm_contract_revenue'])} | "
        f"LTM EBITDA: {format_currency(anchors['ltm_ebitda'])}"
    )
    print(
        f"- Contract clients: ~{anchors['contract_client_count']} | "
        f"top-2 share: {anchors['top2_contract_share'] * 100:.1f}% | "
        f"terms: {anchors['contract_term_months']} months"
    )
    print("Simulation assumptions:")
    print(
        f"- Runs: {result['runs']:,} | Seed: {result['seed']} | "
        f"Thresholds: {format_currency(result['threshold_high'])}, {format_currency(result['threshold_low'])}"
    )
    print(
        "- Renewal means (top2/rest): "
        f"{params['renewal_probs']['top2_mean']:.2f} / {params['renewal_probs']['rest_mean']:.2f}"
    )
    print(
        "- Downsell factor triangular(low/mode/high): "
        f"{params['downsizing_factor']['low']:.2f} / "
        f"{params['downsizing_factor']['mode']:.2f} / {params['downsizing_factor']['high']:.2f}"
    )
    print(
        f"- Backfill: {params['backfill_fraction'] * 100:.0f}% | "
        f"Contract GM: {params['gm_contract'] * 100:.0f}% | "
        f"Drop-through: {params['drop_through'] * 100:.0f}%"
    )
    print()


def print_summary(result: Dict) -> None:
    m = result["metrics"]
    t1 = result["threshold_high"]
    t2 = result["threshold_low"]

    print("Summary risk metrics:")
    print(f"- Expected EBITDA (mean): {format_currency(m['mean_ebitda'])}")
    print(f"- Median EBITDA: {format_currency(m['median_ebitda'])}")
    print(f"- P10 EBITDA: {format_currency(m['p10_ebitda'])}")
    print(f"- P5 EBITDA: {format_currency(m['p5_ebitda'])}")
    print(f"- P(EBITDA < {format_currency(t1)}): {m['prob_below_high'] * 100:.1f}%")
    print(f"- P(EBITDA < {format_currency(t2)}): {m['prob_below_low'] * 100:.1f}%")
    print(f"- Expected contract revenue retained: {m['retained_pct'] * 100:.1f}%")
    print()

    print("Observed churn rates by segment (from simulation):")
    print("| Segment | Churn Rate |")
    print("|---|---:|")
    print(f"| Top 2 customers | {m['top2_churn_rate'] * 100:.1f}% |")
    print(f"| Other 6 customers | {m['rest_churn_rate'] * 100:.1f}% |")
    print()


def build_sensitivity_table(
    config: Dict,
    scenario_name: str,
    runs: int,
    seed: int,
    threshold_high: float,
    threshold_low: float,
) -> List[Tuple[float, float, float, float, float]]:
    gm_values = [0.22, 0.25, 0.28]
    drop_values = [0.5, 0.7, 0.9]
    top2_values = [0.70, 0.80, 0.90]
    backfill_values = [0.0, 0.25, 0.50]

    rows: List[Tuple[float, float, float, float, float]] = []

    for gm in gm_values:
        for drop in drop_values:
            for top2 in top2_values:
                for backfill in backfill_values:
                    sensitivity_result = run_simulation(
                        config=config,
                        scenario_name=scenario_name,
                        runs=runs,
                        seed=seed,
                        threshold_high=threshold_high,
                        threshold_low=threshold_low,
                        scenario_overrides={
                            "gm_contract": gm,
                            "drop_through": drop,
                            "renewal_probs_top2_mean": top2,
                            "backfill_fraction": backfill,
                        },
                    )
                    p10 = sensitivity_result["metrics"]["p10_ebitda"]
                    rows.append((gm, drop, top2, backfill, p10))

    rows.sort(key=lambda x: x[4])
    return rows


def print_sensitivity_table(rows: List[Tuple[float, float, float, float, float]]) -> None:
    print("Sensitivity table: P10 EBITDA across assumption grid")
    print("| gm_contract | drop_through | top2_renewal_mean | backfill | P10 EBITDA |")
    print("|---:|---:|---:|---:|---:|")
    for gm, drop, top2, backfill, p10 in rows:
        print(f"| {gm:.2f} | {drop:.2f} | {top2:.2f} | {backfill:.2f} | {format_currency(p10)} |")
    print()


def build_vp_bullets(
    config: Dict,
    base_result: Dict,
) -> List[str]:
    scenario_name = base_result["scenario_name"]
    runs = base_result["runs"]
    seed = base_result["seed"]
    t_high = base_result["threshold_high"]
    t_low = base_result["threshold_low"]

    base_metrics = base_result["metrics"]

    # What-if 1: top-2 renewal +10 points
    boosted_top2 = min(1.0, base_result["params"]["renewal_probs"]["top2_mean"] + 0.10)
    top2_result = run_simulation(
        config,
        scenario_name,
        runs,
        seed,
        t_high,
        t_low,
        scenario_overrides={"renewal_probs_top2_mean": boosted_top2},
    )

    # What-if 2: add +25% backfill (capped at 50%)
    boosted_backfill = min(0.50, base_result["params"]["backfill_fraction"] + 0.25)
    backfill_result = run_simulation(
        config,
        scenario_name,
        runs,
        seed,
        t_high,
        t_low,
        scenario_overrides={"backfill_fraction": boosted_backfill},
    )

    p10_improve_top2 = top2_result["metrics"]["p10_ebitda"] - base_metrics["p10_ebitda"]
    p10_improve_backfill = backfill_result["metrics"]["p10_ebitda"] - base_metrics["p10_ebitda"]

    bullets = [
        (
            f"In {scenario_name}, there is a {base_metrics['prob_below_high'] * 100:.1f}% probability "
            f"EBITDA falls below {format_currency(t_high)}, with concentration risk centered on top-2 renewals."
        ),
        (
            f"Tail downside remains material: P10 EBITDA is {format_currency(base_metrics['p10_ebitda'])} "
            f"and P5 is {format_currency(base_metrics['p5_ebitda'])}."
        ),
        (
            f"Increasing top-2 renewal mean by +10 pts lifts P10 EBITDA by "
            f"~{format_currency(p10_improve_top2)}."
        ),
        (
            f"Adding +25 pts backfill (capped at 50%) improves P10 EBITDA by "
            f"~{format_currency(p10_improve_backfill)}."
        ),
        (
            f"Expected contract revenue retained is {base_metrics['retained_pct'] * 100:.1f}% of "
            f"the {format_currency(base_result['anchors']['ltm_contract_revenue'])} contract base."
        ),
    ]
    return bullets


def print_vp_bullets(bullets: List[str]) -> None:
    print("VP-ready implications:")
    for bullet in bullets:
        print(f"- {bullet}")
    print()


def export_csv(path: str, result: Dict) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ebitda = result["raw"]["ebitda"]
    contract = result["raw"]["contract_revenue"]
    base_contract_rev = result["anchors"]["ltm_contract_revenue"]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "run_index",
                "scenario",
                "seed",
                "simulated_ebitda",
                "simulated_contract_revenue",
                "retained_pct_of_base_contract",
            ]
        )
        for idx, (ebitda_val, contract_val) in enumerate(zip(ebitda, contract), start=1):
            writer.writerow(
                [
                    idx,
                    result["scenario_name"],
                    result["seed"],
                    f"{ebitda_val:.6f}",
                    f"{contract_val:.6f}",
                    f"{(contract_val / base_contract_rev):.6f}",
                ]
            )


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PCBC contract churn Monte Carlo simulator (earnings-quality risk distribution)."
    )
    parser.add_argument("--scenario", default="base", help="Scenario name from config (default: base)")
    parser.add_argument("--runs", type=int, default=None, help="Number of Monte Carlo runs")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument(
        "--thresholds",
        nargs=2,
        type=float,
        metavar=("CURRENT", "STRESS"),
        default=None,
        help="Two EBITDA thresholds, e.g. --thresholds 1000000 800000",
    )
    parser.add_argument(
        "--export_csv",
        default=None,
        help="Optional path to export run-level results as CSV",
    )
    parser.add_argument(
        "--config",
        default="analysis/contract_churn_sim_config.json",
        help="Path to JSON config",
    )
    return parser.parse_args(argv)


def normalize_scenario_name(name: str) -> str:
    aliases = {
        "optimistic": "upside",
    }
    return aliases.get(name, name)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    config = load_config(args.config)

    scenario_name = normalize_scenario_name(args.scenario)

    defaults = config["model_defaults"]
    runs = args.runs if args.runs is not None else defaults["runs"]
    seed = args.seed if args.seed is not None else defaults["seed"]

    if args.thresholds is not None:
        threshold_high, threshold_low = args.thresholds
    else:
        threshold_high, threshold_low = defaults["thresholds"]

    result = run_simulation(
        config=config,
        scenario_name=scenario_name,
        runs=runs,
        seed=seed,
        threshold_high=threshold_high,
        threshold_low=threshold_low,
    )

    print_assumptions(result)
    print_summary(result)

    sensitivity_rows = build_sensitivity_table(
        config=config,
        scenario_name=scenario_name,
        runs=runs,
        seed=seed,
        threshold_high=threshold_high,
        threshold_low=threshold_low,
    )
    print_sensitivity_table(sensitivity_rows)

    bullets = build_vp_bullets(config, result)
    print_vp_bullets(bullets)

    if args.export_csv:
        export_csv(args.export_csv, result)
        print(f"Exported run-level CSV to: {args.export_csv}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
