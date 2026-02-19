# Mix Optimizer (Program B)

## What this is
A lightweight decision-support CLI that optimizes Branded BBL vs Contract BBL under:
- brewhouse capacity,
- canning-line capacity,
- branded changeover complexity (via average run size).

Objective: maximize gross profit contribution (with optional EBITDA proxy via drop-through).

## What this is not
- Not a full production scheduler.
- Not a detailed SKU-by-SKU planning model.
- Not a hard forecast of future demand.

It is intentionally explainable and assumption-driven for VP-level strategy discussion.

## Case anchors vs assumptions

### Hard-coded case anchors (from Orkila case packet)
These are defaults in `analysis/mix_optimizer_config.json` under `case_anchors`:
- Facility capacity: `60,000 BBL`
- Current production: `~32,000 BBL` (~53% utilization)
- Excess headroom: `~28,000 BBL`
- LTM net revenue: `$12.4M`
- Branded revenue: `$9.2M`
- Contract revenue: `$3.2M`
- Contract business scale: `~8 clients`; contract revenue about `25%` of total
- Margin reference points: branded in the mid-40%s, contract in the mid-20%s
- SKU complexity context: branded has `30+` SKUs and low-velocity SKUs consume disproportionate production time/working capital
- Canning line context: upgraded and commercially attractive for contract work, but increasingly a scheduling bottleneck

### Configurable assumptions (explicitly not in packet)
The packet does not provide numeric canning-hour capacity or changeover times. These are assumptions under `assumptions`:
- `canning_hours_capacity`
- `canning_hours_per_bbl` by stream
- `changeover_hours_per_run`
- `avg_run_size_bbl`
- demand ceilings (`max_branded_bbl`, `max_contract_bbl`)
- revenue per BBL mode and values
- EBITDA drop-through

#### Near-term demand caps
- The case packet does not provide explicit segment demand ceilings.
- `max_branded_bbl` and `max_contract_bbl` are included to prevent unrealistic infinite-demand outcomes.
- These represent near-term commercial constraints (distribution reach, branded demand depth, and contract availability).
- Stress-testing these caps is important; the CLI now includes one-way sensitivity on branded demand cap.

## Model structure
Decision variables:
- `branded_bbl`
- `contract_bbl`

Constraints:
1. Brewhouse capacity:
- `branded_bbl + contract_bbl <= 60,000`

2. Canning bottleneck:
- `branded_bbl * branded_hours_per_bbl`
- `+ contract_bbl * contract_hours_per_bbl`
- `+ branded_runs * changeover_hours_per_run`
- `<= canning_hours_capacity`

Where:
- `branded_runs = branded_bbl / avg_run_size_bbl`

Objective:
- Maximize gross profit contribution:
- `GP = (branded_rev_per_bbl * branded_bbl * branded_gm)`
- `   + (contract_rev_per_bbl * contract_bbl * contract_gm)`

Reported additionally:
- `EBITDA proxy = GP * drop_through_to_ebitda`

## Revenue per BBL modes
Configured by `assumptions.revenue_per_bbl_mode`:
1. `assumed` (default): direct assumed `revenue_per_bbl_assumed`.
2. `infer_from_assumed_volume_split`: infer from case anchor revenue plus assumed segment BBL split (`inferred_revenue_per_bbl`).

## Scenarios included
- `base`
- `sku_bloat` (higher changeover burden, smaller average runs)
- `contract_push` (more contract demand available)
- `de_sku` (SKU rationalization: lower changeover burden, larger runs)

## CLI usage
From repo root:

```bash
python3 analysis/mix_optimizer.py --scenario base
python3 analysis/mix_optimizer.py --scenario sku_bloat
python3 analysis/mix_optimizer.py --sensitivity
python3 analysis/mix_optimizer.py --config analysis/mix_optimizer_config.json
```

## Example output (base)

```text
Scenario: base
Optimal mix:
  Branded BBL: 40,000
  Contract BBL: 17,000
  Total BBL: 57,000 / 60,000
Canning constraint:
  Used: 11412.4 / 12000.0 hours (95.1%)
  Binding: no
```

## Interpreting outputs
- **Optimal mix**: recommended branded/contract volumes.
- **Canning binding flag**: whether canning capacity is effectively the active bottleneck.
- **Scenario comparison table**: quick side-by-side economics for base/sku_bloat/contract_push/de_sku.
- **Sensitivity table** (`--sensitivity`): one-way shifts in mix and GP for key uncertain inputs.
- **VP-ready insights**: concise strategy bullets tied to the case framing (SKU complexity, canning bottleneck, contract fill vs margin dilution).
- **Demand-cap interpretation**: if demand caps bind, the optimizer is signaling demand is the bottleneck; contract is the monetization path until branded demand grows.
- **Financial interpretation note**: contribution and EBITDA outputs are comparative mix economics for directional decision support, not audited accounting financials.

## Tests
Run:

```bash
python3 -m unittest discover -s analysis/tests
```

Tests cover:
- solution feasibility under constraints,
- determinism for fixed config,
- sanity case where huge canning capacity pushes solution to the higher-contribution stream.
