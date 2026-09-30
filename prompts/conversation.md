# AI prompt history

Tool: Claude Code (Sonnet 5), running as a CLI/IDE agent with file read/write and shell access.
This is a raw, un-tidied transcript of the actual session that produced this repo — user turns
verbatim, assistant turns verbatim (prose only; tool calls are summarized inline since the tool's
own JSON payloads aren't meaningful to read back and the harness doesn't export them separately).

---

## Turn 1 — user

> So i have recieved an assignment lets rock it - "RAYY Product Engineer · PE-012 · Take-home
> exercise ... [full hiring email pasted, describing the take-home: fork
> github.com/rayy-hiring/rayy-takehome-b, backend + ~20min client task in Flutter or React,
> prompts/ folder with AI history required for a pass, NOTES.md required, reply within 48 hours
> with the repo link] ... do online resarech as well no guessing no mistakes we doing extra so
> that they like it"

## Turn 1 — assistant

Fetched the template repo's README via `gh`/WebFetch to get the exact spec instead of guessing
from the email summary alone. Confirmed: FastAPI + MongoDB backend, two endpoints
(`apply-discount`, `webhooks/payment`), tests, a client task in Flutter *or* React, `NOTES.md`
with five specific required answers, and a mandatory `prompts/` folder.

Asked the user two clarifying questions before touching anything external, since both affect
what gets pushed to a public GitHub account:

1. Client stack — React vs Flutter → user chose **React**.
2. Repo visibility — private-with-collaborator vs public → user chose **public**.

## Turn 2 — assistant (continued, same task, no further user input yet)

Ran, in order:

- `gh api user --jq '.login'` → confirmed authenticated as `asifiliyas`.
- `gh repo create rayy-takehome-b-asif --public --template rayy-hiring/rayy-takehome-b --clone`
  → created the repo from the template and cloned it locally.
- Read the real `README.md`, `app/models.py`, `app/gateway.py`, `app/api/orders.py`,
  `app/services/orders.py`, `app/repositories/orders.py`, `app/repositories/discount_codes.py`,
  `app/config.py`, `app/db.py`, `app/main.py`, `app/seed.py`, `seed/orders.json`,
  `seed/discount_codes.json`, `seed/fixtures.json`, `tests/conftest.py`, `tests/test_orders.py`,
  `tests/test_gateway.py`, `pytest.ini`, `requirements.txt`, `Makefile`, `docker-compose.yml`, and
  the React starter (`types.ts`, `formatPaise.ts`, `OrderSummary.tsx`, `OrderSummary.test.tsx`,
  `main.tsx`, `package.json`) — in full, before writing any code, specifically to avoid guessing
  at field names, existing conventions, or the client contract.

Key things this reading surfaced that shaped the design:

- `app/gateway.py`'s docstring: webhook delivery is **at-least-once**, and the stub always
  delivers every event **twice** — so the webhook handler has to be idempotent by `payment_id`,
  not just "mark paid."
- `seed/fixtures.json` includes an `apply_4`/`apply_5` pair — the same two codes applied to two
  different orders, one "at_the_same_time" and one "one_after_another" — which reads as a
  deliberate hint to test the *concurrent* double-apply case, not just the sequential one.
- `seed/fixtures.json`'s `webhook_2` fires *after* `apply_2` (a discount) on the same order, but
  carries the **pre-discount** `amount_paise`. That's a deliberately planted amount-mismatch case,
  not an accident — it directly informed the "don't blindly trust the gateway's amount" decision
  in NOTES.md.
- The React starter's `Order` type only has `{ code, amount_paise }` for `discount`, and `onPay`
  is injected as a prop — meaning the client task is a pure presentational-component exercise,
  not something that needs to be wired to the real backend API. That kept the client task to
  roughly its intended ~20 minutes.

Then implemented, in order:

1. `app/services/pricing.py` — pure integer-math helpers: `round_half_up_div` and
   `compute_discount`/`split_discount`, kept deliberately free of any DB or HTTP code so the
   money math is unit-testable and out of the route handlers (the README asks for this
   explicitly).
2. `app/models.py` — added `AppliedDiscount`, `PaymentRecord`, `ApplyDiscountRequest`,
   `PaymentWebhookBody`; extended `Order` with optional `discount`/`payment`.
3. `app/gateway.py` — added a `verify(body, signature)` method (timing-safe `hmac.compare_digest`)
   alongside the existing `sign`, since the webhook handler needs to check the signature the
   README describes and the stub only had `sign`.
4. `app/repositories/orders.py` — added `apply_discount_atomic` and `record_payment_atomic`, both
   single-document `find_one_and_update`s with a filter that only matches if the precondition
   (`no discount yet` / `no payment yet`) still holds, specifically so two concurrent requests
   can't both win the race the fixtures hint at.
5. `app/services/orders.py` — business rules: order/code lookup, expiry check, "one discount per
   order, ever" rule, discount computation via the pricing module, and payment recording with
   amount-match + idempotent-duplicate-delivery handling.
6. `app/api/orders.py` — thin route for `POST /orders/{id}/apply-discount`, translating service
   exceptions to HTTP status codes only.
7. `app/api/webhooks.py` (new) — `POST /webhooks/payment`: verifies the signature, parses and
   validates the body, calls the service, and maps `PaymentAmountMismatch` to a `200` with a
   distinct `amount_mismatch` status (explained in NOTES.md) rather than a `4xx` that a real
   gateway would just retry forever for no benefit.
8. `app/main.py` — registered the new webhooks router.
9. `tests/test_apply_discount.py` and `tests/test_webhook_payment.py` — new tests, including one
   that fires two different discount codes at the same order with `asyncio.gather` to exercise
   the concurrency path.

Before hand-writing any expected numbers into the tests, ran the actual `pricing.py` functions
in a scratch Python one-liner against every code/order pair from `seed/fixtures.json` and used
those printed values in the tests — specifically to avoid the "no guessing, no mistakes"
instruction being violated by mental arithmetic on basis-point percentages.

Ran `MONGO_URL=mongomock://localhost python -m pytest -q` after every batch of changes; final run
was 22/22 passing (8 pre-existing + 14 new).

For the client: implemented `formatPaise.ts` (Indian digit grouping via a regex lookahead
grouping pairs after the first group of three, integer math throughout, throws only on
non-integer input per the spec's note that only the Dart version throws on negative amounts) and
`OrderSummary.tsx` (subtotal/discount/total rows, a `Pay`/`Paid` button with `useState` for the
in-flight and error states, `role="alert"` on failure). Added `formatPaise.test.ts` and extended
`OrderSummary.test.tsx`. Ran `npm ci && npm test` (10/10 passing) and `npm run typecheck` (clean)
in the actual `client/web/` directory — not just read the code and assumed it worked.

One self-caught mistake, called out in more detail in `NOTES.md`: the amount-mismatch webhook
case was initially going to return `422`, which on reflection doesn't fit an at-least-once,
retry-forever delivery model (retrying changes nothing about a wrong amount), so it was changed
to acknowledge with `200` and a distinct body instead, without marking the order paid.

Wrote `NOTES.md` covering the five required points (settlement fields/query, rounding decision,
second-code decision, one AI mistake caught, production-trust gaps, time breakdown) and this
`prompts/` folder.
