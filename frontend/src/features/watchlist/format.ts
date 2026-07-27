/**
 * Presentation-only decimal formatter. Removes trailing fractional zeroes and
 * a now-empty decimal point; every other character and meaningful digit stays intact.
 */
export function formatDecimal(value: string): string {
  if (!value.includes(".")) return value;
  return value.replace(/(\.\d*?[1-9])0+$/, "$1").replace(/\.0+$/, "");
}
