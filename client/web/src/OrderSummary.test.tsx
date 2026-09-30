import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OrderSummary } from "./OrderSummary";
import type { Order } from "./types";

const order: Order = {
  order_id: "ord_test_1",
  subtotal_paise: 19999,
  total_paise: 19999,
  status: "pending",
  discount: null,
};

const discountedOrder: Order = {
  order_id: "ord_test_2",
  subtotal_paise: 199999,
  total_paise: 169999,
  status: "pending",
  discount: { code: "DEMO15", amount_paise: 30000 },
};

describe("OrderSummary", () => {
  it("renders", () => {
    render(<OrderSummary order={order} onPay={async () => {}} />);
    expect(screen.getByRole("region", { name: "Order summary" })).toBeInTheDocument();
  });

  it("shows subtotal and total through formatPaise, with no discount row", () => {
    render(<OrderSummary order={order} onPay={async () => {}} />);
    expect(screen.getAllByText("₹199.99")).toHaveLength(2); // subtotal and total match when there's no discount
    expect(screen.queryByText(/Discount/)).not.toBeInTheDocument();
  });

  it("shows the discount code and amount when there is one", () => {
    render(<OrderSummary order={discountedOrder} onPay={async () => {}} />);
    expect(screen.getByText("Discount (DEMO15)")).toBeInTheDocument();
    expect(screen.getByText("-₹300.00")).toBeInTheDocument();
    expect(screen.getByText("₹1,699.99")).toBeInTheDocument();
  });

  it("disables the Pay button while payment is in progress, and keeps the label", async () => {
    let resolvePay: () => void = () => {};
    const onPay = vi.fn(() => new Promise<void>((resolve) => (resolvePay = resolve)));
    render(<OrderSummary order={order} onPay={onPay} />);

    const button = screen.getByRole("button", { name: "Pay" });
    fireEvent.click(button);

    await waitFor(() => expect(button).toBeDisabled());
    expect(button).toHaveTextContent("Pay");

    resolvePay();
    await waitFor(() => expect(button).not.toBeDisabled());
  });

  it("shows 'Paid' and stays disabled when the order status is paid", () => {
    render(<OrderSummary order={{ ...order, status: "paid" }} onPay={async () => {}} />);
    const button = screen.getByRole("button", { name: "Paid" });
    expect(button).toBeDisabled();
  });

  it("shows an alert and re-enables the button when payment fails", async () => {
    const onPay = vi.fn(() => Promise.reject(new Error("card declined")));
    render(<OrderSummary order={order} onPay={onPay} />);

    fireEvent.click(screen.getByRole("button", { name: "Pay" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Pay" })).not.toBeDisabled();
  });
});
