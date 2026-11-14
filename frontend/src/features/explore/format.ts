import type { Direction, Verdict, VariableResult } from "./types";

const MINUS = "−";

/** Two significant digits, real minus sign, optional leading plus. */
export function fmtNumber(value: number, signed = false): string {
  if (value === 0) return "0";
  const abs = Math.abs(value);
  const text = new Intl.NumberFormat("en-US", {
    maximumSignificantDigits: 2,
    maximumFractionDigits: abs >= 1 ? 1 : 6,
  }).format(abs);
  if (value < 0) return `${MINUS}${text}`;
  return signed ? `+${text}` : text;
}

export function fmtSlope(v: VariableResult): string | null {
  if (v.sen_slope_per_decade == null) return null;
  return `${fmtNumber(v.sen_slope_per_decade, true)} ${v.unit}`;
}

export function fmtPlace(lat: number, lon: number): string {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(2)}° ${ns}, ${Math.abs(lon).toFixed(2)}° ${ew}`;
}

export interface BadgeInfo {
  icon: string;
  text: string;
  tone: "up" | "down" | "neutral";
  strength: Verdict;
  meaning: string;
}

export function badgeFor(verdict: Verdict, direction: Direction): BadgeInfo {
  if (verdict === "unknown" || direction === "flat") {
    return {
      icon: "?",
      text: "Can't tell yet",
      tone: "neutral",
      strength: "unknown",
      meaning: "Too noisy or too short to tell a real change from chance.",
    };
  }
  const icon = direction === "up" ? "↑" : "↓";
  const tone = direction;
  if (verdict === "real") {
    return {
      icon,
      text: "Real",
      tone,
      strength: "real",
      meaning: `Going ${direction}, and very unlikely to be chance.`,
    };
  }
  return {
    icon,
    text: "Likely",
    tone,
    strength: "likely",
    meaning: `Probably going ${direction}. A strong hint, not yet proof.`,
  };
}

/** The confidence interval in plain words. */
export function rangeInWords(v: VariableResult): string {
  if (v.too_short) return "There is not enough data here yet to give a range.";
  if (v.ci_low == null || v.ci_high == null) return "We can't give a reliable range for this one.";
  const lo = fmtNumber(v.ci_low, true);
  const hi = fmtNumber(v.ci_high, true);
  const unit = `${v.unit} per decade`;
  if (v.ci_low <= 0 && v.ci_high >= 0) {
    return `The true change could be anywhere from ${lo} to ${hi} ${unit}. That includes no change at all.`;
  }
  return `The true change is most likely between ${lo} and ${hi} ${unit}.`;
}

export function moreDataInWords(v: VariableResult): string | null {
  if (v.verdict === "real") return null;
  if (v.too_short) return "Not enough months of data to test this here.";
  if (v.years_needed != null) {
    return `≈ ${v.years_needed} more ${v.years_needed === 1 ? "year" : "years"} of data needed to tell, if the trend keeps going.`;
  }
  if (v.verdict === "unknown") return "No sign of a trend so far.";
  return null;
}

/** One-line summary for the top of the results. */
export function summary(vars: VariableResult[]): string {
  const real = vars.filter((v) => v.verdict === "real" && v.direction !== "flat");
  const likely = vars.filter((v) => v.verdict === "likely" && v.direction !== "flat");
  const n = vars.length;
  const list = (xs: VariableResult[]) =>
    xs.map((v) => `${v.label.toLowerCase()} (${v.direction === "up" ? "up" : "down"})`).join(", ");
  if (real.length > 0) {
    return `${real.length} of ${n} climate signals ${real.length === 1 ? "is" : "are"} changing for real here: ${list(real)}.`;
  }
  if (likely.length > 0) {
    return `Nothing is proven yet, but ${list(likely)} ${likely.length === 1 ? "is" : "are"} probably changing.`;
  }
  return `None of the ${n} climate signals shows a change we can tell apart from chance yet.`;
}
