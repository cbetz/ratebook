// Ratebook rate engine — TypeScript port. Shares JSON test vectors with the Python engine so
// the two never diverge. v0 ports the schema + `estimateBill` + `supported` + the charge-window
// optimization (`cheapestChargeWindow`), each held to Python by shared vectors. `estimateAnnual`
// lands in a follow-up.

export { Decimal, decimalToJson, toDecimal } from "./money.js";
export * from "./schema.js";
export {
  BillingWindow,
  BillResult,
  ChargeWindow,
  LineItem,
  Refusal,
  type RefusalReason,
  SupportReport,
  Usage,
  cheapestChargeWindow,
  estimateBill,
  hourlyMarginalPrices,
  periodAt,
  supported,
} from "./engine.js";
