// Tariff schema — the TypeScript mirror of `ratebook.schema`. Parses the same JSON the Python
// engine consumes and applies the same construction-time validation (tier partition, schedule
// shape, in-range period references, uniform bounded-tier units), so a tariff that is malformed
// in Python is malformed here too.
//
// Only the engine-relevant fields are modeled (energy structure, schedule, charges, unsupported
// features, metering); identity/provenance/effective-range are carried in the JSON but not
// needed to price a bill, so they are ignored on parse.

import { Decimal, optDecimal, toDecimal } from "./money.js";

export type TierMaxUnit =
  | "kWh"
  | "kWh daily"
  | "kWh/kW"
  | "kWh/kVA"
  | "kWh/hp"
  | "kWh/kW daily";

export const COMPUTABLE_TIER_MAX_UNITS: ReadonlySet<TierMaxUnit> = new Set(["kWh", "kWh daily"]);

export type FixedChargeUnit = "$/month" | "$/day";
export type MinChargeUnit = "$/month" | "$/day" | "$/year";
export type DayType = "weekday" | "weekend";

export type UnsupportedKind =
  | "demand_charge"
  | "tou_demand"
  | "flat_demand"
  | "coincident_demand"
  | "sell_rate"
  | "net_metering"
  | "rider"
  | "demand_normalized_tier_max"
  | "unmodelable";

// Unsupported kinds that change the consumption bill → force a refusal. Sell-rate / net-metering
// only affect export (v0 usage never exports), so those are warnings, not refusals.
export const REFUSING_UNSUPPORTED_KINDS: ReadonlySet<UnsupportedKind> = new Set([
  "demand_charge",
  "tou_demand",
  "flat_demand",
  "coincident_demand",
  "rider",
  "demand_normalized_tier_max",
  "unmodelable",
]);

export class EnergyTier {
  constructor(
    readonly rate: Decimal,
    readonly adj: Decimal,
    readonly max: Decimal | null,
    readonly maxUnit: TierMaxUnit,
    readonly sell: Decimal | null,
  ) {}

  get effectiveRate(): Decimal {
    return this.rate.plus(this.adj);
  }

  static fromJson(d: Record<string, unknown>): EnergyTier {
    return new EnergyTier(
      toDecimal(d.rate as string),
      d.adj === undefined || d.adj === null ? new Decimal(0) : toDecimal(d.adj as string),
      optDecimal(d.max as string | null),
      ((d.max_unit as TierMaxUnit) ?? "kWh"),
      optDecimal(d.sell as string | null),
    );
  }
}

export class EnergyPeriod {
  constructor(readonly tiers: EnergyTier[]) {
    if (tiers.length === 0) throw new Error("EnergyPeriod must have at least one tier");
    let prev: Decimal | null = null;
    const nonFinalUnits = new Set<TierMaxUnit>();
    tiers.forEach((tier, i) => {
      const isFinal = i === tiers.length - 1;
      if (tier.max === null) {
        if (!isFinal) throw new Error(`non-final tier ${i} has open max`);
        return;
      }
      if (tier.max.lte(0)) throw new Error(`tier ${i} has non-positive max ${tier.max}`);
      if (prev !== null && tier.max.lte(prev)) {
        throw new Error(`tier maxes must strictly increase: tier ${i} max ${tier.max} <= ${prev}`);
      }
      prev = tier.max;
      if (!isFinal) nonFinalUnits.add(tier.maxUnit);
    });
    if (nonFinalUnits.size > 1) {
      throw new Error(`bounded tiers mix max units: ${[...nonFinalUnits].sort().join(",")}`);
    }
  }

  static fromJson(d: Record<string, unknown>): EnergyPeriod {
    return new EnergyPeriod((d.tiers as Record<string, unknown>[]).map(EnergyTier.fromJson));
  }
}

export class EnergyRateStructure {
  constructor(readonly periods: EnergyPeriod[]) {
    if (periods.length === 0) throw new Error("EnergyRateStructure must have at least one period");
  }

  static fromJson(d: Record<string, unknown>): EnergyRateStructure {
    return new EnergyRateStructure(
      (d.periods as Record<string, unknown>[]).map(EnergyPeriod.fromJson),
    );
  }
}

function validateMatrix(name: string, matrix: number[][]): void {
  if (matrix.length !== 12) throw new Error(`${name} must have 12 month rows, got ${matrix.length}`);
  for (const [m, row] of matrix.entries()) {
    if (row.length !== 24) throw new Error(`${name} month ${m} must have 24 hours, got ${row.length}`);
  }
}

export class Schedule {
  constructor(
    readonly weekday: number[][],
    readonly weekend: number[][],
    readonly holidayPolicy: string = "unknown",
  ) {
    validateMatrix("weekday", weekday);
    validateMatrix("weekend", weekend);
  }

  periodAt(dayType: DayType, month: number, hour: number): number {
    const matrix = dayType === "weekday" ? this.weekday : this.weekend;
    return matrix[month - 1][hour];
  }

  referencedPeriods(): Set<number> {
    const out = new Set<number>();
    for (const matrix of [this.weekday, this.weekend]) {
      for (const row of matrix) for (const cell of row) out.add(cell);
    }
    return out;
  }

  static fromJson(d: Record<string, unknown>): Schedule {
    return new Schedule(
      d.weekday as number[][],
      d.weekend as number[][],
      (d.holiday_policy as string) ?? "unknown",
    );
  }
}

export class FixedCharge {
  constructor(readonly amount: Decimal, readonly unit: FixedChargeUnit) {}
  static fromJson(d: Record<string, unknown>): FixedCharge {
    return new FixedCharge(toDecimal(d.amount as string), d.unit as FixedChargeUnit);
  }
}

export class MinCharge {
  constructor(readonly amount: Decimal, readonly unit: MinChargeUnit) {}
  static fromJson(d: Record<string, unknown>): MinCharge {
    return new MinCharge(toDecimal(d.amount as string), d.unit as MinChargeUnit);
  }
}

export class UnsupportedFeature {
  constructor(readonly kind: UnsupportedKind, readonly detail: string = "") {}
  static fromJson(d: Record<string, unknown>): UnsupportedFeature {
    return new UnsupportedFeature(d.kind as UnsupportedKind, (d.detail as string) ?? "");
  }
}

export class Tariff {
  constructor(
    readonly energy: EnergyRateStructure,
    readonly schedule: Schedule,
    readonly fixedCharges: FixedCharge[] = [],
    readonly minCharge: MinCharge | null = null,
    readonly unsupported: UnsupportedFeature[] = [],
    readonly metering: string = "unknown",
  ) {
    const n = energy.periods.length;
    for (const ref of schedule.referencedPeriods()) {
      if (ref < 0 || ref >= n) {
        throw new Error(`schedule references period ${ref}, out of range [0, ${n})`);
      }
    }
  }

  static fromJson(d: Record<string, unknown>): Tariff {
    const mc = d.min_charge as Record<string, unknown> | null;
    return new Tariff(
      EnergyRateStructure.fromJson(d.energy as Record<string, unknown>),
      Schedule.fromJson(d.schedule as Record<string, unknown>),
      ((d.fixed_charges as Record<string, unknown>[]) ?? []).map(FixedCharge.fromJson),
      mc ? MinCharge.fromJson(mc) : null,
      ((d.unsupported as Record<string, unknown>[]) ?? []).map(UnsupportedFeature.fromJson),
      (d.metering as string) ?? "unknown",
    );
  }
}
