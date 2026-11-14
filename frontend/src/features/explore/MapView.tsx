"use client";

import { useEffect, useRef, useState } from "react";
import type { Map as MlMap, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Place } from "./types";
import styles from "./explore.module.css";

import { STYLE } from "./mapStyle";

interface Props {
  place: Place | null;
  onPick: (lat: number, lon: number) => void;
}

export default function MapView({ place, onPick }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const marker = useRef<Marker | null>(null);
  const onPickRef = useRef(onPick);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    onPickRef.current = onPick;
  }, [onPick]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const maplibregl = (await import("maplibre-gl")).default;
      if (cancelled || !container.current) return;
      const m = new maplibregl.Map({
        container: container.current,
        style: STYLE,
        center: [-20, 28],
        zoom: 1.6,
        maxZoom: 10,
        attributionControl: { compact: true },
        cooperativeGestures: false,
      });
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      // Instrument layout: a reading column covers the left of the map on wide screens.
      const pad = () => m.setPadding({ left: window.innerWidth >= 900 ? Math.round(window.innerWidth * 0.4) : 0, top: 0, right: 0, bottom: 0 });
      pad();
      window.addEventListener("resize", pad);
      m.getCanvas().style.cursor = "crosshair";
      m.on("click", (e) => onPickRef.current(e.lngLat.lat, e.lngLat.lng));
      m.on("error", (e) => {
        // Only a failed style means no map at all; a missing tile is harmless.
        if (!m.isStyleLoaded() && String(e.error?.message ?? "").toLowerCase().includes("style")) setFailed(true);
      });
      marker.current = new maplibregl.Marker({ color: "#e9ecee" });
      map.current = m;
      setReady(true);
    })().catch(() => setFailed(true));
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      setReady(false);
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m || !marker.current) return;
    if (!place) {
      marker.current.remove();
      return;
    }
    marker.current.setLngLat([place.lon, place.lat]).addTo(m);
    if (!m.getBounds().contains([place.lon, place.lat]) || m.getZoom() < 3) {
      m.flyTo({ center: [place.lon, place.lat], zoom: Math.max(m.getZoom(), 6), speed: 1.6 });
    }
  }, [place, ready]);

  return (
    <div className={styles.mapWrap}>
      <div
        ref={container}
        className={styles.map}
        role="application"
        aria-label="World map. Click a place to investigate it, or use the example buttons in the panel."
      />
      {!place && !failed && <p className={styles.mapHint}>Click anywhere on Earth to investigate it</p>}
      {failed && (
        <p className={styles.mapError} role="alert">
          The map could not load. Check your connection and reload the page. You can still try the example places in
          the panel.
        </p>
      )}
    </div>
  );
}
