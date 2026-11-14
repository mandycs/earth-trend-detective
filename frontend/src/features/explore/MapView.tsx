"use client";

import { useEffect, useRef, useState } from "react";
import type { Map as MlMap, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Place } from "./types";
import styles from "./explore.module.css";

import type { StyleSpecification } from "maplibre-gl";

/**
 * NASA Blue Marble (via GIBS, public domain, no key) as the ground, with
 * country borders and place names from OpenFreeMap vector tiles on top.
 */
const STYLE: StyleSpecification = {
  version: 8,
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sources: {
    earth: {
      type: "raster",
      tiles: [
        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
      ],
      tileSize: 256,
      maxzoom: 8,
      attribution: "Blue Marble: NASA Earth Observatory via GIBS",
    },
    names: { type: "vector", url: "https://tiles.openfreemap.org/planet" },
  },
  layers: [
    { id: "earth", type: "raster", source: "earth", paint: { "raster-brightness-max": 0.92, "raster-fade-duration": 200 } },
    {
      id: "borders",
      type: "line",
      source: "names",
      "source-layer": "boundary",
      filter: ["all", ["==", ["get", "admin_level"], 2], ["!=", ["get", "maritime"], 1]],
      paint: { "line-color": "rgba(238,240,234,0.45)", "line-width": 1 },
    },
    {
      id: "countries",
      type: "symbol",
      source: "names",
      "source-layer": "place",
      maxzoom: 6,
      filter: ["==", ["get", "class"], "country"],
      layout: {
        "text-field": ["coalesce", ["get", "name:en"], ["get", "name:latin"], ["get", "name"]],
        "text-font": ["Noto Sans Regular"],
        "text-size": 14,
        "text-max-width": 8,
      },
      paint: { "text-color": "#eef0ea", "text-halo-color": "rgba(0,0,0,0.75)", "text-halo-width": 1.5 },
    },
    {
      id: "cities",
      type: "symbol",
      source: "names",
      "source-layer": "place",
      minzoom: 4,
      filter: ["in", ["get", "class"], ["literal", ["city", "town"]]],
      layout: {
        "text-field": ["coalesce", ["get", "name:en"], ["get", "name:latin"], ["get", "name"]],
        "text-font": ["Noto Sans Regular"],
        "text-size": 13,
      },
      paint: { "text-color": "#ffffff", "text-halo-color": "rgba(0,0,0,0.8)", "text-halo-width": 1.5 },
    },
  ],
};

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
      m.getCanvas().style.cursor = "crosshair";
      m.on("click", (e) => onPickRef.current(e.lngLat.lat, e.lngLat.lng));
      m.on("error", (e) => {
        // Only a failed style means no map at all; a missing tile is harmless.
        if (!m.isStyleLoaded() && String(e.error?.message ?? "").toLowerCase().includes("style")) setFailed(true);
      });
      marker.current = new maplibregl.Marker({ color: "#ffd23f" });
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
