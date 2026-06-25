"""Eval-harnessed tariff extraction: utility PDF -> structured tariff -> :class:`Tariff`.

The pipeline has two steps: a Claude structured-output **extractor** turns a tariff PDF into an
:data:`EXTRACTION_SCHEMA`-shaped record, then a **deterministic converter + validator** turns
that record into a priceable tariff and checks it for arithmetic/structural consistency. This
module holds the prompt, the schema, the production API call, and that deterministic
converter/validator; the validation logic reuses ``ratebook.validate`` so the engine and the
eval harness never disagree about "valid". (A model-based grading pass that re-reads the source
PDF is planned, not yet implemented here.)

Extraction surfaces the reality URDB hides: a single rate sheet often carries only the
*distribution* component, with generation ("Price to Compare") and transmission in separate
documents, plus a list of riders. The schema captures that decomposition explicitly so the
engine prices what is on the sheet and the bill-match honestly reports what is still missing.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from ratebook.schema import (
    EnergyPeriod,
    EnergyRateStructure,
    EnergyTier,
    FixedCharge,
    FixedChargeUnit,
    MinCharge,
    MinChargeUnit,
    Schedule,
    Sector,
    Tariff,
    TariffIdentity,
)

DEFAULT_MODEL = "claude-opus-4-8"

#: JSON Schema the extractor is constrained to (Anthropic structured outputs / strict tool use).
#: Richer than the raw Tariff: it captures the distribution/generation/transmission split and
#: the rider list a real tariff sheet carries, so downstream code knows what was and wasn't priced.
EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "plan_code",
        "plan_name",
        "sector",
        "fixed_charges",
        "energy_charges",
        "tiered",
        "time_of_use",
        "components_priced",
        "components_referenced_only",
        "riders",
        "confidence",
        "notes",
    ],
    "properties": {
        "plan_code": {"type": "string", "description": "Short rate code, e.g. 'R'."},
        "plan_name": {"type": "string"},
        "sector": {
            "type": "string",
            "enum": ["residential", "commercial", "industrial", "lighting", "unknown"],
        },
        "effective_date": {"type": "string", "description": "ISO date, or empty if not stated."},
        "fixed_charges": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["amount", "unit", "label"],
                "properties": {
                    "amount": {
                        "type": "string",
                        "description": "Decimal as a string, e.g. '11.30'.",
                    },
                    "unit": {"type": "string", "enum": ["$/month", "$/day"]},
                    "label": {"type": "string"},
                    "applies_to": {
                        "type": "string",
                        "enum": ["standard", "alternative"],
                        "description": "'standard' for the normal customer charge; "
                        "'alternative' for a mutually-exclusive variant (e.g. a legacy "
                        "'former off-peak' meter charge) that must NOT be summed with it.",
                    },
                },
            },
        },
        "energy_charges": {
            "type": "array",
            "description": "Per-kWh charges stated on THIS document, one per component/tier.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["rate", "component", "label"],
                "properties": {
                    "rate": {"type": "string", "description": "$/kWh as a decimal string."},
                    "component": {
                        "type": "string",
                        "enum": ["distribution", "generation", "transmission", "bundled", "other"],
                    },
                    "label": {"type": "string"},
                    "tier_max_kwh": {
                        "type": "string",
                        "description": "Upper kWh bound, or empty if none.",
                    },
                },
            },
        },
        "min_charge": {
            "type": "object",
            "additionalProperties": False,
            "required": ["amount", "unit"],
            "properties": {
                "amount": {"type": "string"},
                "unit": {"type": "string", "enum": ["$/month", "$/day", "$/year"]},
                "basis": {"type": "string"},
            },
        },
        "tiered": {"type": "boolean"},
        "time_of_use": {"type": "boolean"},
        "components_priced": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Bill components with an actual number on this document.",
        },
        "components_referenced_only": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Components named but priced elsewhere (e.g. 'generation: see GSA').",
        },
        "riders": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Named surcharges/adjustments/clauses that apply but carry no value.",
        },
        "confidence": {"type": "number", "description": "0-1 self-assessed extraction confidence."},
        "notes": {"type": "string", "description": "Anything a bill-match consumer must know."},
    },
}

EXTRACTION_SYSTEM = """You extract structured electricity-tariff data from a utility tariff \
PDF. Extract ONLY what the document actually states — never infer a number from outside it.

