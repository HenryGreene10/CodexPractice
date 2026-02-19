# PCBC Contract Churn Monte Carlo Simulator

## What this tool is (and is not)
This tool is a **decision-support risk simulator** for earnings quality in PCBC's contract business. It estimates a distribution of EBITDA outcomes over the next 12 months under churn, downsell, and backfill assumptions.

It is **not** an LBO model, full company forecast, or valuation model.

## Case anchors (hard-coded defaults)
These values are taken from the Orkila case packet and loaded from `analysis/contract_churn_sim_config.json`:
- LTM total revenue: **$12.4M**
- LTM contract revenue: **$3.2M** (~25% of total)
- LTM EBITDA: **$1.0M**
- Contract clients: **~8**
- Top 2 contract customers: **~45%** of contract revenue (22.5% each)
- Contract terms: **short-term (6-12 months), limited volume commitments**
- Contract gross margin case language: **"mid-20s%"**

## Modeling assumptions and logic
The model simulates 8 customers each run:
1. Renewal/churn using scenario renewal means (`top2_mean`, `rest_mean`)
2. If renewed, revenue is adjusted by triangular downsell factor (`low`, `mode`, `high`)
3. Lost revenue is partially recovered via `backfill_fraction`
4. EBITDA impact is mapped via:
   - `delta_contract_revenue = simulated_contract_revenue - 3.2M`
   - `delta_gp = delta_contract_revenue * gm_contract`
   - `delta_ebitda = delta_gp * drop_through`
   - `ebitda_sim = 1.0M + delta_ebitda`

Reproducibility is built in via `--seed` (default `42`).

## Scenarios
Configured in `analysis/contract_churn_sim_config.json`:
- `base`: moderate renewal, conservative 25% backfill
- `downside`: lower renewal, 0% backfill, harsher conversion to EBITDA
- `upside`: stronger renewal and 50% backfill
- `de_risked`: proxy for longer contracts (higher renewal, tighter downsell range)

## How to run
- Base: `python3 analysis/contract_churn_sim.py --scenario base`
- Downside: `python3 analysis/contract_churn_sim.py --scenario downside`
- Upside: `python3 analysis/contract_churn_sim.py --scenario upside`
- De-risked: `python3 analysis/contract_churn_sim.py --scenario de_risked`
- Custom runs/seed: `python3 analysis/contract_churn_sim.py --scenario base --runs 20000 --seed 123`
- Custom thresholds: `python3 analysis/contract_churn_sim.py --scenario base --thresholds 1000000 800000`
- Export CSV: `python3 analysis/contract_churn_sim.py --scenario base --export_csv analysis/output/base_runs.csv`

## Interpreting output for VP discussion
Focus on:
- **Probability of EBITDA below gates** (`$1.0M`, `$0.8M`)
- **Tail risk** (`P10`, `P5`) vs median
- **Concentration risk** through top-2 churn rates
- **Mitigation value** from higher top-2 renewal and backfill in VP bullet section
- **Sensitivity table** to show which assumptions move P10 most

Example talking points:
- The current contract book can create a wide downside tail even with moderate renewal assumptions.
- Top-2 renewals are the fastest lever to improve downside protection.
- Backfill helps, but impact depends on gross margin and drop-through assumptions.
- "De-risked" terms mainly compress tail downside (P10/P5), even if mean changes are modest.
- Use thresholds as management gates, not point forecasts.

## Example outputs (captured from actual runs)
Commands used:
- `python3 analysis/contract_churn_sim.py --scenario base --runs 5000 --seed 42`
- `python3 analysis/contract_churn_sim.py --scenario downside --runs 5000 --seed 42`
- `python3 analysis/contract_churn_sim.py --scenario upside --runs 5000 --seed 42`
- `python3 analysis/contract_churn_sim.py --scenario de_risked --runs 5000 --seed 42`

### Base (excerpt)
```text
Summary risk metrics:
- Expected EBITDA (mean): $916,383
- Median EBITDA: $923,490
- P10 EBITDA: $824,834
- P5 EBITDA: $803,580
- P(EBITDA < $1,000,000): 99.6%
- P(EBITDA < $800,000): 4.5%
- Expected contract revenue retained: 85.1%

VP-ready implications:
- In base, there is a 99.6% probability EBITDA falls below $1,000,000, with concentration risk centered on top-2 renewals.
- Tail downside remains material: P10 EBITDA is $824,834 and P5 is $803,580.
- Increasing top-2 renewal mean by +10 pts lifts P10 EBITDA by ~$33,843.
- Adding +25 pts backfill (capped at 50%) improves P10 EBITDA by ~$58,389.
- Expected contract revenue retained is 85.1% of the $3,200,000 contract base.
```

### Downside (excerpt)
```text
Summary risk metrics:
- Expected EBITDA (mean): $802,804
- Median EBITDA: $812,277
- P10 EBITDA: $663,458
- P5 EBITDA: $629,669
- P(EBITDA < $1,000,000): 100.0%
- P(EBITDA < $800,000): 47.4%
- Expected contract revenue retained: 68.9%

VP-ready implications:
- In downside, there is a 100.0% probability EBITDA falls below $1,000,000, with concentration risk centered on top-2 renewals.
- Tail downside remains material: P10 EBITDA is $663,458 and P5 is $629,669.
- Increasing top-2 renewal mean by +10 pts lifts P10 EBITDA by ~$44,688.
- Adding +25 pts backfill (capped at 50%) improves P10 EBITDA by ~$84,136.
- Expected contract revenue retained is 68.9% of the $3,200,000 contract base.
```

### Upside (excerpt)
```text
Summary risk metrics:
- Expected EBITDA (mean): $978,981
- Median EBITDA: $983,116
- P10 EBITDA: $935,329
- P5 EBITDA: $927,932
- P(EBITDA < $1,000,000): 71.7%
- P(EBITDA < $800,000): 0.0%
- Expected contract revenue retained: 95.3%

VP-ready implications:
- In upside, there is a 71.7% probability EBITDA falls below $1,000,000, with concentration risk centered on top-2 renewals.
- Tail downside remains material: P10 EBITDA is $935,329 and P5 is $927,932.
- Increasing top-2 renewal mean by +10 pts lifts P10 EBITDA by ~$26,044.
- Adding +25 pts backfill (capped at 50%) improves P10 EBITDA by ~$0.
- Expected contract revenue retained is 95.3% of the $3,200,000 contract base.
```

### De-risked (excerpt)
```text
Summary risk metrics:
- Expected EBITDA (mean): $962,462
- Median EBITDA: $992,153
- P10 EBITDA: $901,507
- P5 EBITDA: $865,555
- P(EBITDA < $1,000,000): 91.7%
- P(EBITDA < $800,000): 0.6%
- Expected contract revenue retained: 93.3%

VP-ready implications:
- In de_risked, there is a 91.7% probability EBITDA falls below $1,000,000, with concentration risk centered on top-2 renewals.
- Tail downside remains material: P10 EBITDA is $901,507 and P5 is $865,555.
- Increasing top-2 renewal mean by +10 pts lifts P10 EBITDA by ~$54,402.
- Adding +25 pts backfill (capped at 50%) improves P10 EBITDA by ~$32,831.
- Expected contract revenue retained is 93.3% of the $3,200,000 contract base.
```

Note: each run also prints a full 81-row sensitivity table for P10 EBITDA across `(gm_contract, drop_through, top2_renewal_mean, backfill)` combinations.
