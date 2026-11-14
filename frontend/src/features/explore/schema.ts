import { z } from "zod";

const num = z.number().nullable();

export const variableSchema = z.object({
  id: z.string(),
  label: z.string(),
  unit: z.string(),
  sen_slope_per_decade: num,
  ci_low: num,
  ci_high: num,
  sigma_per_decade: num,
  p_value: num,
  q_value: num,
  verdict: z.enum(["real", "likely", "unknown"]),
  direction: z.enum(["up", "down", "flat"]),
  n_months: z.number(),
  years_span: z.number(),
  too_short: z.boolean(),
  years_needed: num.optional().default(null),
  residual_pct_non_climate: num.optional().default(null),
  residual_pct_range: z.tuple([z.number(), z.number()]).nullable().optional().default(null),
});

export const sweepSchema = z.object({
  lat: z.number(),
  lon: z.number(),
  start: z.number(),
  end: z.number(),
  source: z.string(),
  variables: z.array(variableSchema),
  series: z
    .record(z.array(z.object({ date: z.string(), value: num, anomaly: num })))
    .optional(),
});

export const sitesSchema = z.array(
  z.object({
    id: z.string(),
    name: z.string(),
    bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
    point: z.tuple([z.number(), z.number()]),
    tags: z.array(z.string()),
  }),
);
