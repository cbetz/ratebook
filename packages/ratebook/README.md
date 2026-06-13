# ratebook

Deterministic US electricity tariff rate engine. Pure functions, no I/O, no surprises —
correctness bugs here are customer-facing "your app lied about my bill" failures, so
everything is property-tested (hypothesis) and validated against PySAM `utilityrate5`.

Sprint 0 scope: tiered + time-of-use + seasonal energy charges plus fixed charges.
