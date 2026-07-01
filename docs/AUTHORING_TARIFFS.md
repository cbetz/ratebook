# Authoring a Ratebook tariff

A Ratebook tariff is one JSON file: the rate ladder (`energy.periods[].tiers[]`), two 12×24
month-by-hour schedules (`schedule.weekday` / `schedule.weekend`), fixed charges, identity,
and provenance. Everything the engine prices is in the file — no code, no lookup tables.

The fastest path is to let an LLM do the transcription and let the engine + your bill do the
verification. The schema is deliberately small enough to paste into a prompt.

## The 15-minute recipe

1. **Get the rate sheet.** Your utility publishes a PDF rate schedule (search
   "`<utility>` `<plan code>` rate schedule pdf"). Grab the current one — check the
   effective date.
2. **Ask an LLM to transcribe it.** Paste the rate sheet (or its text) plus an existing
   tariff as a template — a TOU example is
   [`sdge-tou-dr-1.json`](../packages/ratebook-data/dataset/tariffs/sdge-tou-dr-1.json), a
   tiered-baseline example is
   [`pge-e-tou-c.json`](../packages/ratebook-data/dataset/tariffs/pge-e-tou-c.json) — with a
   prompt like:

   > Transcribe this electricity rate sheet into the same JSON schema as the example.
   > Rules: every rate is a string; a tier's customer price is `rate + adj`; the two
   > schedules are 12 month-rows × 24 hour-columns of indices into `energy.periods` (row 0 =
   > January, hour column 0 = midnight, local time); make one period per season × TOU block;
   > if the sheet names holidays that price off-peak, set `schedule.holiday_policy` to
   > `"as_weekend"` and list them in `schedule.holidays` (vocabulary: `new_years_day`,
   > `mlk_day`, `washingtons_birthday`, `memorial_day`, `juneteenth`, `independence_day`,
   > `labor_day`, `columbus_day`, `veterans_day`, `thanksgiving`, `day_after_thanksgiving`,
   > `christmas`).

3. **Validate with the engine.** From a checkout of this repo:

   ```bash
   uv run python - <<'EOF'
   import json
   from ratebook import Tariff, BillingWindow, hourly_marginal_prices
   from ratebook.validate import validate_tariff
   from ratebook.engine import supported
   import datetime as dt

   t = Tariff.from_json(json.load(open("my-tariff.json")))
   print("issues:", validate_tariff(t))          # structural problems, if any
   print(supported(t))                            # fully_supported=True is the goal
   # Spot-check a summer weekday + winter weekend against the rate sheet:
   print([str(p) for p in hourly_marginal_prices(t, BillingWindow(dt.date(2026, 7, 15), 1))])
   print([str(p) for p in hourly_marginal_prices(t, BillingWindow(dt.date(2026, 1, 17), 1))])
   EOF
   ```

4. **Check one real bill.** `estimate_bill` with your billing window and kWh should land on
   your bill's energy charge. If it doesn't, the transcription (or the rate sheet's riders)
   is the reason — that difference is exactly what's worth documenting in `provenance`.
5. **Use it or share it.** Paste the JSON straight into the Home Assistant config flow
   ("Custom tariff JSON"), or open a PR adding it to
   `packages/ratebook-data/dataset/` (+ a manifest entry) so everyone on your utility gets
   it in the dropdown. Fill `provenance.last_verified` and `source_documents`.

## Gotchas

- **`rate` + `adj` must sum to the all-in price** a default-service customer pays per kWh
  (supply + delivery + riders, pre-tax). A delivery-only number looks plausible and is
  silently ~half the real price — the #1 transcription error. Cross-check the sum against
  the "price to compare" or an actual bill line.
- **Tier caps**: `"kWh daily"` maxes are daily baseline allowances (they scale by days in
  the billing window); `"kWh"` maxes are per-window totals.
- **Schedules are local time**, hour-beginning columns: column 16 covers 4-5pm.
- **Seasons live in the schedule**, not in the tiers: summer and winter get different
  periods, and the month rows point at the right one.
