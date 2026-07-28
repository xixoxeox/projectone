export type DisplayValue = string | number | null | undefined;

export function displayDecimal(value: DisplayValue): string {
  if (value === null || value === undefined) return "—";
  return String(value).replace(/(\.\d*?[1-9])0+$|\.0+$/, "$1");
}

export function money(value: DisplayValue): string {
  return value === null || value === undefined
    ? "—"
    : `${displayDecimal(value)} 원`;
}

export function percent(value: DisplayValue): string {
  return value === null || value === undefined
    ? "—"
    : `${decimalTimes100(String(value))}%`;
}

function decimalTimes100(value: string): string {
  const negative = value.startsWith("-");
  const raw = negative ? value.slice(1) : value;
  const [whole, fraction = ""] = raw.split(".");
  const digits = (whole + fraction).replace(/^0+(?=\d)/, "") || "0";
  const scale = fraction.length - 2;
  const output =
    scale <= 0
      ? digits + "0".repeat(-scale)
      : `${digits.slice(0, -scale) || "0"}.${digits.slice(-scale).padStart(scale, "0")}`;
  return `${negative ? "-" : ""}${displayDecimal(output)}`;
}

export function dateTime(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function compareDecimal(a: string | number, b: string | number): number {
  const normalize = (value: string | number) => {
    const raw = String(value);
    const negative = raw.startsWith("-");
    const [whole, fraction = ""] = (negative ? raw.slice(1) : raw).split(".");
    return {
      negative,
      whole: whole.replace(/^0+/, "") || "0",
      fraction: fraction.replace(/0+$/, ""),
    };
  };
  const left = normalize(a);
  const right = normalize(b);
  if (left.negative !== right.negative) return left.negative ? -1 : 1;
  const direction = left.negative ? -1 : 1;
  if (left.whole.length !== right.whole.length) {
    return left.whole.length > right.whole.length ? direction : -direction;
  }
  const width = Math.max(left.fraction.length, right.fraction.length);
  const leftDigits = left.whole + left.fraction.padEnd(width, "0");
  const rightDigits = right.whole + right.fraction.padEnd(width, "0");
  if (leftDigits === rightDigits) return 0;
  return leftDigits > rightDigits ? direction : -direction;
}
