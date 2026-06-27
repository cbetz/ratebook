// Cross-engine contract for the charge-window optimization: the TS engine must reproduce the
// Python engine's golden vectors byte-for-byte. Both read the SAME file
// (packages/ratebook/tests/vectors/v0_charge_windows.json); regenerate it with
// `uv run python packages/ratebook/tests/generate_charge_vectors.py`.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { BillingWindow, cheapestChargeWindow } from "../src/engine.js";
import { Tariff } from "../src/schema.js";

const vectorsPath = fileURLToPath(
  new URL("../../ratebook/tests/vectors/v0_charge_windows.json", import.meta.url),
);
const data = JSON.parse(readFileSync(vectorsPath, "utf8")) as {
  cases: {
    name: string;
    tariff: Record<string, unknown>;
    window: { start: string; days: number };
    charge_hours: number;
    tier: number;
    expected: unknown;
  }[];
};

describe("cross-engine charge-window vectors", () => {
  it("has the expected case set", () => {
    expect(data.cases.length).toBeGreaterThanOrEqual(6);
  });

  for (const c of data.cases) {
    it(c.name, () => {
      const tariff = Tariff.fromJson(c.tariff);
      const window = BillingWindow.fromIso(c.window.start, c.window.days);
      const cw = cheapestChargeWindow(tariff, window, c.charge_hours, { tier: c.tier });
      expect(cw.toJson()).toEqual(c.expected);
    });
  }

  it("notBefore excludes past windows (matches the Python engine)", () => {
    const flat = Tariff.fromJson(data.cases[0].tariff); // PECO flat — every block ties
    const window = BillingWindow.fromIso("2025-06-02", 1);
    const cw = cheapestChargeWindow(flat, window, 3, {
      notBefore: new Date(Date.UTC(2025, 5, 2, 10, 30)),
    });
    expect(cw.toJson().start).toBe("2025-06-02T11:00:00");
  });
});
