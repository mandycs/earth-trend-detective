'use client'

import { useEffect, useRef, useState } from 'react'
import type { GeoJSONSource, Map as MlMap, Marker } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { STYLE } from '../explore/mapStyle'
import styles from './investigate.module.css'

export type MapLayerSpec = {
  id: string
  visible: boolean
  opacity: number
} & (
  | { kind: 'footprint'; center: [number, number]; widthKm: number }
  | { kind: 'wms'; layer: string; year: number }
  | { kind: 'image'; url: string; bbox: [number, number, number, number] }
)

interface Props {
  place: { lat: number; lon: number } | null
  layers: MapLayerSpec[]
  onPick: (lat: number, lon: number) => void
  focusBbox: [number, number, number, number] | null
}

/** Below the borders and names, so labels stay on top of every data layer. */
const BEFORE = 'borders'

function circle(center: [number, number], radiusKm: number): GeoJSON.Feature<GeoJSON.Polygon> {
  const [lon, lat] = center
  const ring: [number, number][] = []
  for (let i = 0; i <= 96; i += 1) {
    const a = (i / 96) * Math.PI * 2
    const dLat = (radiusKm / 110.574) * Math.sin(a)
    const dLon = (radiusKm / (111.32 * Math.cos((lat * Math.PI) / 180))) * Math.cos(a)
    ring.push([lon + dLon, lat + dLat])
  }
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } }
}

function wmsTiles(layer: string, year: number): string {
  const params = new URLSearchParams({
    SERVICE: 'WMS',
    REQUEST: 'GetMap',
    VERSION: '1.3.0',
    LAYERS: layer,
    STYLES: '',
    CRS: 'EPSG:3857',
    WIDTH: '256',
    HEIGHT: '256',
    FORMAT: 'image/png',
    TRANSPARENT: 'TRUE',
    TIME: `${year}-01-01`,
  })
  return `https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?${params.toString()}&BBOX={bbox-epsg-3857}`
}

/** Removes every map layer and source this component added for one spec id. */
function drop(m: MlMap, prefix: string) {
  for (const layer of m.getStyle().layers ?? []) {
    if (layer.id.startsWith(prefix)) m.removeLayer(layer.id)
  }
  for (const source of Object.keys(m.getStyle().sources ?? {})) {
    if (source.startsWith(prefix)) m.removeSource(source)
  }
}

