import styles from "./explore.module.css";

export const STEPS = ["What's changing?", "Is it real?", "Is it the climate?"] as const;

interface Props {
  current: number;
  onSelect: (step: number) => void;
}

export default function StepIndicator({ current, onSelect }: Props) {
  return (
    <nav aria-label="Investigation steps">
      <ol className={styles.steps}>
        {STEPS.map((title, i) => (
          <li key={title}>
            <button
              type="button"
              className={styles.step}
              aria-current={i === current ? "step" : undefined}
              onClick={() => onSelect(i)}
            >
              <span className={styles.stepNum} aria-hidden="true">
                {i < current ? "✓" : i + 1}
              </span>
              <span className={styles.stepTitle}>
                <span className={styles.srOnly}>Step {i + 1}: </span>
                {title}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
