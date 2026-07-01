// The rate engine — TypeScript mirror of `ratebook.engine`. Same single BillingWindow
// abstraction (tiers reset once per window), same typed Refusal instead of a wrong number, same
// line-item ordering and warnings, so `estimate_bill` reproduces the Python engine's shared JSON
// vectors byte-for-byte.

import { Decimal, ZERO, decimalToJson, type DecimalLike, toDecimal } from "./money.js";
import {
  COMPUTABLE_TIER_MAX_UNITS,
  type DayType,
  REFUSING_UNSUPPORTED_KINDS,
  type Tariff,
  type UnsupportedKind,
} from "./schema.js";

export type RefusalReason =
  | "demand_charge"
  | "rider"
  | "unmodelable"
  | "demand_normalized_tier_max"
  | "aggregate_usage_multi_period"
  | "annual_min_single_window";

const UNSUPPORTED_REASON: Record<string, RefusalReason> = {
  demand_charge: "demand_charge",
  tou_demand: "demand_charge",
  flat_demand: "demand_charge",
  coincident_demand: "demand_charge",
  rider: "rider",
  demand_normalized_tier_max: "demand_normalized_tier_max",
  unmodelable: "unmodelable",
};

export class Refusal {
  constructor(readonly reason: RefusalReason, readonly detail: string = "") {}
  toJson() {
    return { reason: this.reason, detail: this.detail };
  }
}

// --- date helpers (UTC throughout, to match Python date semantics) ---
function parseUtcDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}
function addDaysUtc(d: Date, n: number): Date {
  return new Date(d.getTime() + n * 86_400_000);
}
function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}
// ---------------------------------------------------------------------------------------
// Holidays (mirrors the Python engine's named-holiday rules; dates computed in UTC)
// ---------------------------------------------------------------------------------------
function nthWeekdayUtc(year: number, month: number, jsDay: number, n: number): Date {
  // jsDay uses JS convention (0 = Sun … 6 = Sat); month is 1-12.
  const first = new Date(Date.UTC(year, month - 1, 1));
  const offset = (jsDay - first.getUTCDay() + 7) % 7;
  return new Date(Date.UTC(year, month - 1, 1 + offset + 7 * (n - 1)));
}
function lastWeekdayUtc(year: number, month: number, jsDay: number): Date {
  const last = new Date(Date.UTC(year, month, 0)); // day 0 of next month = last of this one
  const offset = (last.getUTCDay() - jsDay + 7) % 7;
  return new Date(last.getTime() - offset * 86_400_000);
}

const HOLIDAY_RULE: Record<string, (y: number) => Date> = {
  new_years_day: (y) => new Date(Date.UTC(y, 0, 1)),
  mlk_day: (y) => nthWeekdayUtc(y, 1, 1, 3),
  washingtons_birthday: (y) => nthWeekdayUtc(y, 2, 1, 3),
  memorial_day: (y) => lastWeekdayUtc(y, 5, 1),
  juneteenth: (y) => new Date(Date.UTC(y, 5, 19)),
  independence_day: (y) => new Date(Date.UTC(y, 6, 4)),
  labor_day: (y) => nthWeekdayUtc(y, 9, 1, 1),
  columbus_day: (y) => nthWeekdayUtc(y, 10, 1, 2),
  veterans_day: (y) => new Date(Date.UTC(y, 10, 11)),
  thanksgiving: (y) => nthWeekdayUtc(y, 11, 4, 4),
  day_after_thanksgiving: (y) => addDaysUtc(nthWeekdayUtc(y, 11, 4, 4), 1),
  christmas: (y) => new Date(Date.UTC(y, 11, 25)),
};

const holidayCache = new Map<string, Set<string>>();

