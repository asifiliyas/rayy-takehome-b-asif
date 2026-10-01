# Notes

## What was built

- `POST /orders/{order_id}/apply-discount` — [app/api/orders.py](app/api/orders.py), business rules in
  [app/services/orders.py](app/services/orders.py), money math in [app/services/pricing.py](app/services/pricing.py).
- `POST /webhooks/payment` — [app/api/webhooks.py](app/api/webhooks.py), signature check via
  `StubGateway.verify` (added to [app/gateway.py](app/gateway.py)); rejects unknown `event` values
  and negative amounts at the model level (`app/models.py`).
- Tests: [tests/test_apply_discount.py](tests/test_apply_discount.py),
  [tests/test_webhook_payment.py](tests/test_webhook_payment.py). `make test` — 24 passed
  (8 from the original template + 16 added).
- Client: **React** (`client/web/`). Implemented `formatPaise.ts` and `OrderSummary.tsx`, plus
  tests in `formatPaise.test.ts` and `OrderSummary.test.tsx`. `npm ci && npm test` — 10 passed.
  Did not touch `client/flutter/`.

## Settlement (5 lines)

Each order stores its discount as a frozen snapshot at apply-time: `code`, `percent_off_bps`,
`cap_paise`, `discount_paise`, `partner_share_bps`, `rayy_share_bps`, `partner_share_paise`,
`rayy_share_paise`, `applied_at` (see `AppliedDiscount` in [app/models.py](app/models.py)).
Storing the split in paise (not just the bps ratio) at apply-time is the important part: a
partner's ratio can change next month, but this month's settlement must use the ratio that was
actually in force when the discount was applied, not whatever the code's ratio is when the query
runs. The monthly settlement query reads all paid orders for a partner with `payment.received_at`
(when the customer actually paid, not `created_at`) in the target month, and sums
`discount.partner_share_paise` across them — that sum is what RAYY owes the partner for discounts
funded that month.

## Rounding decision

A percentage of an integer paise amount can produce a fraction of a paisa (e.g. 12% of ₹299.99 =
3599.88 paise). I round **half up** to the nearest paisa, using integer arithmetic only —
`(numerator + denominator // 2) // denominator` — never floats (see
[app/services/pricing.py](app/services/pricing.py)). The discount is computed first and capped at
`cap_paise`; the partner/RAYY split is then computed from the *capped* discount, again rounding
half up for the partner's share, with the RAYY share taken as the remainder
(`discount_paise - partner_share_paise`) rather than separately rounded. That guarantees
`partner_share_paise + rayy_share_paise == discount_paise` exactly, with no reconciliation gap —
important since this pair is what settlement sums. The 1-paisa rounding remainder, when there is
one, lands with RAYY rather than the partner; that's an arbitrary but consistent choice.

## Second discount code on an order

Rejected outright: an order can carry at most one discount, ever. A second `apply-discount` call
gets `409 Conflict` regardless of whether the order already has a discount or is already paid.
This is enforced by a single atomic `find_one_and_update({"discount": {"$exists": False}, ...})`
in [app/repositories/orders.py](app/repositories/orders.py), not a separate check-then-write, so
two requests that both read the order before either writes still can't both succeed — only one
write will match the filter. `tests/test_apply_discount.py::test_apply_discount_atomic_update_rejects_a_late_write`
proves this directly, by calling the atomic update twice back-to-back. There's also an
`asyncio.gather`-based test with two codes fired at once; worth being honest that it does **not**
exercise a real race — `mongomock_motor`'s async wrappers never yield control (I traced the actual
request path to confirm), so it runs fully sequentially and would pass even with a naive
non-atomic implementation. It's kept because it documents the end-state invariant, with a comment
explaining the limitation. Stacking codes, or replacing one code with another, was out of scope
for the time available; a real system would need product input on whether stacking is ever
allowed before this is more than "reject the second one."

## One thing the AI tool got wrong

See `prompts/` for the full history. The first version of the React test for the no-discount case
asserted `screen.getByText("₹199.99")` expecting a single match. It failed: when an order has no
discount, the subtotal and total are equal, so that text appears twice on the page, and Testing
Library throws on an ambiguous `getByText`. The fix was `getAllByText(...).toHaveLength(2)`
instead. Small, but it's a real, verifiable mistake-and-fix (the failing test output is in the
`prompts/` history) — a better answer than something invented after the fact, which I'd rather
admit I don't have than fabricate.

## Not yet trusted in production

- The amount-mismatch webhook path (see above) just swallows the mismatch with a `200` and a
  distinct response body; nothing pages anyone or queues it for manual review. That's the
  single biggest gap.
- No transactions: `mongomock` (used for `make test`) doesn't support them, so both the discount
  and payment writes are single-document atomic `find_one_and_update`s rather than
  multi-document transactions. That's fine here since everything lives on one order document, but
  I have not run this against the real replica set in `docker-compose.yml` (`make test-mongo`).
- Discount codes are loaded from a JSON file via `lru_cache` (existing code, unchanged) — fine for
  this exercise, but a real partner-config change wouldn't be picked up without a process restart.
- No auth/rate-limiting on `apply-discount`; anyone who can guess an order id could apply a code
  to it.
- The client (`OrderSummary`) is a pure presentational component with an injected `onPay` — it
  isn't wired to the real `POST /orders/{id}/apply-discount` or a payment API, since the task
  scope (per the starter's `Order` type) didn't call for that wiring.

## Time allocation

I did this with Claude Code doing the implementation end-to-end in one agent session, directed and
reviewed by me, plus a second session where I had it audit its own work against this README before
submitting. I don't have a reliable wall-clock breakdown of either session (I wasn't timing myself
against sub-tasks, and an honest minute-by-minute split isn't something either of us can actually
reconstruct after the fact — I'd rather say that than make numbers up). What I can say honestly:
most of the first session went into reading the template thoroughly before writing any code, then
the backend (pricing/models/repositories/services/routes/tests), then the client task, then
`NOTES.md`/`prompts/`. The second session re-read every file fresh, ran the tests itself rather
than trusting the first pass, found that the "concurrent" test didn't prove what it claimed and
fixed it, found two real small validation gaps in the webhook model and fixed those, and found
that this file's original "AI mistake" and time-breakdown sections were not actually supported by
the session history and rewrote them to what's in this version.
