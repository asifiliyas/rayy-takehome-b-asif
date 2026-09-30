import { useState } from "react";
import { formatPaise } from "./formatPaise";
import type { Order } from "./types";

/**
 * Shows the subtotal, the discount (code and amount) when there is one, and
 * the total, all through formatPaise, plus a "Pay" button that calls onPay.
 *
 * - The button is disabled while onPay is pending (no double submit); it
 *   still reads "Pay".
 * - Only when order.status is "paid" does the button read "Paid"; it is then
 *   disabled.
 * - If onPay rejects, show an error in an element with role="alert" and
 *   re-enable the button.
 */
export function OrderSummary(props: { order: Order; onPay: () => Promise<void> }): JSX.Element {
  const { order, onPay } = props;
  const [isPaying, setIsPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isPaid = order.status === "paid";

  async function handlePay() {
    setError(null);
    setIsPaying(true);
    try {
      await onPay();
    } catch {
      setError("Payment failed. Please try again.");
    } finally {
      setIsPaying(false);
    }
  }

  return (
    <section aria-label="Order summary">
      <h2>Order {order.order_id}</h2>
      <dl>
        <dt>Subtotal</dt>
        <dd>{formatPaise(order.subtotal_paise)}</dd>
        {order.discount && (
          <>
            <dt>Discount ({order.discount.code})</dt>
            <dd>-{formatPaise(order.discount.amount_paise)}</dd>
          </>
        )}
        <dt>Total</dt>
        <dd>{formatPaise(order.total_paise)}</dd>
      </dl>
      <button type="button" onClick={handlePay} disabled={isPaying || isPaid}>
        {isPaid ? "Paid" : "Pay"}
      </button>
      {error && <div role="alert">{error}</div>}
    </section>
  );
}