/** ISO dates the named holidays land on in `year` (with sunday→monday observance). */
export function holidayDates(
  year: number,
  holidays: readonly string[],
  observance = "sunday_to_monday",
): Set<string> {
  const key = `${year}|${observance}|${holidays.join(",")}`;
  const cached = holidayCache.get(key);
  if (cached) return cached;
  const out = new Set<string>();
  for (const h of holidays) {
    const rule = HOLIDAY_RULE[h];
    if (!rule) throw new Error(`unknown holiday: ${h}`);
    const d = rule(year);
    out.add(isoDate(d));
    if (observance === "sunday_to_monday" && d.getUTCDay() === 0) out.add(isoDate(addDaysUtc(d, 1)));
  }
  holidayCache.set(key, out);
  return out;
}

function dayTypeOf(d: Date, schedule?: Tariff["schedule"]): DayType {
  if (
    schedule &&
    schedule.holidayPolicy === "as_weekend" &&
    schedule.holidays.length > 0 &&
    holidayDates(d.getUTCFullYear(), schedule.holidays, schedule.holidayObservance).has(isoDate(d))
  ) {
    return "weekend";
  }
  // "as_weekday" and "unknown" price every day by its real weekday/weekend.
  const wd = d.getUTCDay(); // 0 = Sun … 6 = Sat
  return wd === 0 || wd === 6 ? "weekend" : "weekday";
}

export class BillingWindow {
  constructor(readonly start: Date, readonly days: number) {
    if (days <= 0) throw new Error(`window days must be positive, got ${days}`);
  }
  static fromIso(startIso: string, days: number): BillingWindow {
    return new BillingWindow(parseUtcDate(startIso), days);
  }
  get hours(): number {
    return this.days * 24;
  }
  *iterDays(): Generator<Date> {
    for (let i = 0; i < this.days; i++) yield addDaysUtc(this.start, i);
  }
  toJson() {
    return { start: isoDate(this.start), days: this.days };
  }
}

export class Usage {
  constructor(readonly hourlyKwh: Decimal[] | null, readonly totalKwh: Decimal | null) {
    if ((hourlyKwh === null) === (totalKwh === null)) {
      throw new Error("Usage requires exactly one of hourlyKwh or totalKwh");
    }
  }
  static hourly(values: DecimalLike[]): Usage {
    return new Usage(values.map(toDecimal), null);
  }
  static aggregate(total: DecimalLike): Usage {
    return new Usage(null, toDecimal(total));
  }
}

export class LineItem {
  constructor(
    readonly period: number,
    readonly tier: number,
    readonly kwh: Decimal,
    readonly rate: Decimal,
    readonly subtotal: Decimal,
    readonly note: string = "",
  ) {}
  toJson() {
    return {
      period: this.period,
      tier: this.tier,
      kwh: decimalToJson(this.kwh),
      rate: decimalToJson(this.rate),
      subtotal: decimalToJson(this.subtotal),
      note: this.note,
    };
  }
}

export class BillResult {
  constructor(
    readonly ok: boolean,
    readonly total: Decimal | null,
    readonly energyCharge: Decimal = ZERO,
    readonly fixedCharge: Decimal = ZERO,
    readonly minChargeFloorApplied: boolean = false,
    readonly lineItems: LineItem[] = [],
    readonly window: BillingWindow | null = null,
    readonly warnings: string[] = [],
    readonly refusal: Refusal | null = null,
  ) {}
  toJson() {
    return {
      ok: this.ok,
      total: decimalToJson(this.total),
      energy_charge: decimalToJson(this.energyCharge),
      fixed_charge: decimalToJson(this.fixedCharge),
      min_charge_floor_applied: this.minChargeFloorApplied,
      line_items: this.lineItems.map((li) => li.toJson()),
      window: this.window ? this.window.toJson() : null,
      warnings: this.warnings,
      refusal: this.refusal ? this.refusal.toJson() : null,
    };
  }
}

export class SupportReport {
  constructor(readonly fullySupported: boolean, readonly reasons: string[] = []) {}
}

// --- internals ---
/** Public: the energy period index a tariff assigns to (day, hour). Mirror of `period_at`. */
export function periodAt(tariff: Tariff, day: Date, hour: number): number {
  return tariff.schedule.periodAt(dayTypeOf(day, tariff.schedule), day.getUTCMonth() + 1, hour);
}

