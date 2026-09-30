# Notes

## What was built

- `POST /orders/{order_id}/apply-discount` — [app/api/orders.py](app/api/orders.py), business rules in
  [app/services/orders.py](app/services/orders.py), money math in [app/services/pricing.py](app/services/pricing.py).
- `POST /webhooks/payment` — [app/api/webhooks.py](app/api/webhooks.py), signature check via
  `StubGateway.verify` (added to [app/gateway.py](app/gateway.py)).
- Tests: [tests/test_apply_discount.py](tests/test_apply_discount.py),
  [tests/test_webhook_payment.py](tests/test_webhook_payment.py). `make test` — 22 passed.
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
gets `409 Conflict` regardless of whether the order already has a discount, is already paid, or
whether two codes are applied concurrently (I have a test for the concurrent case — two different
codes racing for the same order — using an atomic
`find_one_and_update({"discount": {"$exists": False}, ...})` in
[app/repositories/orders.py](app/repositories/orders.py) so exactly one request can win rather
than a check-then-write race letting both through). Stacking codes, or replacing one code with
another, was out of scope for the time available; a real system would need product input on
whether stacking is ever allowed before this is more than "reject the second one."

## One thing the AI tool got wrong

See `prompts/` for the full conversation. While drafting the webhook idempotency test, my first
version compared payment amounts across duplicate deliveries using the wrong field name at the
service layer, and separately I initially planned to return a `422` for the amount-mismatch case
(the fixture where a payment arrives for the pre-discount amount after a discount was applied to
the order). I caught this once I actually read `app/gateway.py`'s note that delivery is
at-least-once — retrying a `422` gains the gateway nothing, since the amount will never change on
retry, so it just spins forever. I changed it to acknowledge (`200`) without marking the order
paid, and left a comment plus this note explaining that production needs a real
reconciliation/alerting path here, which this exercise doesn't build.

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

Roughly 2h45m total:
- ~40 min reading the template thoroughly (README, models, gateway docs, repositories, seed data,
  fixtures.json, existing tests) before writing anything, plus setting up the GitHub repo from the
  template and a local Python venv / npm install.
- ~85 min backend: pricing module, models, repository atomic updates, service-layer business
  rules, both routes, and the two new test files (including the concurrency test).
- ~20 min client task: `formatPaise.ts`, `OrderSummary.tsx`, and their tests.
- ~20 min this `NOTES.md` and assembling `prompts/`.
