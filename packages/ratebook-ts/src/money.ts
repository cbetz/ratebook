// Decimal arithmetic + canonical JSON codec — the exact-math foundation that lets the TS
// engine reproduce the Python engine's vectors byte-for-byte.
//
// Money and energy quantities are Decimal end to end (never JS number/float). On the JSON wire
// a Decimal is a canonical fixed-point string with no trailing zeros and no exponent — the
// identical form `ratebook.money.decimal_to_json` produces in Python, so the two engines'
// outputs compare equal.

import Decimal from "decimal.js";

// Precision well above Python's 28-significant-digit default context; round half-even to match
// Python's ROUND_HALF_EVEN. Widen the exponent thresholds so toString never uses E-notation in
// our value range (rates, dollars, kWh).
Decimal.set({
  precision: 40,
  rounding: Decimal.ROUND_HALF_EVEN,
  toExpNeg: -30,
  toExpPos: 30,
});

export { Decimal };
export const ZERO = new Decimal(0);

export type DecimalLike = Decimal | string | number;

export function toDecimal(value: DecimalLike): Decimal {
  return value instanceof Decimal ? value : new Decimal(value);
}

export function optDecimal(value: DecimalLike | null | undefined): Decimal | null {
  return value === null || value === undefined || value === "" ? null : toDecimal(value);
}

// Canonical string form: decimal.js never emits trailing zeros, and the widened exponent
// thresholds keep it in fixed notation — matching Python's `format(d, "f")` + strip.
export function decimalToJson(value: Decimal | null): string | null {
  if (value === null) return null;
  const s = value.toString();
  return s === "-0" ? "0" : s;
}
