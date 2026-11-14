import type { StyleSpecification } from "maplibre-gl";

/**
 * NASA Blue Marble (via GIBS, public domain, no key) as the ground, with
 * country borders and place names from OpenFreeMap vector tiles on top.
 */
export const STYLE: StyleSpecification = {
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
