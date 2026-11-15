// Turns DrawSpecs into maplibre sources and layers, shared by the main map and the curtain map.
// Same registry + signature diffing as features/investigate/InvestigateMap.tsx.
import type { Map as MlMap } from 'maplibre-gl'
import { bboxPolygon, footprintData, imageCoordinates, specLayerIds, specSignature } from './map/draw'
import type { DrawSpec } from './map/draw'

/** Below the borders and names, so labels stay on top of every data layer. */
export const BEFORE = 'borders'
const INK = '#e9ecee'
const HALO = 'rgba(0,0,0,0.8)'

function drop(m: MlMap, id: string) {
  for (const layer of m.getStyle().layers ?? []) {
    if (layer.id === id || layer.id.startsWith(`${id}-`)) m.removeLayer(layer.id)
  }
  if (m.getSource(id)) m.removeSource(id)
}

function add(m: MlMap, spec: DrawSpec, anchor: string | undefined) {
  switch (spec.kind) {
    case 'raster':
      m.addSource(spec.id, { type: 'raster', tiles: spec.tiles, tileSize: 256, maxzoom: spec.maxzoom, attribution: spec.attribution })
      m.addLayer(
        { id: `${spec.id}-raster`, type: 'raster', source: spec.id, paint: { 'raster-resampling': 'linear', 'raster-fade-duration': 150 } },
        anchor,
      )
      return
    case 'image':
      m.addSource(spec.id, { type: 'image', url: spec.url, coordinates: imageCoordinates(spec.bbox) })
      m.addLayer({ id: `${spec.id}-image`, type: 'raster', source: spec.id, paint: { 'raster-resampling': 'linear' } }, anchor)
      return
    case 'footprint':
      m.addSource(spec.id, { type: 'geojson', data: footprintData(spec.bbox, spec.text) })
      m.addLayer(
        {
          id: `${spec.id}-edge`, type: 'line', source: spec.id, filter: ['==', ['geometry-type'], 'Polygon'],
          paint: { 'line-color': INK, 'line-width': 2.5, 'line-dasharray': [2, 1.5] },
        },
        anchor,
      )
      m.addLayer(
        {
          id: `${spec.id}-label`, type: 'symbol', source: spec.id, filter: ['==', ['geometry-type'], 'Point'],
          layout: {
            'text-field': ['get', 'text'], 'text-font': ['Noto Sans Regular'], 'text-size': 15,
            'text-anchor': 'bottom', 'text-offset': [0, -0.4], 'text-allow-overlap': true,
          },
          paint: { 'text-color': INK, 'text-halo-color': HALO, 'text-halo-width': 1.5 },
        },
        anchor,
      )
      return
    case 'outline':
      m.addSource(spec.id, { type: 'geojson', data: bboxPolygon(spec.bbox) })
      m.addLayer({ id: `${spec.id}-edge`, type: 'line', source: spec.id, paint: { 'line-color': INK, 'line-width': 3 } }, anchor)
  }
}

/** Brings the map in line with `specs` (bottom to top). `registry` maps spec id → signature of what is drawn. */
export function syncSpecs(m: MlMap, specs: DrawSpec[], registry: Map<string, string>) {
  const anchor = m.getLayer(BEFORE) ? BEFORE : undefined
  const wanted = new Set(specs.map((s) => s.id))
  for (const id of [...registry.keys()]) {
    if (!wanted.has(id)) {
      drop(m, id)
      registry.delete(id)
    }
  }
  for (const spec of specs) {
    const sig = specSignature(spec)
    if (registry.get(spec.id) !== sig) {
      drop(m, spec.id)
      add(m, spec, anchor)
      registry.set(spec.id, sig)
    }
    if (spec.kind === 'raster' || spec.kind === 'image') {
      for (const id of specLayerIds(spec)) if (m.getLayer(id)) m.setPaintProperty(id, 'raster-opacity', spec.opacity)
    }
  }
  // Re-stack in spec order: a layer rebuilt later must not jump above the ones meant to sit over it.
  for (const spec of specs) {
    for (const id of specLayerIds(spec)) if (m.getLayer(id)) m.moveLayer(id, anchor)
  }
}
