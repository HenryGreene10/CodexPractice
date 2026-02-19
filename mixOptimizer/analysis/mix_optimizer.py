#!/usr/bin/env python3
"""Mix Optimizer: branded vs. contract production under capacity/canning constraints."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any, Dict, List


def load_config(config_path: str | Path) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def resolve_scenario_config(config: Dict[str, Any], scenario_name: str) -> Dict[str, Any]:
    scenarios = config.get("scenarios", {})
    if scenario_name not in scenarios:
        available = ", ".join(sorted(scenarios.keys()))
        raise ValueError(f"Unknown scenario '{scenario_name}'. Available: {available}")

    resolved = copy.deepcopy(config)
    deep_merge(resolved, scenarios.get(scenario_name, {}))
    return resolved


def get_revenue_per_bbl(cfg: Dict[str, Any]) -> Dict[str, float]:
    assumptions = cfg["assumptions"]
    anchors = cfg["case_anchors"]
    mode = assumptions.get("revenue_per_bbl_mode", "assumed")

    if mode == "assumed":
        values = assumptions["revenue_per_bbl_assumed"]
        return {
            "branded": float(values["branded"]),
            "contract": float(values["contract"]),
        }

    if mode == "infer_from_assumed_volume_split":
        infer = assumptions["inferred_revenue_per_bbl"]
        total_basis_bbl = float(infer.get("volume_basis_bbl", anchors["current_production_bbl"]))
        branded_share = float(infer["assumed_branded_volume_share"])

        if total_basis_bbl <= 0:
            raise ValueError("inferred_revenue_per_bbl.volume_basis_bbl must be > 0")
        if not 0 < branded_share < 1:
            raise ValueError("inferred_revenue_per_bbl.assumed_branded_volume_share must be in (0, 1)")

        branded_bbl = total_basis_bbl * branded_share
        contract_bbl = total_basis_bbl * (1.0 - branded_share)

        return {
            "branded": float(anchors["branded_revenue_usd"]) / branded_bbl,
            "contract": float(anchors["contract_revenue_usd"]) / contract_bbl,
        }

    raise ValueError(
        "Unsupported revenue_per_bbl_mode. Use 'assumed' or 'infer_from_assumed_volume_split'."
    )


def compute_canning_hours(branded_bbl: int, contract_bbl: int, canning_cfg: Dict[str, Any]) -> float:
    hours_per_bbl = canning_cfg["canning_hours_per_bbl"]
    branded_hpbbl = float(hours_per_bbl["branded"])
    contract_hpbbl = float(hours_per_bbl["contract"])
    changeover_hours = float(canning_cfg["changeover_hours_per_run"])
    avg_run_size_bbl = float(canning_cfg["avg_run_size_bbl"])

    if avg_run_size_bbl <= 0:
        raise ValueError("assumptions.canning.avg_run_size_bbl must be > 0")

    branded_runs = branded_bbl / avg_run_size_bbl
    return (
        branded_bbl * branded_hpbbl
        + contract_bbl * contract_hpbbl
        + branded_runs * changeover_hours
    )


def _iter_values(min_value: int, max_value: int, step: int) -> List[int]:
    if step <= 0:
        raise ValueError("optimization.bbl_step must be > 0")
    if min_value > max_value:
        return []
    return list(range(min_value, max_value + 1, step))


def optimize_resolved_config(cfg: Dict[str, Any], scenario_name: str) -> Dict[str, Any]:
    anchors = cfg["case_anchors"]
    assumptions = cfg["assumptions"]
    optimization = cfg["optimization"]

    capacity_bbl = int(anchors["facility_capacity_bbl"])
    step = int(optimization.get("bbl_step", 100))

    demand = assumptions["demand_limits_bbl"]
    min_branded = int(demand.get("min_branded_bbl", 0))
    min_contract = int(demand.get("min_contract_bbl", 0))
    max_branded = int(min(demand.get("max_branded_bbl", capacity_bbl), capacity_bbl))
    max_contract = int(min(demand.get("max_contract_bbl", capacity_bbl), capacity_bbl))

    canning_cfg = assumptions["canning"]
    canning_capacity = float(canning_cfg["canning_hours_capacity"])

    rev_per_bbl = get_revenue_per_bbl(cfg)
    gross_margin = assumptions["gross_margin"]
    branded_gm = float(gross_margin["branded"])
    contract_gm = float(gross_margin["contract"])
    drop_through = float(assumptions.get("drop_through_to_ebitda", 1.0))

    best: Dict[str, Any] | None = None

    for branded_bbl in _iter_values(min_branded, max_branded, step):
        for contract_bbl in _iter_values(min_contract, max_contract, step):
            total_bbl = branded_bbl + contract_bbl
            if total_bbl > capacity_bbl:
                continue

            canning_hours_used = compute_canning_hours(branded_bbl, contract_bbl, canning_cfg)
            if canning_hours_used > canning_capacity + 1e-9:
                continue

            gross_profit = (
                rev_per_bbl["branded"] * branded_bbl * branded_gm
                + rev_per_bbl["contract"] * contract_bbl * contract_gm
            )
            ebitda_proxy = gross_profit * drop_through

            is_better = False
            if best is None:
                is_better = True
            elif gross_profit > best["gross_profit_usd"] + 1e-9:
                is_better = True
            elif abs(gross_profit - best["gross_profit_usd"]) <= 1e-9:
                # Deterministic tie-breaker: favor more branded volume.
                is_better = branded_bbl > best["branded_bbl"]

            if is_better:
                best = {
                    "scenario": scenario_name,
                    "branded_bbl": branded_bbl,
                    "contract_bbl": contract_bbl,
                    "total_bbl": total_bbl,
                    "canning_hours_used": canning_hours_used,
                    "gross_profit_usd": gross_profit,
                    "ebitda_proxy_usd": ebitda_proxy,
                }

    if best is None:
        raise ValueError(f"No feasible solution found for scenario '{scenario_name}'.")

    canning_util_pct = 0.0
    if canning_capacity > 0:
        canning_util_pct = 100.0 * best["canning_hours_used"] / canning_capacity

    hours_per_bbl = canning_cfg["canning_hours_per_bbl"]
    effective_branded_hour = (
        float(hours_per_bbl["branded"])
        + float(canning_cfg["changeover_hours_per_run"]) / float(canning_cfg["avg_run_size_bbl"])
    )
    effective_contract_hour = float(hours_per_bbl["contract"])
    one_step_hours = step * max(effective_branded_hour, effective_contract_hour)
    canning_slack = canning_capacity - best["canning_hours_used"]
    canning_binds = canning_slack <= (one_step_hours + 1e-9)

    baseline = assumptions.get("baseline_mix", {})
    baseline_total = int(baseline.get("total_bbl", anchors["current_production_bbl"]))
    baseline_branded_share = float(baseline.get("assumed_branded_share_bbl", 0.7))
    baseline_branded = int(round(baseline_total * baseline_branded_share / step) * step)
    baseline_contract = max(0, baseline_total - baseline_branded)

    baseline_gp = (
        rev_per_bbl["branded"] * baseline_branded * branded_gm
        + rev_per_bbl["contract"] * baseline_contract * contract_gm
    )

    blended_revenue = (
        rev_per_bbl["branded"] * best["branded_bbl"]
        + rev_per_bbl["contract"] * best["contract_bbl"]
    )
    blended_margin = (best["gross_profit_usd"] / blended_revenue) if blended_revenue > 0 else 0.0

    best.update(
        {
            "capacity_bbl": capacity_bbl,
            "canning_hours_capacity": canning_capacity,
            "canning_util_pct": canning_util_pct,
            "canning_binds": canning_binds,
            "canning_slack_hours": canning_slack,
            "branded_share_pct": (100.0 * best["branded_bbl"] / best["total_bbl"]) if best["total_bbl"] else 0.0,
            "contract_share_pct": (100.0 * best["contract_bbl"] / best["total_bbl"]) if best["total_bbl"] else 0.0,
            "baseline_total_bbl": baseline_total,
            "baseline_branded_bbl": baseline_branded,
            "baseline_contract_bbl": baseline_contract,
            "delta_total_bbl_vs_baseline": best["total_bbl"] - baseline_total,
            "delta_gp_vs_baseline_usd": best["gross_profit_usd"] - baseline_gp,
            "revenue_per_bbl": rev_per_bbl,
            "gross_margin": {"branded": branded_gm, "contract": contract_gm},
            "blended_margin_pct": 100.0 * blended_margin,
        }
    )

    return best


def optimize_for_scenario(config: Dict[str, Any], scenario_name: str) -> Dict[str, Any]:
    resolved = resolve_scenario_config(config, scenario_name)
    return optimize_resolved_config(resolved, scenario_name)


def optimize_with_override(
    config: Dict[str, Any], scenario_name: str, override: Dict[str, Any], label: str
) -> Dict[str, Any]:
    resolved = resolve_scenario_config(config, scenario_name)
    deep_merge(resolved, override)
    return optimize_resolved_config(resolved, label)


def format_currency(value: float) -> str:
    return f"${value:,.0f}"


def format_table(headers: List[str], rows: List[List[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def _fmt(row: List[str]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    sep = "-+-".join("-" * w for w in widths)
    lines = [_fmt(headers), sep]
    lines.extend(_fmt(row) for row in rows)
    return "\n".join(lines)


def build_scenario_table(config: Dict[str, Any]) -> str:
    scenario_order = ["base", "sku_bloat", "contract_push", "de_sku"]
    available = config.get("scenarios", {})

    rows: List[List[str]] = []
    for scenario_name in scenario_order:
        if scenario_name not in available:
            continue
        result = optimize_for_scenario(config, scenario_name)
        rows.append(
            [
                scenario_name,
                f"{result['branded_bbl']:,}",
                f"{result['contract_bbl']:,}",
                f"{result['total_bbl']:,}",
                f"{result['canning_util_pct']:.1f}%",
                f"{result['gross_profit_usd'] / 1_000_000:.2f}M",
            ]
        )

    headers = ["Scenario", "Branded BBL", "Contract BBL", "Total BBL", "Canning Util", "GP"]
    return format_table(headers, rows)


def run_sensitivity(config: Dict[str, Any], scenario_name: str) -> str:
    sensitivity = config.get("sensitivity", {})
    rows: List[List[str]] = []

    for value in sensitivity.get("changeover_hours_per_run", []):
        result = optimize_with_override(
            config,
            scenario_name,
            {"assumptions": {"canning": {"changeover_hours_per_run": value}}},
            f"changeover={value}",
        )
        rows.append(
            [
                "changeover_hours_per_run",
                f"{value:.2f}",
                f"{result['branded_share_pct']:.1f}%/{result['contract_share_pct']:.1f}%",
                f"{result['gross_profit_usd'] / 1_000_000:.2f}M",
            ]
        )

    for value in sensitivity.get("canning_hours_capacity", []):
        result = optimize_with_override(
            config,
            scenario_name,
            {"assumptions": {"canning": {"canning_hours_capacity": value}}},
            f"canning_cap={value}",
        )
        rows.append(
            [
                "canning_hours_capacity",
                f"{value:,.0f}",
                f"{result['branded_share_pct']:.1f}%/{result['contract_share_pct']:.1f}%",
                f"{result['gross_profit_usd'] / 1_000_000:.2f}M",
            ]
        )

    for value in sensitivity.get("contract_gm", []):
        result = optimize_with_override(
            config,
            scenario_name,
            {"assumptions": {"gross_margin": {"contract": value}}},
            f"contract_gm={value}",
        )
        rows.append(
            [
                "contract_gm",
                f"{value:.2f}",
                f"{result['branded_share_pct']:.1f}%/{result['contract_share_pct']:.1f}%",
                f"{result['gross_profit_usd'] / 1_000_000:.2f}M",
            ]
        )

    for value in sensitivity.get("branded_gm", []):
        result = optimize_with_override(
            config,
            scenario_name,
            {"assumptions": {"gross_margin": {"branded": value}}},
            f"branded_gm={value}",
        )
        rows.append(
            [
                "branded_gm",
                f"{value:.2f}",
                f"{result['branded_share_pct']:.1f}%/{result['contract_share_pct']:.1f}%",
                f"{result['gross_profit_usd'] / 1_000_000:.2f}M",
            ]
        )

    headers = ["Parameter", "Value", "Optimal Mix (B/C)", "GP"]
    return format_table(headers, rows)


def build_vp_insights(config: Dict[str, Any], selected: Dict[str, Any]) -> List[str]:
    base = optimize_for_scenario(config, "base")
    sku_bloat = optimize_for_scenario(config, "sku_bloat")
    contract_push = optimize_for_scenario(config, "contract_push")
    de_sku = optimize_for_scenario(config, "de_sku")

    mix_statement = (
        f"Under base assumptions, canning utilization is {base['canning_util_pct']:.1f}% "
        f"({'binding' if base['canning_binds'] else 'not binding'}), and the optimal mix is "
        f"{base['branded_share_pct']:.1f}% branded / {base['contract_share_pct']:.1f}% contract."
    )

    sku_delta_gp = sku_bloat["gross_profit_usd"] - base["gross_profit_usd"]
    sku_delta_bbl = sku_bloat["total_bbl"] - base["total_bbl"]
    sku_statement = (
        f"When low-velocity SKU burden increases (smaller runs, more changeovers), "
        f"effective throughput changes by {sku_delta_bbl:+,} BBL and GP changes by "
        f"{format_currency(sku_delta_gp)} vs base, reflecting the case warning that long-tail SKUs absorb disproportionate time."
    )

    de_sku_delta_gp = de_sku["gross_profit_usd"] - base["gross_profit_usd"]
    de_sku_delta_bbl = de_sku["total_bbl"] - base["total_bbl"]
    de_sku_statement = (
        f"SKU rationalization (larger average run size, fewer changeovers) unlocks about {de_sku_delta_bbl:+,} BBL and "
        f"{format_currency(de_sku_delta_gp)} GP vs base."
    )

    contract_push_delta_bbl = contract_push["contract_bbl"] - base["contract_bbl"]
    contract_push_delta_gp = contract_push["gross_profit_usd"] - base["gross_profit_usd"]
    contract_push_statement = (
        f"Higher contract demand availability fills idle capacity (+{contract_push_delta_bbl:,} contract BBL) and changes GP by "
        f"{format_currency(contract_push_delta_gp)} vs base, showing how contract can monetize headroom despite lower segment margins."
    )

    strategy_statement = (
        f"Given branded GM ({selected['gross_margin']['branded']:.0%}) exceeds contract GM ({selected['gross_margin']['contract']:.0%}) "
        f"but branded is more canning/changeover intensive, the practical plan is to protect core branded SKUs and batch long-tail branded runs."
    )

    return [
        mix_statement,
        sku_statement,
        de_sku_statement,
        contract_push_statement,
        strategy_statement,
    ]


def print_primary_result(result: Dict[str, Any]) -> None:
    print(f"Scenario: {result['scenario']}")
    print("Optimal mix:")
    print(f"  Branded BBL: {result['branded_bbl']:,}")
    print(f"  Contract BBL: {result['contract_bbl']:,}")
    print(f"  Total BBL: {result['total_bbl']:,} / {result['capacity_bbl']:,}")
    print(
        f"  Mix: {result['branded_share_pct']:.1f}% branded / {result['contract_share_pct']:.1f}% contract"
    )
    print("Canning constraint:")
    print(
        f"  Used: {result['canning_hours_used']:.1f} / {result['canning_hours_capacity']:.1f} hours "
        f"({result['canning_util_pct']:.1f}%)"
    )
    print(f"  Binding: {'yes' if result['canning_binds'] else 'no'}")
    print("Economics:")
    print(f"  Gross profit contribution: {format_currency(result['gross_profit_usd'])}")
    print(f"  EBITDA proxy: {format_currency(result['ebitda_proxy_usd'])}")
    print(
        f"  Delta vs baseline (assumed {result['baseline_total_bbl']:,} BBL current state): "
        f"{result['delta_total_bbl_vs_baseline']:+,} BBL, "
        f"{format_currency(result['delta_gp_vs_baseline_usd'])} GP"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mix optimizer for branded vs contract production under capacity and canning constraints."
    )
    parser.add_argument(
        "--config",
        default="analysis/mix_optimizer_config.json",
        help="Path to JSON config file.",
    )
    parser.add_argument(
        "--scenario",
        default="base",
        help="Scenario name from config.scenarios (default: base).",
    )
    parser.add_argument(
        "--sensitivity",
        action="store_true",
        help="Run one-way sensitivity table for the selected scenario.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)

    selected_result = optimize_for_scenario(cfg, args.scenario)
    print_primary_result(selected_result)

    print("\nScenario comparison:")
    print(build_scenario_table(cfg))

    if args.sensitivity:
        print("\nSensitivity (one-way):")
        print(run_sensitivity(cfg, args.scenario))

    print("\nVP-ready insights:")
    for bullet in build_vp_insights(cfg, selected_result):
        print(f"- {bullet}")


if __name__ == "__main__":
    main()
