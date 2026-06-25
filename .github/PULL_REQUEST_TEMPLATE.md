<!-- Thanks for contributing to Ratebook. Keep PRs focused; one logical change per PR. -->

## Summary

<!-- What does this change and why? Link any related issue (e.g. "Fixes #123"). -->

## Type of change

- [ ] Tariff correction (data fix to the corpus)
- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (changes existing behavior or output)
- [ ] Docs / tooling only

## Checklist

- [ ] Tests added or updated, and `uv run pytest` passes locally
- [ ] `uv run ruff check .` is clean
- [ ] If I touched either engine, both still reproduce `packages/ratebook/tests/vectors/v0_bills.json` byte-for-byte (`pnpm -C packages/ratebook-ts test`; regenerate via `uv run python packages/ratebook/tests/generate_vectors.py` only when the change is intended and explained above)
- [ ] For a tariff correction: the source tariff PDF URL and effective date are included above or in the linked issue

## DCO sign-off

- [ ] I certify that this contribution is made under the project's license and I have the right to submit it under the [Developer Certificate of Origin](https://developercertificate.org/) — I have signed off my commits (`git commit -s`).
