"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { FriendlyError, fetchSites, fetchSweep } from "./api";
import { fmtPlace } from "./format";
import ResultsPanel from "./ResultsPanel";
import { CloseIcon } from "../../lib/Icons";
import type { Place, Site, SweepResponse } from "./types";
import styles from "./explore.module.css";

const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => (
    <div className={styles.mapWrap}>
      <div className={styles.mapLoading}>Loading the map…</div>
    </div>
  ),
});

type Status =
  | { kind: "empty" }
  | { kind: "loading"; place: Place }
  | { kind: "error"; place: Place; message: string }
  | { kind: "done"; place: Place; result: SweepResponse };

const LOADING_STAGES = [
  "Getting monthly climate data from NASA POWER for this point…",
  "Removing the normal seasons so only the change is left…",
  "Testing each trend against the noise…",
];

function siteAt(sites: Site[], lat: number, lon: number): string | undefined {
  return sites.find(({ bbox: [w, s, e, n] }) => lon >= w && lon <= e && lat >= s && lat <= n)?.name;
}

function Loading({ place }: { place: Place }) {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setStage((s) => Math.min(s + 1, LOADING_STAGES.length - 1)), 2500);
    return () => clearInterval(id);
  }, []);
  return (
    <div className={styles.state} role="status" aria-live="polite">
      <div className={styles.spinner} aria-hidden="true" />
      <h2 className={styles.stateTitle}>Analyzing…</h2>
      <p>{LOADING_STAGES[stage]}</p>
      <p className={styles.note}>This can take up to a minute the first time for {place.name ?? "a new place"}.</p>
    </div>
  );
}

export default function ExploreView() {
  const [status, setStatus] = useState<Status>({ kind: "empty" });
  const [step, setStep] = useState(0);
  const [sites, setSites] = useState<Site[]>([]);
  const controller = useRef<AbortController | null>(null);
  const panel = useRef<HTMLElement>(null);

  useEffect(() => {
    const c = new AbortController();
    fetchSites(c.signal).then(setSites);
    return () => c.abort();
  }, []);

  const analyze = useCallback(
    async (lat: number, lon: number, name?: string) => {
      controller.current?.abort();
      const c = new AbortController();
      controller.current = c;
      const place: Place = { lat, lon, name: name ?? siteAt(sites, lat, lon) };
      setStatus({ kind: "loading", place });
      setStep(0);
      try {
        const result = await fetchSweep(lat, lon, c.signal);
        if (c.signal.aborted) return;
        setStatus({ kind: "done", place, result });
        // Phones: map is on top, so bring the answer into view once it is ready.
        if (window.matchMedia("(max-width: 899px)").matches) {
          requestAnimationFrame(() => panel.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
        }
      } catch (err) {
        if (c.signal.aborted) return;
        const message =
          err instanceof FriendlyError ? err.message : "Something unexpected happened. Try again in a moment.";
        setStatus({ kind: "error", place, message });
      }
    },
    [sites],
  );

  const clear = () => {
    controller.current?.abort();
    setStatus({ kind: "empty" });
  };

  const place = status.kind === "empty" ? null : status.place;

  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <Link href="/" className={styles.homeLink}>
          <span aria-hidden="true">←</span> Earth Trend Detective
        </Link>
        <Link href="/story/lake_mead" className={styles.topbarHint}>
          Solved cases <span aria-hidden="true">→</span>
        </Link>
      </header>
      <div className={styles.layout}>
        <MapView place={place} onPick={analyze} />
        <aside ref={panel} className={styles.panel} aria-label="Results">
          {place && (
            <div className={styles.placeBar}>
              <div>
                <p className={styles.placeName}>{place.name ?? "Selected point"}</p>
                <p className={styles.placeCoords}>{fmtPlace(place.lat, place.lon)}</p>
              </div>
              <button type="button" className={styles.iconButton} onClick={clear} aria-label="Clear this place">
                <CloseIcon />
              </button>
            </div>
          )}

          {status.kind === "empty" && (
            <div className={styles.state}>
              <h1 className={styles.stateTitle}>Pick a place to investigate</h1>
              <p>
                Click anywhere on the map. We&apos;ll check what is changing there, whether it is real, and whether it
                is the climate.
              </p>
              {sites.length > 0 && (
                <>
                  <p className={styles.note}>Or start with a known case:</p>
                  <div className={styles.chips}>
                    {sites.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        className={styles.chip}
                        onClick={() => analyze(s.point[1], s.point[0], s.name)}
                      >
                        {s.name}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {status.kind === "loading" && <Loading key={`${status.place.lat},${status.place.lon}`} place={status.place} />}

          {status.kind === "error" && (
            <div className={styles.state} role="alert">
              <h2 className={styles.stateTitle}>
                We couldn&apos;t analyse this place
              </h2>
              <p>{status.message}</p>
              <div className={styles.stepNav}>
                <button type="button" className={styles.ghost} onClick={clear}>
                  Pick another place
                </button>
                <button
                  type="button"
                  className={styles.primary}
                  onClick={() => analyze(status.place.lat, status.place.lon, status.place.name)}
                >
                  Try again
                </button>
              </div>
            </div>
          )}

          {status.kind === "done" && <ResultsPanel result={status.result} step={step} onStep={setStep} />}
        </aside>
      </div>
    </div>
  );
}
