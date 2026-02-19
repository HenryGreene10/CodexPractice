# Repository Guidelines

## Project Structure & Module Organization
This repository currently centers on the simulator brief in `project brief.md`. Implementation should live under `analysis/`:
- `analysis/contract_churn_sim.py`: Monte Carlo CLI entry point
- `analysis/contract_churn_sim_config.json`: default anchors and scenario configs
- `analysis/README.md`: assumptions, usage, and interpretation
- `analysis/tests/`: unit tests for allocation logic, reproducibility, and input validation

Keep files focused: simulation logic in functions, CLI argument parsing in `main()`, and output formatting separated from core math.

## Build, Test, and Development Commands
- `python analysis/contract_churn_sim.py --runs 20000 --scenario base`: run base simulation
- `python analysis/contract_churn_sim.py --scenario downside`: run downside case
- `python analysis/contract_churn_sim.py --scenario de-risked`: run contract-stability case
- `pytest -q`: run tests (once `analysis/tests/` is present)

If needed, create an isolated environment before running:
`python -m venv .venv && source .venv/bin/activate`.

## Coding Style & Naming Conventions
Use Python with 4-space indentation, PEP 8 naming, and explicit type hints for public functions.
- Functions/variables: `snake_case`
- Constants/default anchors: `UPPER_SNAKE_CASE`
- Keep stochastic assumptions configurable via JSON, not hard-coded in function bodies.

Prefer small, testable functions (allocation, renewal draw, EBITDA translation, metrics).

## Testing Guidelines
Use `pytest` with deterministic seeds for reproducible checks.
- Test files: `test_*.py`
- Include baseline tests for:
  - customer share sums and top-2 concentration
  - stable summary metrics under fixed seed
  - rejection of invalid inputs (`runs <= 0`, negative rates, malformed scenarios)

## Commit & Pull Request Guidelines
No existing Git history is available in this workspace, so use concise Conventional Commit style:
- `feat(sim): add base churn Monte Carlo engine`
- `test(sim): add seed reproducibility coverage`

PRs should include:
- what changed and why
- sample CLI output for at least `base` and `downside`
- any assumption changes (renewal priors, fill fraction, drop-through)
- linked issue or brief problem statement
