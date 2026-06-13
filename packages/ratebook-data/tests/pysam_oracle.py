"""Drive PySAM ``utilityrate5`` as a reference oracle for the Ratebook engine.

PySAM is the validation target named in the roadmap. We build ``utilityrate5`` inputs
directly from a :class:`ratebook.schema.Tariff` (rather than via NREL's URDB-JSON converter)
so the comparison is fully under our control and isolates engine math: the tariffs are real
URDB records, the rate-input construction is ours.

Parity facts pinned by probing PySAM:

- PySAM assumes the 8,760-hour year starts on a **Monday** (104 weekend days), so the
  engine's :func:`estimate_annual` is driven with a non-leap year that starts Monday
  (``PYSAM_YEAR``) to align weekday/weekend assignment exactly.
- ``ur_ec_tou_mat`` has no adjustment column, so the buy rate is ``rate + adj``.
- Tier-max unit codes: ``kWh`` → 0, ``kWh daily`` → 2.
- Generation is zero (no export), so sell rates never perturb the consumption comparison.
"""

from __future__ import annotations

from decimal import Decimal

from ratebook.schema import TierMaxUnit

PYSAM_YEAR = 2018  # non-leap, Jan 1 = Monday, matches PySAM's internal calendar
_OPEN_MAX = 1e38
_UNIT_CODE = {TierMaxUnit.KWH: 0, TierMaxUnit.KWH_DAILY: 2}


def tariff_to_ur5_inputs(tariff) -> dict:
    """Translate a (fully supported, $/month-fixed) Tariff into utilityrate5 inputs."""
    sched_weekday = [[c + 1 for c in row] for row in tariff.schedule.weekday]
    sched_weekend = [[c + 1 for c in row] for row in tariff.schedule.weekend]

    tou_mat: list[list[float]] = []
    for p, period in enumerate(tariff.energy.periods):
        for t, tier in enumerate(period.tiers):
            is_final = t == len(period.tiers) - 1
            max_kwh = _OPEN_MAX if (tier.max is None or is_final) else float(tier.max)
            tou_mat.append(
                [
                    p + 1,
                    t + 1,
                    max_kwh,
                    _UNIT_CODE[tier.max_unit],
                    float(tier.effective_rate),
                    0.0,
                ]
            )

    fixed_monthly = sum(
        (fc.amount for fc in tariff.fixed_charges if fc.unit.value == "$/month"),
        Decimal(0),
    )
    monthly_min = Decimal(0)
    annual_min = Decimal(0)
    if tariff.min_charge is not None:
        if tariff.min_charge.unit.value == "$/month":
            monthly_min = tariff.min_charge.amount
        elif tariff.min_charge.unit.value == "$/year":
            annual_min = tariff.min_charge.amount

    return {
        "ur_ec_sched_weekday": sched_weekday,
        "ur_ec_sched_weekend": sched_weekend,
        "ur_ec_tou_mat": tou_mat,
        "ur_monthly_fixed_charge": float(fixed_monthly),
        "ur_monthly_min_charge": float(monthly_min),
        "ur_annual_min_charge": float(annual_min),
    }


def run_pysam(tariff, load_8760: list[float]) -> dict:
    """Return PySAM's year-1 monthly energy charges, monthly fixed charges, and annual total."""
    import PySAM.Utilityrate5 as ur5

    m = ur5.new()
    m.Lifetime.analysis_period = 1
    m.Lifetime.system_use_lifetime_output = 0
    m.Lifetime.inflation_rate = 0
    m.SystemOutput.degradation = [0]
    m.SystemOutput.gen = [0.0] * len(load_8760)
    m.ElectricityRates.en_electricity_rates = 1
    m.ElectricityRates.ur_metering_option = 0
    m.ElectricityRates.ur_dc_enable = 0
    m.ElectricityRates.rate_escalation = [0]
    m.ElectricityRates.ur_en_ts_buy_rate = 0
    m.ElectricityRates.ur_en_ts_sell_rate = 0
    m.Load.load = load_8760

    for key, value in tariff_to_ur5_inputs(tariff).items():
        setattr(m.ElectricityRates, key, value)

    m.execute(0)
    return {
        "monthly_energy": list(m.Outputs.year1_monthly_ec_charge_with_system),
        "monthly_fixed": list(m.Outputs.year1_monthly_fixed_with_system),
        "annual_total": m.Outputs.utility_bill_w_sys_year1,
    }


def shaped_load_8760() -> list[float]:
    """A deterministic, non-flat 8,760-hour load that exercises TOU buckets and crosses tier
    boundaries (monthly totals in the high-hundreds of kWh). No RNG — fully reproducible.

    Hour 0 is Jan 1 00:00. An evening bump (16:00-20:00) loads the TOU peak window; a mild
    summer bump loads the seasonal periods.
    """
    load: list[float] = []
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    for month_idx, ndays in enumerate(days_in_month):
        summer = 1.4 if 5 <= month_idx <= 8 else 1.0
        for _day in range(ndays):
            for hour in range(24):
                base = 0.6 + (0.9 if 16 <= hour < 21 else 0.0)
                load.append(round(base * summer, 4))
    return load