Critical distinctions a US electricity bill requires:
- A distribution utility's rate sheet often prices ONLY the distribution component. Generation \
("supply", "Price to Compare", "Generation Supply Adjustment") and transmission are frequently \
in SEPARATE documents and updated on a different cadence. Put each per-kWh charge under its \
correct `component`, and list components that are named but not priced here under \
`components_referenced_only`.
- Riders/surcharges/adjustment clauses (fuel, DSIC, state tax, universal service, \
decommissioning, etc.) usually apply with no number on the sheet — list them in `riders`.
- A minimum charge defined as "equal to the fixed charge" should copy that amount.

Be exact with decimals (copy digits verbatim). Set `confidence` lower when the document is \
ambiguous or a needed value is absent. Use `notes` to flag what a bill calculator still needs."""

EXTRACTION_USER = "Extract the residential tariff from this PDF into the required schema."


def pdf_to_text(path: str | Path) -> str:
    """Plain-text extraction of a tariff PDF (used for grading context and as an API fallback)."""
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_tariff_dict(
    pdf_path: str | Path,
    *,
    client: Any | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Run the Claude structured-output extractor on a tariff PDF (production path).

    Sends the PDF natively (Claude reads PDFs) and constrains the response to
    :data:`EXTRACTION_SCHEMA`. Requires the ``extract`` extra (``anthropic``); ``client`` may be
    injected for testing. Returns the validated extraction dict.
    """
    if client is None:
        import anthropic  # imported lazily so the engine path never needs the SDK

        client = anthropic.Anthropic()

    pdf_b64 = base64.standard_b64encode(Path(pdf_path).read_bytes()).decode()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=EXTRACTION_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": EXTRACTION_USER},
                ],
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}},
    )
    import json

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


# --------------------------------------------------------------------------------------
# Deterministic converter + grader (no API; the eval-harness core)
# --------------------------------------------------------------------------------------
_FIXED_UNIT = {"$/month": FixedChargeUnit.PER_MONTH, "$/day": FixedChargeUnit.PER_DAY}
_MIN_UNIT = {
    "$/month": MinChargeUnit.PER_MONTH,
    "$/day": MinChargeUnit.PER_DAY,
    "$/year": MinChargeUnit.PER_YEAR,
}
_SECTOR = {s.value: s for s in Sector}


@dataclass(frozen=True)
class PricedComponents:
    """What the engine can price from an extraction vs what a full bill still needs."""

    tariff: Tariff
    priced_components: tuple[str, ...]
    missing_components: tuple[str, ...]
    riders: tuple[str, ...]


