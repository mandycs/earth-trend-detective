import { badgeFor } from "./format";
import type { Direction, Verdict } from "./types";
import styles from "./explore.module.css";

export default function Badge({ verdict, direction }: { verdict: Verdict; direction: Direction }) {
  const b = badgeFor(verdict, direction);
  return (
    <span className={`${styles.badge} ${styles[`tone_${b.tone}`]} ${styles[`strength_${b.strength}`]}`} title={b.meaning}>
      <span aria-hidden="true" className={styles.badgeIcon}>
        {b.icon}
      </span>
      <span>{b.text}</span>
    </span>
  );
}