export default function InvestigateMap({ place, layers, onPick, focusBbox }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<MlMap | null>(null)
  const marker = useRef<Marker | null>(null)
  const onPickRef = useRef(onPick)
  const added = useRef(new Map<string, string>())
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    onPickRef.current = onPick
  }, [onPick])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const maplibregl = (await import('maplibre-gl')).default
      if (cancelled || !container.current) return
      const m = new maplibregl.Map({
        container: container.current,
        style: STYLE,
        center: [-20, 28],
        zoom: 1.6,
        maxZoom: 10,
        attributionControl: { compact: true },
      })
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
      m.getCanvas().style.cursor = 'crosshair'
      m.on('click', (e) => onPickRef.current(e.lngLat.lat, e.lngLat.lng))
      m.on('load', () => !cancelled && setReady(true))
      // Instrument layout: a reading column covers the left of the map on wide screens.
      const pad = () => m.setPadding({ left: window.innerWidth >= 1000 ? Math.round(window.innerWidth * 0.4) : 0, top: 0, right: 0, bottom: 0 })
      pad()
      window.addEventListener('resize', pad)
      m.on('error', (e) => {
        if (!m.isStyleLoaded() && String(e.error?.message ?? '').toLowerCase().includes('style')) setFailed(true)
      })
      marker.current = new maplibregl.Marker({ color: '#e9ecee' })
      map.current = m
    })().catch(() => setFailed(true))
    const registry = added.current
    return () => {
      cancelled = true
      map.current?.remove()
      map.current = null
      registry.clear()
      setReady(false)
    }
  }, [])

  // Marker and camera follow the place.
  useEffect(() => {
    const m = map.current
    if (!m || !ready || !marker.current) return
    if (!place) {
      marker.current.remove()
      return
    }
    marker.current.setLngLat([place.lon, place.lat]).addTo(m)
    if (!focusBbox) m.flyTo({ center: [place.lon, place.lat], zoom: Math.max(m.getZoom(), 6.5), speed: 1.4 })
  }, [place, ready, focusBbox])

  useEffect(() => {
    const m = map.current
    if (!m || !ready || !focusBbox) return
    const [w, s, e, n] = focusBbox
    m.fitBounds(
      [
        [w, s],
        [e, n],
      ],
      { padding: 60, maxZoom: 9.5, duration: 1600 },
    )
  }, [focusBbox, ready])

  // Keep the data layers in step with the specs.
  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    const anchor = m.getLayer(BEFORE) ? BEFORE : undefined
    const wanted = new Set(layers.map((l) => l.id))
    for (const [id] of added.current) {
      if (!wanted.has(id)) {
        drop(m, `inv-${id}`)
        added.current.delete(id)
      }
    }
    for (const spec of layers) {
      const prefix = `inv-${spec.id}`
      const signature =
        spec.kind === 'wms' ? `wms:${spec.layer}:${spec.year}` : spec.kind === 'image' ? `img:${spec.url}` : `fp:${spec.center.join(',')}:${spec.widthKm}`
      if (added.current.get(spec.id) !== signature) {
        drop(m, prefix)
        if (spec.kind === 'footprint') {
          m.addSource(prefix, { type: 'geojson', data: circle(spec.center, spec.widthKm / 2) })
          m.addLayer({ id: `${prefix}-fill`, type: 'fill', source: prefix, paint: { 'fill-color': '#e9ecee', 'fill-opacity': 0.1 } }, anchor)
          m.addLayer(
            { id: `${prefix}-edge`, type: 'line', source: prefix, paint: { 'line-color': '#e9ecee', 'line-width': 3, 'line-dasharray': [2, 1.5] } },
            anchor,
          )
        } else if (spec.kind === 'wms') {
          m.addSource(prefix, { type: 'raster', tiles: [wmsTiles(spec.layer, spec.year)], tileSize: 256, attribution: 'MODIS land cover: NASA GIBS' })
          m.addLayer({ id: `${prefix}-raster`, type: 'raster', source: prefix, paint: { 'raster-fade-duration': 150 } }, anchor)
        } else {
          const [w, s, e, n] = spec.bbox
          m.addSource(prefix, {
            type: 'image',
            url: spec.url,
            coordinates: [
              [w, n],
              [e, n],
              [e, s],
              [w, s],
            ],
          })
          m.addLayer({ id: `${prefix}-image`, type: 'raster', source: prefix }, anchor)
        }
        added.current.set(spec.id, signature)
      }
      const visibility = spec.visible ? 'visible' : 'none'
      for (const layer of m.getStyle().layers ?? []) {
        if (!layer.id.startsWith(prefix)) continue
        m.setLayoutProperty(layer.id, 'visibility', visibility)
        if (layer.type === 'raster') m.setPaintProperty(layer.id, 'raster-opacity', spec.opacity)
        if (layer.type === 'fill') m.setPaintProperty(layer.id, 'fill-opacity', 0.2 * spec.opacity)
        if (layer.type === 'line') m.setPaintProperty(layer.id, 'line-opacity', spec.opacity)
      }
      if (spec.kind === 'footprint') {
        const source = m.getSource(prefix) as GeoJSONSource | undefined
        source?.setData(circle(spec.center, spec.widthKm / 2))
      }
    }
  }, [layers, ready])

  return (
    <div className={styles.mapWrap}>
      <div
        ref={container}
        className={styles.map}
        role="application"
        aria-label="World map. Click a place to set where to investigate."
      />
      {!place && !failed ? <p className={styles.mapHint}>Click anywhere on Earth to set the place</p> : null}
      {failed ? (
        <p className={styles.mapError} role="alert">
          The map could not load. Check your connection and reload. You can still investigate the solved cases from
          the panel.
        </p>
      ) : null}
    </div>
  )
}
