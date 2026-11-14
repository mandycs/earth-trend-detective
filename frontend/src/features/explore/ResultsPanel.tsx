"use client";

import Link from "next/link";
import Badge from "./Badge";
import StepIndicator, { STEPS } from "./StepIndicator";
import TrendChart from "./TrendChart";
import { badgeFor, fmtNumber, fmtSlope, moreDataInWords, rangeInWords, summary } from "./format";
import type { SweepResponse, VariableResult } from "./types";
import { residualText } from "../../lib/cases";
import styles from "./explore.module.css";

interface Props {
  result: SweepResponse;
  step: number;
  onStep: (step: number) => void;
}

function NextButton({ step, onStep }: { step: number; onStep: (s: number) => void }) {
  if (step >= STEPS.length - 1) return null;
  return (
    <button type="button" className={styles.primary} onClick={() => onStep(step + 1)}>
      Next: {STEPS[step + 1]} <span aria-hidden="true">→</span>
    </button>
  );
}

function WhatsChanging({ result }: { result: SweepResponse }) {
  return (
    <>
      <p className={styles.lead}>{summary(result.variables)}</p>
      <p className={styles.note}>
        We checked every NASA climate signal for this point, month by month from {result.start} to {result.end}.
        Biggest change first.
      </p>
      <ul className={styles.cards}>
        {result.variables.map((v) => (
          <li key={v.id} className={styles.card}>
            <div className={styles.cardHead}>
              <h3 className={styles.cardTitle}>{v.label}</h3>
              <Badge verdict={v.verdict} direction={v.direction} />
            </div>
            {fmtSlope(v) && (
              <p className={styles.slope}>
                <span className={styles.slopeValue}>{fmtSlope(v)}</span> per decade
              </p>
            )}
            <TrendChart variable={v} points={result.series?.[v.id]} />
          </li>
        ))}
      </ul>
    </>
  );
}

function IsItReal({ result }: { result: SweepResponse }) {
  return (
    <>
      <p className={styles.lead}>Every place has odd years. We check whether each change is bigger than that noise.</p>
      <ul className={styles.legend} aria-label="What the labels mean">
        <li>
          <Badge verdict="real" direction="up" /> very unlikely to be chance.
        </li>
        <li>
          <Badge verdict="likely" direction="up" /> a strong hint, not yet proof.
        </li>
        <li>
          <Badge verdict="unknown" direction="flat" /> too noisy or too short to say.
        </li>
      </ul>
      <ul className={styles.cards}>
        {result.variables.map((v) => {
          const more = moreDataInWords(v);
          return (
            <li key={v.id} className={styles.card}>
              <div className={styles.cardHead}>
                <h3 className={styles.cardTitle}>{v.label}</h3>
                <Badge verdict={v.verdict} direction={v.direction} />
              </div>
              <p>{badgeFor(v.verdict, v.direction).meaning}</p>
              <p>{rangeInWords(v)}</p>
              {more && <p className={styles.more}>{more}</p>}
            </li>
          );
        })}
      </ul>
      <HowWeKnow variables={result.variables} source={result.source} />
    </>
  );
}

function HowWeKnow({ variables, source }: { variables: VariableResult[]; source: string }) {
  return (
    <details className={styles.details}>
      <summary>How we know (the method)</summary>
      <div className={styles.detailsBody}>
        <p>
          Data: {source}. We remove the normal yearly cycle (each month minus its usual value), then run a
          Mann-Kendall trend test with the Hamed-Rao correction for autocorrelation. The size of the change is the
          Theil-Sen slope with its 95% confidence interval.
        </p>
        <p>
          Because we test several variables at once, p-values are corrected with the Benjamini-Hochberg false
          discovery rate. <strong>Real</strong> means q &lt; 0.05 after that correction; <strong>Likely</strong>{" "}
          means p &lt; 0.10 before it. &ldquo;Years needed&rdquo; estimates how long the record must be for the
          current slope to reach significance against the observed noise.
        </p>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Variable</th>
              <th scope="col">p</th>
              <th scope="col">q (FDR)</th>
              <th scope="col">Months</th>
            </tr>
          </thead>
          <tbody>
            {variables.map((v) => (
              <tr key={v.id}>
                <th scope="row">{v.label}</th>
                <td>{v.p_value == null ? "n/a" : fmtNumber(v.p_value)}</td>
                <td>{v.q_value == null ? "n/a" : fmtNumber(v.q_value)}</td>
                <td>{v.n_months}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function IsItClimate({ result }: { result: SweepResponse }) {
  const split = result.variables.filter((v) => v.residual_pct_non_climate != null);
  if (split.length > 0) {
    return (
      <>
        <p className={styles.lead}>How much of each change the climate does not explain.</p>
        <ul className={styles.cards}>
          {split.map((v) => (
            <li key={v.id} className={styles.card}>
              <h3 className={styles.cardTitle}>{v.label}</h3>
              <p className={styles.slope}>
                <span className={styles.slopeValue}>{residualText(v)}</span> not explained by climate
                {v.residual_pct_range ? ', depending on the climate model' : ''}
              </p>
            </li>
          ))}
        </ul>
      </>
    );
  }
  return (
    <>
      <p className={styles.lead}>Here, everything we measured is the climate itself: temperature, rain and sunlight.</p>
      <p>
        To tell the climate apart from what people do, we need something the climate acts on, like water stored
        underground or how green the plants are. Then we check how much of its change the climate explains, and what
        is left over.
      </p>
      <p>That deeper check is ready for three real cases, including Lake Mead, where the water is going down.</p>
      <Link href="/story/lake_mead" className={styles.secondaryLink}>
        See the solved cases in story mode <span aria-hidden="true">→</span>
      </Link>
    </>
  );
}

export default function ResultsPanel({ result, step, onStep }: Props) {
  return (
    <div className={styles.results}>
      <StepIndicator current={step} onSelect={onStep} />
      <section aria-labelledby="step-title" className={styles.stepBody}>
        <h2 id="step-title" className={styles.stepHeading}>
          <span className={styles.stepKicker}>Step {step + 1} of 3</span>
          {STEPS[step]}
        </h2>
        {step === 0 && <WhatsChanging result={result} />}
        {step === 1 && <IsItReal result={result} />}
        {step === 2 && <IsItClimate result={result} />}
        <div className={styles.stepNav}>
          {step > 0 && (
            <button type="button" className={styles.ghost} onClick={() => onStep(step - 1)}>
              <span aria-hidden="true">←</span> Back
            </button>
          )}
          <NextButton step={step} onStep={onStep} />
        </div>
      </section>
    </div>
  );
}