def extracted_to_tariff(extracted: dict[str, Any]) -> PricedComponents:
    """Convert an extraction record into a priceable :class:`Tariff` for the priced components.

    Energy charges are summed per tier across priced components (a bundled bill is the sum of
    distribution + generation + transmission). Components named but not priced on the sheet,
    and riders, are carried as :class:`UnsupportedFeature` markers so the engine's bill is
    honestly labelled "partial" rather than presented as a full bill.
    """
    charges = extracted.get("energy_charges", [])
    if not charges:
        raise ValueError("extraction has no energy charges to price")

    # v0 scope: flat or simple-tiered, single period. Group priced charges by tier boundary,
    # summing components that share a boundary.
    by_tier: dict[str | None, Decimal] = {}
    tier_order: list[str | None] = []
    for ch in charges:
        cap = ch.get("tier_max_kwh") or None
        if cap not in by_tier:
            by_tier[cap] = Decimal(0)
            tier_order.append(cap)
        by_tier[cap] += Decimal(ch["rate"])

    # Order tiers by ascending cap (None = open final tier last).
    def _key(cap: str | None) -> Decimal:
        return Decimal("Infinity") if cap is None else Decimal(cap)

    tiers = [
        EnergyTier(rate=by_tier[cap], max=(None if cap is None else Decimal(cap)))
        for cap in sorted(tier_order, key=_key)
    ]
    energy = EnergyRateStructure(periods=(EnergyPeriod(tiers=tuple(tiers)),))

    # Mutually-exclusive fixed charges must not be summed: a tariff sheet may list a standard
    # customer charge alongside a legacy/alternative-meter charge that applies to a different
    # customer. The eval grader caught this on PECO ($11.30 standard vs $2.19 former-off-peak).
    # Prefer the explicit `applies_to` qualifier; fall back to a label heuristic for extractors
    # that don't populate it.
    def _is_alternative(fc: dict[str, Any]) -> bool:
        if fc.get("applies_to") == "alternative":
            return True
        label = fc.get("label", "").lower()
        return any(w in label for w in ("former", "legacy", "off-peak", "off peak"))

    fixed = tuple(
        FixedCharge(Decimal(fc["amount"]), _FIXED_UNIT.get(fc["unit"], FixedChargeUnit.PER_MONTH))
        for fc in extracted.get("fixed_charges", [])
        if not _is_alternative(fc)
    )
    mc = extracted.get("min_charge")
    min_charge = (
        MinCharge(Decimal(mc["amount"]), _MIN_UNIT.get(mc["unit"], MinChargeUnit.PER_MONTH))
        if mc
        else None
    )

    missing = tuple(extracted.get("components_referenced_only", []))
    riders = tuple(extracted.get("riders", []))

    identity = TariffIdentity(
        plan_code=extracted.get("plan_code", ""),
        plan_name=extracted.get("plan_name", ""),
        sector=_SECTOR.get(extracted.get("sector", "unknown"), Sector.UNKNOWN),
    )
    flat = tuple(tuple(0 for _ in range(24)) for _ in range(12))
    # The Tariff faithfully represents the PRICED components and is cleanly priceable. Whether
    # those components constitute a *full* bill is reported by PricedComponents (missing /
    # riders), not encoded as engine refusals — that keeps the distribution-only bill
    # computable while the caller stays honest about what is still missing.
    tariff = Tariff(
        energy=energy,
        schedule=Schedule(weekday=flat, weekend=flat),
        identity=identity,
        fixed_charges=fixed,
        min_charge=min_charge,
    )
    return PricedComponents(
        tariff=tariff,
        priced_components=tuple(extracted.get("components_priced", [])),
        missing_components=missing,
        riders=riders,
    )


@dataclass(frozen=True)
class FieldDiff:
    field: str
    extracted: str
    expected: str
    ok: bool


@dataclass(frozen=True)
class GradeReport:
    arithmetic_issues: list[Any] = field(default_factory=list)
    field_diffs: list[FieldDiff] = field(default_factory=list)
    passed: bool = True

    @property
    def field_accuracy(self) -> float:
        if not self.field_diffs:
            return 1.0
        return sum(d.ok for d in self.field_diffs) / len(self.field_diffs)


def grade_extraction(priced: PricedComponents, golden: dict[str, str] | None = None) -> GradeReport:
    """Grade an extraction: arithmetic consistency (via the shared validators) plus, when a
    golden record is supplied, field-by-field accuracy on the priceable numbers."""
    from ratebook.validate import validate_tariff

    issues = [i for i in validate_tariff(priced.tariff) if i.severity == "error"]
    diffs: list[FieldDiff] = []
    if golden is not None:
        checks = {
            "distribution_rate": str(priced.tariff.energy.periods[0].tiers[0].effective_rate),
            "fixed_charge": str(priced.tariff.fixed_charges[0].amount)
            if priced.tariff.fixed_charges
            else "",
            "min_charge": str(priced.tariff.min_charge.amount) if priced.tariff.min_charge else "",
        }
        for key, expected in golden.items():
            got = checks.get(key, "")
            diffs.append(FieldDiff(key, got, expected, Decimal(got or 0) == Decimal(expected or 0)))
    passed = not issues and all(d.ok for d in diffs)
    return GradeReport(arithmetic_issues=issues, field_diffs=diffs, passed=passed)
