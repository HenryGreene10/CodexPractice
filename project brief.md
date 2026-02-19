# Project Brief: PCBC Contract Churn Monte Carlo (Earnings Quality Simulator)

## Goal
Build a small, defensible Monte Carlo simulator that quantifies earnings-quality risk for PCBC's contract production business:
- Expected EBITDA impact distribution from contract churn/renewal uncertainty
- Downside risk metrics (P10/P5 EBITDA, probability EBITDA below thresholds)
- Scenario outputs that translate directly into VP-level talking points

This is not an LBO model. It is a risk-distribution model with gating thresholds.

## Source Facts (Default Anchors)
Hard-code these defaults from the Orkila case packet:
- LTM total revenue: `12.4M`
- LTM contract revenue: `3.2M` (~25% of total)
- LTM EBITDA: `1.0M`
- Contract clients: `~8`
- Top 2 clients: `~45%` of contract revenue
- Contract terms: short-term (6-12 months), limited volume commitments
- Contract gross margin: "mid-20s%" (default `25%`)

## Model Scope
Simulate annual EBITDA outcomes over a 12-month horizon using:
1. Contract customer renewal/churn
2. Partial volume downsell (or modest growth) on renewals
3. Optional replacement wins to backfill lost volume
4. EBITDA translation from contract revenue deltas

Primary output is a distribution of EBITDA outcomes, not a point estimate.

## Core Modeling Choices

### Customer Revenue Allocation
- Total contract revenue fixed at `3.2M`
- Customer 1 share: `22.5%`
- Customer 2 share: `22.5%`
- Remaining `55%` split across 6 customers (default equal `9.166%` each)
- Optional: Dirichlet allocation for smaller customers

### Renewal/Churn Probabilities
- Top 2 renewal probability: `p_top ~ Beta(a,b)` with configurable mean `0.70-0.85`
- Remaining customers: `p_rest ~ Beta(a,b)` with configurable mean `0.75-0.90`
- Default design: top-2 renewal mean slightly lower (concentration risk)

Conditional downsell on renewal:
- `d ~ Triangular(low=0.85, mode=1.00, high=1.05)`

### Replacement/Backfill
If revenue is lost, recover fraction `f_fill`:
- Default scenario values: `0%`, `25%`, `50%`
- Optional stochastic mode: `f_fill ~ Beta(...)`

Conservative default is required due to informal pipeline/no dedicated BD.

### EBITDA Impact Mapping
Use:
- `gm_contract` range `0.22-0.28` (default `0.25`)
- `drop_through` range `0.5-0.9` (default `0.7`)

Formula:
```text
delta_gp = delta_contract_revenue * gm_contract
delta_ebitda = delta_gp * drop_through
EBITDA_sim = base_ebitda + delta_ebitda
```

Assume branded EBITDA is unchanged over the 12-month horizon.

## Required Outputs

### 1) Summary Risk Metrics
Print:
- Mean EBITDA
- Median EBITDA
- P10 and P5 EBITDA
- `P(EBITDA < 0.8M)` (configurable threshold)
- `P(EBITDA < 1.0M)` (below current level)
- Expected contract revenue retained (%)

### 2) Sensitivity (Tornado-Style) Table
Show P10 EBITDA across:
- `gm_contract`: `22%`, `25%`, `28%`
- `drop_through`: `50%`, `70%`, `90%`
- Top renewal mean: `70%`, `80%`, `90%`
- Fill fraction: `0%`, `25%`, `50%`

### 3) VP-Ready Implication Strings
Auto-generate 3-5 bullets, e.g.:
- "With current concentration and short-term contracts, there is X% probability EBITDA falls below $Y."
- "Locking top-2 into multi-year terms (+10 pts renewal) improves P10 EBITDA by ~$Z."
- "A 25% backfill engine reduces downside tail risk by ~$Z at P10."

## Engineering Requirements

### Code Structure
Create:
- `analysis/contract_churn_sim.py` (CLI)
- `analysis/contract_churn_sim_config.json` (defaults + scenarios)
- `analysis/README.md` (usage + interpretation)

CLI examples:
- `python analysis/contract_churn_sim.py --runs 20000 --scenario base`
- `python analysis/contract_churn_sim.py --scenario optimistic`
- `python analysis/contract_churn_sim.py --scenario downside`

### Minimum Scenarios
- `base`: conservative fill, moderate renewal
- `downside`: lower renewal, `0%` fill
- `upside`: higher renewal, `25-50%` fill
- `de-risked`: higher renewal + lower downsell variance (proxy for longer terms)

### Testing
Minimal tests should validate:
- Allocation sums to 1 and matches top-2 share
- Deterministic seed yields stable summary metrics
- Edge-case handling (`0` runs, invalid/negative params)

Use `pytest` if already present; otherwise keep tests minimal/self-contained.

### Documentation
`analysis/README.md` must:
- Explain assumptions and case mapping (short terms + concentration)
- Emphasize range/tail-risk interpretation
- Include sample output blocks for each scenario

### Git Discipline
- Work on branch: `feat/contract-churn-sim`
- Commit logically (at least 1-2 commits)
- Use concise, specific commit messages
- Do not modify unrelated files

## Acceptance Criteria
- CLI prints summary metrics, sensitivity table, and VP-ready bullets
- Scenarios configurable via JSON
- Seeded runs are reproducible
- Code is readable, commented where needed, and defensible for interview discussion