function periodActiveDays(tariff: Tariff, window: BillingWindow): Map<number, number> {
  const seen = new Map<number, Set<string>>();
  for (const day of window.iterDays()) {
    const key = isoDate(day);
    for (let hour = 0; hour < 24; hour++) {
      const p = periodAt(tariff, day, hour);
      if (!seen.has(p)) seen.set(p, new Set());
      seen.get(p)!.add(key);
    }
  }
  const out = new Map<number, number>();
  for (const [p, s] of seen) out.set(p, s.size);
  return out;
}

// --- charge-window optimization (mirror of ratebook.engine.cheapest_charge_window) ---
function isoDateTime(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}T${p(d.getUTCHours())}:00:00`;
}

/** Per-hour marginal energy price ($/kWh) over the window — the TOU "when to charge" signal. */
export function hourlyMarginalPrices(tariff: Tariff, window: BillingWindow, tier = 0): Decimal[] {
  const prices: Decimal[] = [];
  for (const day of window.iterDays()) {
    for (let hour = 0; hour < 24; hour++) {
      const tiers = tariff.energy.periods[periodAt(tariff, day, hour)].tiers;
      prices.push(tiers[Math.max(0, Math.min(tier, tiers.length - 1))].effectiveRate);
    }
  }
  return prices;
}

export class ChargeWindow {
  constructor(
    readonly start: Date,
    readonly hours: number,
    readonly avgRate: Decimal,
    readonly hourlyRates: Decimal[],
  ) {}
  toJson() {
    return {
      start: isoDateTime(this.start),
      hours: this.hours,
      avg_rate: decimalToJson(this.avgRate),
      hourly_rates: this.hourlyRates.map((r) => decimalToJson(r)),
    };
  }
}

/**
 * Cheapest contiguous `chargeHours`-long block in the window to add load. Ties resolve to the
 * earliest start. With `notBefore`, only blocks starting at/after it (rounded up to the next whole
 * hour, clamped to the last fitting block) are considered — so a "charge next" caller never gets a
 * window in the past. Mirror of the Python engine; held to it by shared JSON vectors.
 */
export function cheapestChargeWindow(
  tariff: Tariff,
  window: BillingWindow,
  chargeHours: number,
  opts: { tier?: number; notBefore?: Date | null } = {},
): ChargeWindow {
  const tier = opts.tier ?? 0;
  const prices = hourlyMarginalPrices(tariff, window, tier);
  if (chargeHours <= 0 || chargeHours > prices.length) {
    throw new Error(`charge_hours ${chargeHours} out of range for a ${prices.length}-hour window`);
  }
  const lastStart = prices.length - chargeHours;
  let firstStart = 0;
  if (opts.notBefore != null) {
    const offsetHours = (opts.notBefore.getTime() - window.start.getTime()) / 3_600_000;
    firstStart = Math.min(Math.max(0, Math.ceil(offsetHours)), lastStart);
  }
  let bestStart = firstStart;
  let bestSum: Decimal | null = null;
  for (let i = firstStart; i <= lastStart; i++) {
    let sum = ZERO;
    for (let j = i; j < i + chargeHours; j++) sum = sum.plus(prices[j]);
    if (bestSum === null || sum.lt(bestSum)) {
      bestSum = sum;
      bestStart = i;
    }
  }
  const start = new Date(window.start.getTime() + bestStart * 3_600_000);
  return new ChargeWindow(
    start,
    chargeHours,
    bestSum!.div(chargeHours),
    prices.slice(bestStart, bestStart + chargeHours),
  );
}

function ladderKey(period: { tiers: { effectiveRate: Decimal; max: Decimal | null; maxUnit: string }[] }): string {
  return JSON.stringify(
    period.tiers.map((t) => [t.effectiveRate.toString(), t.max ? t.max.toString() : null, t.maxUnit]),
  );
}

function hasDailyTier(period: { tiers: { maxUnit: string }[] }): boolean {
  return period.tiers.some((t) => t.maxUnit === "kWh daily");
}

function refuseForUnsupported(tariff: Tariff, usedPeriods: number[]): Refusal | null {
  for (const feat of tariff.unsupported) {
    if (REFUSING_UNSUPPORTED_KINDS.has(feat.kind as UnsupportedKind)) {
      return new Refusal(UNSUPPORTED_REASON[feat.kind] ?? "unmodelable", feat.detail || feat.kind);
    }
  }
  for (const p of usedPeriods) {
    const tiers = tariff.energy.periods[p].tiers;
    for (let t = 0; t < tiers.length; t++) {
      if (!COMPUTABLE_TIER_MAX_UNITS.has(tiers[t].maxUnit)) {
        return new Refusal("demand_normalized_tier_max", `period ${p} tier ${t} uses ${tiers[t].maxUnit}`);
      }
    }
  }
  return null;
}

function warningsFor(tariff: Tariff): string[] {
  const out: string[] = [];
  for (const feat of tariff.unsupported) {
    if (feat.kind === "net_metering" || feat.kind === "sell_rate") out.push(`${feat.kind}_not_modeled`);
  }
  if (tariff.metering === "net_metering" || tariff.metering === "net_billing") {
    out.push("net_metering_not_modeled");
  }
  if (tariff.energy.periods.some((p) => p.tiers.some((t) => t.sell !== null && !t.sell.isZero()))) {
    out.push("sell_rate_not_modeled");
  }
  if (tariff.schedule.holidayPolicy === "as_weekend" && tariff.schedule.holidays.length === 0) {
    // The rate sheet defines holiday treatment but the dates aren't enumerated yet.
    out.push("holidays_not_enumerated");
  }
  return [...new Set(out)];
}

function priceTiers(
  periodKwh: Decimal,
  tariff: Tariff,
  period: number,
  activeDays: number,
): { items: LineItem[]; charge: Decimal; exceededFinal: boolean } {
  const items: LineItem[] = [];
  let charge = ZERO;
  let remaining = periodKwh;
  let priorMax = ZERO;
  let exceededFinal = false;
  const tiers = tariff.energy.periods[period].tiers;
  const boundaryOf = (tier: { max: Decimal | null; maxUnit: string }): Decimal =>
    tier.maxUnit === "kWh daily" ? tier.max!.times(activeDays) : tier.max!;

  for (let t = 0; t < tiers.length; t++) {
    if (remaining.lte(0)) break;
    const tier = tiers[t];
    const isFinal = t === tiers.length - 1;
    let slice: Decimal;
    if (tier.max === null) {
      slice = remaining;
    } else if (isFinal) {
      if (priorMax.plus(remaining).gt(boundaryOf(tier))) exceededFinal = true;
      slice = remaining;
    } else {
      let cap = boundaryOf(tier).minus(priorMax);
      if (cap.lt(0)) cap = ZERO;
      slice = remaining.lt(cap) ? remaining : cap;
      priorMax = boundaryOf(tier);
    }
    const eff = tier.effectiveRate;
    const subtotal = slice.times(eff);
    items.push(new LineItem(period, t, slice, eff, subtotal));
    charge = charge.plus(subtotal);
    remaining = remaining.minus(slice);
  }
  return { items, charge, exceededFinal };
}

function priceWindow(tariff: Tariff, usage: Usage, window: BillingWindow, isAnnual: boolean): BillResult {
  if (usage.hourlyKwh !== null && usage.hourlyKwh.length !== window.hours) {
    throw new Error(`hourly_kwh has ${usage.hourlyKwh.length} values, window needs ${window.hours}`);
  }

  const activeDays = periodActiveDays(tariff, window);
  const usedPeriods = [...activeDays.keys()].sort((a, b) => a - b);

  const refusal = refuseForUnsupported(tariff, usedPeriods);
  if (refusal) return new BillResult(false, null, ZERO, ZERO, false, [], window, [], refusal);

  if (!isAnnual && tariff.minCharge && tariff.minCharge.unit === "$/year") {
    return new BillResult(
      false, null, ZERO, ZERO, false, [], window, [],
      new Refusal("annual_min_single_window", "$/year minimum cannot be allocated to one window; use estimate_annual"),
    );
  }

  // Step 1: accumulate kWh per period.
  const periodKwh = new Map<number, Decimal>();
  for (let p = 0; p < tariff.energy.periods.length; p++) periodKwh.set(p, ZERO);

  if (usage.hourlyKwh !== null) {
    let i = 0;
    for (const day of window.iterDays()) {
      for (let hour = 0; hour < 24; hour++) {
        const p = periodAt(tariff, day, hour);
        periodKwh.set(p, periodKwh.get(p)!.plus(usage.hourlyKwh[i]));
        i++;
      }
    }
  } else {
    const distinct = new Set(usedPeriods.map((p) => ladderKey(tariff.energy.periods[p])));
    const touchesDaily = usedPeriods.some((p) => hasDailyTier(tariff.energy.periods[p]));
    if (usedPeriods.length === 1 || (distinct.size === 1 && !touchesDaily)) {
      periodKwh.set(usedPeriods[0], usage.totalKwh!);
    } else {
      return new BillResult(
        false, null, ZERO, ZERO, false, [], window, [],
        new Refusal("aggregate_usage_multi_period", `window touches ${distinct.size} distinct price periods; supply hourly load`),
      );
    }
  }

  // Step 2: tiers per period.
  const lineItems: LineItem[] = [];
  let energy = ZERO;
  const extraWarnings: string[] = [];
  for (const p of [...periodKwh.keys()].sort((a, b) => a - b)) {
    if (periodKwh.get(p)!.lte(0)) continue;
    const { items, charge, exceededFinal } = priceTiers(periodKwh.get(p)!, tariff, p, activeDays.get(p) ?? window.days);
    lineItems.push(...items);
    energy = energy.plus(charge);
    if (exceededFinal) extraWarnings.push("usage_exceeds_final_tier_max");
  }

  // Step 3: fixed charges.
  let fixed = ZERO;
  for (const fc of tariff.fixedCharges) {
    const amount = fc.unit === "$/month" ? fc.amount : fc.amount.times(window.days);
    fixed = fixed.plus(amount);
    lineItems.push(new LineItem(-1, -1, ZERO, ZERO, amount, `fixed ${fc.unit}`));
  }

  const subtotal = energy.plus(fixed);

  // Step 4: minimum charge floor ($/year handled only in estimate_annual).
  let floorApplied = false;
  let total = subtotal;
  const mc = tariff.minCharge;
  if (mc && mc.unit !== "$/year") {
    const floor = mc.unit === "$/month" ? mc.amount : mc.amount.times(window.days);
    if (floor.gt(subtotal)) {
      total = floor;
      floorApplied = true;
      lineItems.push(new LineItem(-1, -1, ZERO, ZERO, floor.minus(subtotal), "min charge floor"));
    }
  }

  const warnings = [...new Set([...warningsFor(tariff), ...extraWarnings])];
  return new BillResult(true, total, energy, fixed, floorApplied, lineItems, window, warnings, null);
}

export function estimateBill(tariff: Tariff, usage: Usage, window: BillingWindow): BillResult {
  return priceWindow(tariff, usage, window, false);
}

export function supported(tariff: Tariff, singleWindow = true): SupportReport {
  const reasons: string[] = [];
  for (const feat of tariff.unsupported) {
    if (REFUSING_UNSUPPORTED_KINDS.has(feat.kind as UnsupportedKind)) {
      reasons.push(`${feat.kind}: ${feat.detail}`.replace(/: $/, ""));
    }
  }
  tariff.energy.periods.forEach((period, p) => {
    period.tiers.forEach((tier, t) => {
      if (!COMPUTABLE_TIER_MAX_UNITS.has(tier.maxUnit)) {
        reasons.push(`demand_normalized_tier_max at period ${p} tier ${t}`);
      }
    });
  });
  if (singleWindow && tariff.minCharge && tariff.minCharge.unit === "$/year") {
    reasons.push("annual_min_single_window (use estimate_annual)");
  }
  return new SupportReport(reasons.length === 0, reasons);
}
