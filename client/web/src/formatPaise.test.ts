import { describe, expect, it } from "vitest";
import { formatPaise } from "./formatPaise";

describe("formatPaise", () => {
  it("formats with Indian digit grouping and two decimals", () => {
    expect(formatPaise(199999)).toBe("₹1,999.99");
    expect(formatPaise(12345678)).toBe("₹1,23,456.78");
    expect(formatPaise(5)).toBe("₹0.05");
    expect(formatPaise(0)).toBe("₹0.00");
  });

  it("groups very large amounts correctly", () => {
    expect(formatPaise(123456789012)).toBe("₹1,23,45,67,890.12");
  });

  it("handles amounts under one rupee", () => {
    expect(formatPaise(99)).toBe("₹0.99");
  });

  it("throws on non-integer input", () => {
    expect(() => formatPaise(19.5)).toThrow();
  });
});
