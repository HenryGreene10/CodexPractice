import copy
import unittest
from pathlib import Path

from analysis import mix_optimizer


def _load_default_config():
    config_path = Path(__file__).resolve().parents[1] / "mix_optimizer_config.json"
    return mix_optimizer.load_config(config_path)


class MixOptimizerTests(unittest.TestCase):
    def test_constraints_respected(self):
        cfg = _load_default_config()
        result = mix_optimizer.optimize_for_scenario(cfg, "base")

        self.assertLessEqual(result["total_bbl"], result["capacity_bbl"])
        self.assertLessEqual(result["canning_hours_used"], result["canning_hours_capacity"] + 1e-9)

    def test_deterministic_for_fixed_config(self):
        cfg = _load_default_config()
        r1 = mix_optimizer.optimize_for_scenario(cfg, "base")
        r2 = mix_optimizer.optimize_for_scenario(cfg, "base")

        keys = [
            "branded_bbl",
            "contract_bbl",
            "total_bbl",
            "gross_profit_usd",
            "ebitda_proxy_usd",
            "canning_hours_used",
        ]
        self.assertEqual({k: r1[k] for k in keys}, {k: r2[k] for k in keys})

    def test_huge_canning_prefers_higher_contribution_stream(self):
        cfg = _load_default_config()
        cfg_huge = copy.deepcopy(cfg)
        cfg_huge["assumptions"]["canning"]["canning_hours_capacity"] = 10_000_000
        cfg_huge["assumptions"]["demand_limits_bbl"]["max_branded_bbl"] = 60_000
        cfg_huge["assumptions"]["demand_limits_bbl"]["max_contract_bbl"] = 60_000

        result = mix_optimizer.optimize_for_scenario(cfg_huge, "base")

        self.assertEqual(result["branded_bbl"], 60_000)
        self.assertEqual(result["contract_bbl"], 0)

    def test_low_branded_cap_flags_demand_cap_binding(self):
        cfg = _load_default_config()
        cfg_capped = copy.deepcopy(cfg)
        cfg_capped["assumptions"]["canning"]["canning_hours_capacity"] = 10_000_000
        cfg_capped["assumptions"]["demand_limits_bbl"]["max_branded_bbl"] = 10_000
        cfg_capped["assumptions"]["demand_limits_bbl"]["max_contract_bbl"] = 60_000

        result = mix_optimizer.optimize_for_scenario(cfg_capped, "base")

        self.assertEqual(result["branded_bbl"], 10_000)
        self.assertTrue(result["branded_demand_cap_binds"])
        self.assertTrue(result["any_demand_cap_binds"])
        self.assertIn("Branded max cap reached", " ".join(result["demand_cap_binding_messages"]))


if __name__ == "__main__":
    unittest.main()
