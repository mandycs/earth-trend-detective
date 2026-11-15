import { test } from "node:test";
import assert from "node:assert/strict";
import { FADED_PLAIN, plainLegendLabel, plainLegendLabels } from "../legendWords.ts";

test("statistics jargon in a faded label becomes plain words", () => {
  assert.equal(plainLegendLabel("Faded = not statistically significant (Mann-Kendall p ≥ 0.05)"), FADED_PLAIN);
  assert.equal(plainLegendLabel("Faded = not significant (p-value > 0.05)"), FADED_PLAIN);
  assert.equal(plainLegendLabel("Faded where p >= 0.05"), FADED_PLAIN);
  assert.equal(plainLegendLabel("↑ more heat (warmer ground)"), "↑ more heat (warmer ground)");
  assert.equal(plainLegendLabel("Mann-Kendall test"), null);
  assert.deepEqual(plainLegendLabels(["Wetter", "Faded (Mann-Kendall)", "Faded = significant?"]), ["Wetter", FADED_PLAIN]);
});
