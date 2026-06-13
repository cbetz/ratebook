"""Tests for the golden-set scorecard aggregation (deterministic)."""

from __future__ import annotations

from ratebook_data.golden import build_scorecard, render_scorecard_md

SAMPLE = [
    {
        "utility": "PECO Energy Co",
        "plan_name": "Residential Service (R)",
        "grade": {
            "sector_match": True,
            "tiered_match": True,
            "tou_match": True,
            "fixed_charge_match": True,
            "arithmetic_consistent": True,
            "rate_relationship": "distribution_only_vs_bundled",
            "verdict": "pass-with-notes",
        },
    },
    {
        "utility": "Salt River Project",
        "plan_name": "E-23",
        "grade": {
            "sector_match": True,
            "tiered_match": True,
            "tou_match": True,
            "fixed_charge_match": False,
            "arithmetic_consistent": True,
            "rate_relationship": "matches",
            "verdict": "pass",
        },
    },
]


def test_scorecard_aggregates_field_accuracy() -> None:
    sc = build_scorecard(SAMPLE)
    assert sc.n == 2
    assert sc.field_accuracy["sector_match"] == 1.0
    assert sc.field_accuracy["fixed_charge_match"] == 0.5
    assert sc.arithmetic_pass_rate == 1.0
    assert sc.verdicts == {"pass-with-notes": 1, "pass": 1}
    assert sc.rate_relationships["distribution_only_vs_bundled"] == 1


def test_scorecard_handles_empty() -> None:
    sc = build_scorecard([])
    assert sc.n == 0
    assert sc.overall_field_accuracy == 0.0


def test_render_scorecard_markdown() -> None:
    md = render_scorecard_md(SAMPLE, snapshot="usurdb-2026-06-13", n_total=3)
    assert "# Golden-set extraction scorecard" in md
    assert "Graded **2** golden pairs of 3 selected" in md
    assert "PECO Energy Co" in md
    assert "distribution_only_vs_bundled" in md
