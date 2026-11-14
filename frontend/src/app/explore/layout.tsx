import type { Viewport } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import styles from "./theme.module.css";

const sans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-mono", subsets: ["latin"] });
const serif = Instrument_Serif({ variable: "--font-serif", subsets: ["latin"], weight: "400" });

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#f4f1ea" };

export default function ExploreLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className={`${styles.theme} ${sans.variable} ${mono.variable} ${serif.variable}`}>{children}</div>
  );
}
