import styles from "./theme.module.css";

export default function ExploreLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <div className={styles.theme}>{children}</div>;
}
