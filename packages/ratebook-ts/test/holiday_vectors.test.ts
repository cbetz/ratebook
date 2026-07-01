// Cross-engine contract for holiday-aware day-typing: the TS engine must reproduce the
// Python engine's golden vectors byte-for-byte. Both read the SAME file
// (packages/ratebook/tests/vectors/v0_holidays.json); regenerate it with
// `uv run python packages/ratebook/tests/generate_holiday_vectors.py`.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  BillingWindow,
  Usage,
  cheapestChargeWindow,
  estimateBill,
  holidayDates,
  hourlyMarginalPrices,
} from "../src/engine.js";
import { decimalToJson } from "../src/money.js";
import { Tariff } from "../src/schema.js";

const vectorsPath = fileURLToPath(
  new URL("../../ratebook/tests/vectors/v0_holidays.json", import.meta.url),
);
type Case = {
  name: string;
  tariff: Record<string, unknown>;
  window: { start: string; days: number };
  tier?: number;
  usage?: { hourly_kwh?: string[]; total_kwh?: string };
  charge_hours?: number;
  expected: unknown;
};
const data = JSON.parse(readFileSync(vectorsPath, "utf8")) as {
  price_cases: Case[];
  bill_cases: Case[];
  charge_cases: Case[];
};

describe("cross-engine holiday vectors", () => {
  for (const c of data.price_cases) {
    it(`prices: ${c.name}`, () => {
      const prices = hourlyMarginalPrices(
        Tariff.fromJson(c.tariff),
        BillingWindow.fromIso(c.window.start, c.window.days),
        c.tier ?? 0,
      );
      expect(prices.map((p) => decimalToJson(p))).toEqual(c.expected);
    });
  }

  for (const c of data.bill_cases) {
    it(`bill: ${c.name}`, () => {
      const usage = c.usage?.hourly_kwh
        ? Usage.hourly(c.usage.hourly_kwh)
        : Usage.aggregate(c.usage!.total_kwh!);
      const result = estimateBill(
        Tariff.fromJson(c.tariff),
        usage,
        BillingWindow.fromIso(c.window.start, c.window.days),
      );
      expect(result.toJson()).toEqual(c.expected);
    });
  }

  for (const c of data.charge_cases) {
    it(`charge window: ${c.name}`, () => {
      const cw = cheapestChargeWindow(
        Tariff.fromJson(c.tariff),
        BillingWindow.fromIso(c.window.start, c.window.days),
        c.charge_hours!,
      );
      expect(cw.toJson()).toEqual(c.expected);
    });
  }

  it("holidayDates matches the documented rules", () => {
    const d2026 = holidayDates(2026, ["labor_day", "thanksgiving", "independence_day"]);
    expect(d2026.has("2026-09-07")).toBe(true);
    expect(d2026.has("2026-11-26")).toBe(true);
    expect(d2026.has("2026-07-04")).toBe(true); // Saturday: no shift
    expect(d2026.has("2026-07-06")).toBe(false);
    const d2027 = holidayDates(2027, ["independence_day"]);
    expect(d2027.has("2027-07-04")).toBe(true);
    expect(d2027.has("2027-07-05")).toBe(true); // Sunday -> following Monday
  });
});
