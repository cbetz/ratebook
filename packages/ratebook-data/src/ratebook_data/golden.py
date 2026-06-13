"""Golden-set scorecard: turn eval-run results into a per-utility accuracy report.

The golden set pairs URDB structured records (ground truth) with their source PDFs. An eval run
extracts each PDF and grades it against the URDB record. This module aggregates those graded
results into the accuracy scorecard the project publishes as content (per the build-in-public
decision) — structural-field accuracy, fixed-charge accuracy, and the rate-relationship
distribution that surfaces how often URDB carries a *bundled* rate where the sheet prices only
distribution (the core "URDB is decaying/bundled" finding).

The grade record per pair is expected to carry: ``sector_match``, ``tiered_match``,
``tou_match``, ``fixed_charge_match`` (bools), ``arithmetic_consistent`` (bool),
``rate_relationship`` (str), and ``verdict`` (str) — matching the eval's grading schema.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

STRUCTURAL_FIELDS = ("sector_match", "tiered_match", "tou_match", "fixed_charge_match")


@dataclass(frozen=True)
class Scorecard:
    n: int
    field_accuracy: dict[str, float]
    arithmetic_pass_rate: float
    verdicts: dict[str, int]
    rate_relationships: dict[str, int]

    @property
    def overall_field_accuracy(self) -> float:
        if not self.field_accuracy:
            return 0.0
        return sum(self.field_accuracy.values()) / len(self.field_accuracy)


def build_scorecard(results: list[dict]) -> Scorecard:
    """Aggregate a list of ``{grade: {...}}`` eval results into a :class:`Scorecard`."""
    grades = [r["grade"] for r in results if r.get("grade")]
    n = len(grades)
    if n == 0:
        return Scorecard(0, {}, 0.0, {}, {})

    field_acc = {
        f: sum(1 for g in grades if g.get(f)) / n for f in STRUCTURAL_FIELDS
    }
    arithmetic = sum(1 for g in grades if g.get("arithmetic_consistent")) / n
    verdicts = dict(Counter(g.get("verdict", "unknown") for g in grades))
    relationships = dict(Counter(g.get("rate_relationship", "unknown") for g in grades))
    return Scorecard(
        n=n,
        field_accuracy=field_acc,
        arithmetic_pass_rate=arithmetic,
        verdicts=verdicts,
        rate_relationships=relationships,
    )


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _check(b: bool | None) -> str:
    return "✅" if b else "❌"


def render_scorecard_md(results: list[dict], *, snapshot: str = "", n_total: int = 0) -> str:
    """Render the per-utility accuracy scorecard as markdown."""
    sc = build_scorecard(results)
    lines: list[str] = []
    lines.append("# Golden-set extraction scorecard")
    lines.append("")
    if snapshot:
        lines.append(f"Snapshot: {snapshot}. ")
    graded = len(results)
    suffix = (
        f" of {n_total} selected ({n_total - graded} unfetchable — link rot)." if n_total else "."
    )
    lines.append(f"Graded **{graded}** golden pairs{suffix}")
    lines.append("")
    lines.append("## Aggregate accuracy (extraction vs URDB ground truth)")
    lines.append("")
    lines.append("| Metric | Score |")
    lines.append("|---|---|")
    labels = {
        "sector_match": "Sector",
        "tiered_match": "Tiered (yes/no)",
        "tou_match": "Time-of-use (yes/no)",
        "fixed_charge_match": "Fixed charge amount",
    }
    for f in STRUCTURAL_FIELDS:
        lines.append(f"| {labels[f]} | {_pct(sc.field_accuracy.get(f, 0))} |")
    lines.append(f"| Arithmetic consistency | {_pct(sc.arithmetic_pass_rate)} |")
    lines.append(f"| **Overall structural** | **{_pct(sc.overall_field_accuracy)}** |")
    lines.append("")
    lines.append("Verdicts: " + ", ".join(f"{k} {v}" for k, v in sorted(sc.verdicts.items())))
    lines.append("")
    lines.append(
        "Energy-rate relationship to the URDB record: "
        + ", ".join(f"{k} {v}" for k, v in sorted(sc.rate_relationships.items()))
        + ". (`distribution_only_vs_bundled` is the headline finding: URDB carries a bundled "
        "rate while the sheet prices distribution only.)"
    )
    lines.append("")
    lines.append("## Per-utility detail")
    lines.append("")
    lines.append("| Utility | Plan | Sec | Tier | TOU | Fixed | Rate vs URDB | Verdict |")
    lines.append("|---|---|:--:|:--:|:--:|:--:|---|---|")
    for r in results:
        g = r.get("grade") or {}
        lines.append(
            f"| {r.get('utility', '')[:22]} | {r.get('plan_name', '')[:24]} "
            f"| {_check(g.get('sector_match'))} | {_check(g.get('tiered_match'))} "
            f"| {_check(g.get('tou_match'))} | {_check(g.get('fixed_charge_match'))} "
            f"| {g.get('rate_relationship', '')} | {g.get('verdict', '')} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"
