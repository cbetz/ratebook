# ratebook

Deterministic US electricity tariff rate engine. Pure functions, no I/O, no surprises —
correctness bugs here are customer-facing "your app lied about my bill" failures, so
everything is property-tested (hypothesis) and cross-validated against NREL's PySAM
`utilityrate5` on representative tariffs spanning the supported structure classes. (PySAM is a
test-only oracle; those tests skip when it isn't installed — `uv sync --group validation` to run
them.)

v0 scope: tiered + time-of-use + seasonal energy charges plus fixed/minimum charges.
