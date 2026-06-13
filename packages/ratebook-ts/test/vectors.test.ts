// The cross-engine contract: the TypeScript engine must reproduce the Python engine's golden
// bill vectors byte-for-byte. Both read the SAME file
// (packages/ratebook/tests/vectors/v0_bills.json); regenerate it with
// `uv run python packages/ratebook/tests/generate_vectors.py`.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { BillingWindow, estimateBill, Usage } from "../src/engine.js";
import { Tariff } from "../src/schema.js";

const vectorsPath = fileURLToPath(
  new URL("../../ratebook/tests/vectors/v0_bills.json", import.meta.url),
);
const data = JSON.parse(readFileSync(vectorsPath, "utf8")) as {
  cases: {
    name: string;
    tariff: Record<string, unknown>;
    usage: { total_kwh?: string; hourly_kwh?: string[] };
    window: { start: string; days: number };
    expected: unknown;
  }[];
};

function usageFromJson(u: { total_kwh?: string; hourly_kwh?: string[] }): Usage {
  return u.hourly_kwh ? Usage.hourly(u.hourly_kwh) : Usage.aggregate(u.total_kwh!);
}

describe("cross-engine golden vectors", () => {
  it("has the expected case set", () => {
    expect(data.cases.length).toBeGreaterThanOrEqual(10);
  });

  for (const c of data.cases) {
    it(c.name, () => {
      const tariff = Tariff.fromJson(c.tariff);
      const usage = usageFromJson(c.usage);
      const window = BillingWindow.fromIso(c.window.start, c.window.days);
      const result = estimateBill(tariff, usage, window);
      expect(result.toJson()).toEqual(c.expected);
    });
  }
});
