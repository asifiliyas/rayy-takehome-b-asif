/**
 * Format integer paise as rupees: en-IN digit grouping, exactly two decimals,
 * integer maths only (no floating-point division of the amount).
 *
 *   formatPaise(199999)   === "₹1,999.99"
 *   formatPaise(12345678) === "₹1,23,456.78"
 *   formatPaise(5)        === "₹0.05"
 *   formatPaise(0)        === "₹0.00"
 *
 * Throws an Error if `paise` is not an integer.
 */
export function formatPaise(paise: number): string {
  if (!Number.isInteger(paise)) {
    throw new Error("formatPaise: paise must be an integer");
  }

  const sign = paise < 0 ? "-" : "";
  const abs = Math.abs(paise);
  const rupees = Math.trunc(abs / 100);
  const cents = String(abs % 100).padStart(2, "0");

  const digits = String(rupees);
  const lastThree = digits.slice(-3);
  const rest = digits.slice(0, -3);
  const groupedRest = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  const grouped = rest ? `${groupedRest},${lastThree}` : lastThree;

  return `${sign}₹${grouped}.${cents}`;
}
