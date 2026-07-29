import { describe, expect, it } from "vitest";
import { compareDecimalStrings, formatPercent } from "@/features/screener/screener-dashboard";

describe("Sprint 19 exact financial formatting", () => {
  it.each([["0.03","3%"],["0.00125","0.125%"],["0","0%"]])("formats %s", (value, expected) => expect(formatPercent(value)).toBe(expected));
  it("formats missing percentages", () => expect(formatPercent(null)).toBe("—"));
  it("compares exact large Decimal strings", () => {
    expect(compareDecimalStrings("900719925474099312345.01", "900719925474099312345.001")).toBeGreaterThan(0);
    expect(compareDecimalStrings("005930", "5930")).toBe(0);
  });
});
