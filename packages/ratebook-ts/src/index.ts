// Ratebook rate engine — TypeScript port. Shares JSON test vectors with the Python engine so
// the two never diverge. v0 ports the schema + `estimateBill` + `supported`; `estimateAnnual`
// and charge-window optimization land in a follow-up with their own shared vectors.

export { Decimal, decimalToJson, toDecimal } from "./money.js";
export * from "./schema.js";
export {
  BillingWindow,
  BillResult,
  LineItem,
  Refusal,
  type RefusalReason,
  SupportReport,
  Usage,
  estimateBill,
  supported,
} from "./engine.js";
