/**
 * Presentation-only decimal formatter. Removes trailing fractional zeroes and
 * a now-empty decimal point; every other character and meaningful digit stays intact.
 */
export function formatDecimal(value: string): string {
  if (!value.includes(".")) return value;
  return value.replace(/(\.\d*?[1-9])0+$/, "$1").replace(/\.0+$/, "");
}

/** Convert an exact decimal ratio to percentage text without floating point. */
export function formatRatioPercent(value: string | null | undefined): string {
  if (value == null) return "—";
  const match = value.match(/^([+-]?)(\d+)(?:\.(\d*))?$/);
  if (!match) return "—";
  const [, sign, whole, fraction = ""] = match;
  const digits = `${whole}${fraction}`;
  const decimalIndex = whole.length + 2;
  const padded = digits.padEnd(decimalIndex, "0");
  const integer = padded.slice(0, decimalIndex).replace(/^0+(?=\d)/, "") || "0";
  const decimals = padded.slice(decimalIndex);
  const result = decimals ? `${integer}.${decimals}` : integer;
  const normalized = formatDecimal(result.replace(/^0+(?=\d)/, ""));
  return `${sign === "-" && normalized !== "0" ? "-" : ""}${normalized}%`;
}
