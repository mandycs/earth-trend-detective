import Link from "next/link";
import styles from "./home.module.css";

export default function Home() {
  return (
    <main className={styles.page}>
      <div className={styles.inner}>
        <p className={styles.kicker}>NASA Space Apps · Earth trends</p>
        <h1 className={styles.title}>Earth Trend Detective</h1>
        <p className={styles.tagline}>Is it the climate, or is it us?</p>
        <p className={styles.body}>
          Pick any place on Earth. We use NASA data to find what is changing there, check whether the change is real
          or just chance, and show how much of it the climate explains.
        </p>
        <ol className={styles.steps} aria-label="How it works">
          <li>
            <span aria-hidden="true">1</span> What&apos;s changing?
          </li>
          <li>
            <span aria-hidden="true">2</span> Is it real?
          </li>
          <li>
            <span aria-hidden="true">3</span> Is it the climate?
          </li>
        </ol>
        <div className={styles.actions}>
          <Link href="/explore" className={styles.primary}>
            Explore the map <span aria-hidden="true">→</span>
          </Link>
          <Link href="/story" className={styles.secondary}>
            Or follow three solved cases in story mode
          </Link>
        </div>
      </div>
    </main>
  );
}
