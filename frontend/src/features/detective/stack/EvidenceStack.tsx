'use client'

// The exploded evidence stack (Task 17): the current turn's layers as opaque slabs over the relief (or the flat
// picture) of the same box. Separation is the point: this view is not the map's "one coloured layer at a time".
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { MutableRefObject } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import type { ThreeEvent } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { loadHeights, sampleHeight } from '../../../story/heights'
import type { HeightGrid } from '../../../story/heights'
import { Stamp } from '../../../lib/Stamp'
import { STATUS_WORDS } from '../board'
import type { Bbox } from '../events'
import type { Slab, StackModel } from './stackModel'
import { atRest, collapseReport, springStep } from './motion'
import type { CollapseState, SlabMotion } from './motion'
import styles from './stack.module.css'

export interface EvidenceStackProps {
  model: StackModel
  exploded: boolean
  onPick: (key: string) => void
  /** Esc or "Back to the map". */
  onClose: () => void
  /** The slabs are back on the ground after `exploded` went false (at once with reduced motion). */
  onCollapsed: () => void
  reducedMotion: boolean
}

/** Shown on screen with the relief (DESIGN: the vertical exaggeration is shown). */
export const RELIEF_EXAGGERATION = 3
const SLAB_T = 0.014
const CELL_T = 0.05
const GAP = 0.15
const LIFT = 0.1
const SIDE = '#262b30'
const EDGE = '#3a4146'
const EDGE_ON = '#e9ecee'
const CELL_TOP = '#6f787f'
const WIDE = '(min-width: 900px)'

// ---- geometry helpers (drawing only: nothing here is printed) ----

/** Width (east-west) and depth (north-south) of the box in metres. */
function boxMetres(b: Bbox): [number, number] {
  const [w, s, e, n] = b
  const mid = (((s + n) / 2) * Math.PI) / 180
  return [Math.max(1, Math.abs(e - w) * 111_320 * Math.cos(mid)), Math.max(1, Math.abs(n - s) * 110_540)]
}

function boxAspect(b: Bbox): number {
  const [wm, dm] = boxMetres(b)
  return Math.min(2.2, Math.max(0.45, dm / wm))
}

/** A lon/lat rectangle in the stack's world (x across, z north to south), clipped to the box. */
function rectIn(box: Bbox, r: Bbox, depth: number): { x0: number; x1: number; z0: number; z1: number } {
  const [w, s, e, n] = box
  const cx = (lon: number) => Math.min(0.5, Math.max(-0.5, (lon - w) / (e - w) - 0.5))
  const cz = (lat: number) => Math.min(0.5, Math.max(-0.5, (n - lat) / (n - s) - 0.5)) * depth
  return { x0: cx(r[0]), x1: cx(r[2]), z0: cz(r[3]), z1: cz(r[1]) }
}

export type PictureStatus = 'loading' | 'ok' | 'failed' | 'empty'

/** True when every pixel of the picture is fully transparent (a "no data" answer, not a picture). */
function isBlank(image: CanvasImageSource): boolean {
  try {
    const c = document.createElement('canvas')
    c.width = 32
    c.height = 32
    const ctx = c.getContext('2d', { willReadFrequently: true })
    if (!ctx) return false
    ctx.drawImage(image, 0, 0, 32, 32)
    const d = ctx.getImageData(0, 0, 32, 32).data
    for (let i = 3; i < d.length; i += 4) if (d[i] !== 0) return false
    return true
  } catch {
    return false
  }
}

function useTexture(url: string | null): { tex: THREE.Texture | null; status: PictureStatus } {
  const [state, setState] = useState<{ tex: THREE.Texture | null; status: PictureStatus }>({ tex: null, status: 'loading' })
  useEffect(() => {
    if (!url) return
    let live = true
    let loaded: THREE.Texture | null = null
    const loader = new THREE.TextureLoader()
    loader.setCrossOrigin('anonymous')
    loader.load(
      url,
      (t) => {
        if (!live) {
          t.dispose()
          return
        }
        if (isBlank(t.image as CanvasImageSource)) {
          t.dispose()
          setState({ tex: null, status: 'empty' })
          return
        }
        t.colorSpace = THREE.SRGBColorSpace
        t.anisotropy = 4
        loaded = t
        setState({ tex: t, status: 'ok' })
      },
      undefined,
      () => live && setState({ tex: null, status: 'failed' }),
    )
    return () => {
      live = false
      loaded?.dispose()
    }
  }, [url])
  return state
}

// ---- the base ----

function ReliefMesh({ grid, picture, metres, depth }: { grid: HeightGrid; picture: THREE.Texture | null; metres: number; depth: number }) {
  const geo = useMemo(() => {
    const segX = Math.min(220, grid.width - 1)
    const segZ = Math.max(8, Math.min(grid.height - 1, Math.round(segX * depth)))
    const g = new THREE.PlaneGeometry(1, depth, segX, segZ)
    g.rotateX(-Math.PI / 2)
    const pos = g.attributes.position
    for (let i = 0; i < pos.count; i += 1) {
      const u = pos.getX(i) + 0.5
      const v = pos.getZ(i) / depth + 0.5
      const h = sampleHeight(grid, u, v)
      pos.setY(i, ((h - grid.min) / metres) * RELIEF_EXAGGERATION)
    }
    g.computeVertexNormals()
    return g
  }, [grid, metres, depth])
  useEffect(() => () => geo.dispose(), [geo])
  return (
    <mesh geometry={geo}>
      <meshStandardMaterial key={picture ? picture.uuid : 'none'} map={picture ?? undefined} color={picture ? '#ffffff' : '#4a4238'} roughness={1} metalness={0} />
    </mesh>
  )
}

function Base({ model, depth, onPeak, onFailed }: { model: StackModel; depth: number; onPeak: (p: number) => void; onFailed: () => void }) {
  const base = model.base
  const { tex } = useTexture(base?.picture?.url ?? null)
  const [grid, setGrid] = useState<HeightGrid | null>(null)
  const hm = base?.heightmap ?? null
  // Keyed on primitives: a fresh model object with the same heightmap does not reload it.
  const hmUrl = hm?.url ?? null
  const hmRgb = hm?.encoding === 'terrain-rgb'
  const lo = hm?.rangeM?.[0] ?? null
  const hi = hm?.rangeM?.[1] ?? null
  useEffect(() => {
    if (!hmUrl) return
    let live = true
    const urls = hmRgb ? { rgb: hmUrl, grey: hmUrl } : { grey: hmUrl }
    loadHeights(urls, lo != null && hi != null ? [lo, hi] : undefined)
      .then((g) => live && setGrid(g))
      .catch(() => live && onFailed())
    return () => {
      live = false
    }
  }, [hmUrl, hmRgb, lo, hi, onFailed])
  const metres = model.bbox ? boxMetres(model.bbox)[0] : 1
  const peak = grid ? ((grid.max - grid.min) / metres) * RELIEF_EXAGGERATION : 0
  useEffect(() => onPeak(peak), [peak, onPeak])
  return (
    <group>
      {/* the plinth: a dark block under the ground, like a museum relief model */}
      <mesh position={[0, -0.03, 0]}>
        <boxGeometry args={[1, 0.06, depth]} />
        <meshBasicMaterial color={SIDE} />
      </mesh>
      {grid ? (
        <ReliefMesh grid={grid} picture={tex} metres={metres} depth={depth} />
      ) : (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.0005, 0]}>
          <planeGeometry args={[1, depth]} />
          <meshBasicMaterial key={tex ? tex.uuid : 'none'} map={tex ?? undefined} color={tex ? '#ffffff' : '#2b2f33'} toneMapped={false} />
        </mesh>
      )}
    </group>
  )
}

// ---- slabs ----

function SlabMesh({
  slab, box, depth, groupRef, active, onPick, onHover, onTexture,
}: {
  slab: Slab; box: Bbox; depth: number; groupRef: (g: THREE.Group | null) => void; active: boolean
  onPick: (key: string) => void; onHover: (key: string | null) => void; onTexture: (key: string, status: PictureStatus) => void
}) {
  const url = slab.texture.kind === 'cell' ? null : slab.texture.url
  // An empty or failed picture leaves a neutral slab: never a colour that was not in the data.
  const { tex, status } = useTexture(url)
  useEffect(() => {
    if (url) onTexture(slab.key, status)
  }, [status, url, slab.key, onTexture])
  const edgeColour = active ? EDGE_ON : EDGE
  const cellBox = slab.texture.kind === 'cell' ? slab.texture.bbox : null
  const cellKm = slab.texture.kind === 'cell' ? slab.texture.cellKm : null
  const shapes = useMemo(() => {
    if (!cellBox) return { edges: new THREE.EdgesGeometry(new THREE.BoxGeometry(1, SLAB_T, depth)), lines: null, r: null }
    const r = rectIn(box, cellBox, depth)
    const w = Math.max(0.01, r.x1 - r.x0)
    const d = Math.max(0.01, r.z1 - r.z0)
    return { edges: new THREE.EdgesGeometry(new THREE.BoxGeometry(w, CELL_T, d)), lines: cellGrid(box, cellBox, cellKm, depth), r }
  }, [box, cellBox, cellKm, depth])
  useEffect(
    () => () => {
      shapes.edges.dispose()
      shapes.lines?.dispose()
    },
    [shapes],
  )
  const lines = shapes.lines
  const click = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation()
    if (e.delta > 6) return // a drag to turn the stack, not a pick
    onPick(slab.key)
  }
  const hover = {
    onPointerOver: (e: ThreeEvent<PointerEvent>) => {
      e.stopPropagation()
      onHover(slab.key)
      document.body.style.cursor = 'pointer'
    },
    onPointerOut: () => {
      onHover(null)
      document.body.style.cursor = ''
    },
  }

  if (slab.texture.kind === 'cell') {
    const r = shapes.r ?? rectIn(box, slab.texture.bbox, depth)
    const w = Math.max(0.01, r.x1 - r.x0)
    const d = Math.max(0.01, r.z1 - r.z0)
    const cx = (r.x0 + r.x1) / 2
    const cz = (r.z0 + r.z1) / 2
    return (
      <group ref={groupRef}>
        {/* the plate: the whole box, dark, with the outline of neighbouring cells of the same size */}
        <mesh onClick={click} {...hover}>
          <boxGeometry args={[1, SLAB_T * 0.6, depth]} />
          <meshBasicMaterial color={'#1c2024'} />
        </mesh>
        {lines && (
          <lineSegments geometry={lines} position={[0, SLAB_T * 0.31, 0]}>
            <lineBasicMaterial color={EDGE} />
          </lineSegments>
        )}
        {/* the cell: one coarse block, one value for everything under it */}
        <mesh position={[cx, CELL_T / 2, cz]} onClick={click} {...hover}>
          <boxGeometry args={[w, CELL_T, d]} />
          <meshBasicMaterial color={CELL_TOP} />
        </mesh>
        <lineSegments position={[cx, CELL_T / 2, cz]} geometry={shapes.edges}>
          <lineBasicMaterial color={edgeColour} />
        </lineSegments>
      </group>
    )
  }

  return (
    <group ref={groupRef}>
      <mesh onClick={click} {...hover}>
        <boxGeometry args={[1, SLAB_T, depth]} />
        <meshBasicMaterial attach="material-0" color={SIDE} />
        <meshBasicMaterial attach="material-1" color={SIDE} />
        <meshBasicMaterial
          key={tex ? tex.uuid : 'none'}
          attach="material-2"
          map={tex ?? undefined}
          color={tex ? '#ffffff' : '#2b2f33'}
          toneMapped={false}
        />
        <meshBasicMaterial attach="material-3" color={SIDE} />
        <meshBasicMaterial attach="material-4" color={SIDE} />
        <meshBasicMaterial attach="material-5" color={SIDE} />
      </mesh>
      <lineSegments geometry={shapes.edges}>
        <lineBasicMaterial color={edgeColour} />
      </lineSegments>
    </group>
  )
}

/** Grid lines one cell apart, aligned on the footprint, across the box (only when cells are smaller than it). */
function cellGrid(box: Bbox, cell: Bbox, cellKm: number | null, depth: number): THREE.BufferGeometry | null {
  if (!cellKm || cellKm <= 0) return null
  const [wm, dm] = boxMetres(box)
  const stepX = (cellKm * 1000) / wm
  const stepZ = ((cellKm * 1000) / dm) * depth
  if (stepX >= 1 && stepZ >= depth) return null
  if (1 / stepX > 40 || depth / stepZ > 40) return null
  const r = rectIn(box, cell, depth)
  const pts: number[] = []
  const xs: number[] = []
  for (let x = r.x0; x >= -0.5; x -= stepX) xs.push(x)
  for (let x = r.x0 + stepX; x <= 0.5; x += stepX) xs.push(x)
  const zs: number[] = []
  for (let z = r.z0; z >= -depth / 2; z -= stepZ) zs.push(z)
  for (let z = r.z0 + stepZ; z <= depth / 2; z += stepZ) zs.push(z)
  for (const x of xs) pts.push(x, 0, -depth / 2, x, 0, depth / 2)
  for (const z of zs) pts.push(-0.5, 0, z, 0.5, 0, z)
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
  return g
}

// ---- motion, camera and the label anchors ----

type Anchor = { x: number; y: number }

function Rig({
  slabs, groups, exploded, reduced, groundY, onCollapsed, anchors, onAnchors, follow, stackTop, depth,
}: {
  slabs: Slab[]; groups: MutableRefObject<Map<string, THREE.Group>>; exploded: boolean; reduced: boolean
  groundY: number; onCollapsed: () => void; anchors: MutableRefObject<Map<string, Anchor>>
  /** Called when a card anchor moved on screen (slab motion, the visitor turning the stack, a resize). */
  onAnchors: () => void
  follow: boolean; stackTop: number; depth: number
}) {
  const { camera, size } = useThree()
  // Keyed by slab key: a slab added or removed by a late event never shifts another slab's state.
  const motion = useRef(new Map<string, SlabMotion>())
  const collapse = useRef<CollapseState>({ wasExploded: false, reported: false })
  const since = useRef(0)
  const done = useRef(onCollapsed)
  const notify = useRef(onAnchors)
  useEffect(() => {
    done.current = onCollapsed
    notify.current = onAnchors
  }, [onCollapsed, onAnchors])
  useEffect(() => {
    since.current = 0
  }, [exploded])

  // Frame the stack; on a wide screen it sits left of the label column.
  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera
    const far = size.width < 700 || size.width < size.height ? 2.15 : 1.9
    cam.position.set(-0.95 * far, 0.55 * far + stackTop * 0.5, 1.15 * far)
    cam.lookAt(0, stackTop * 0.45, 0)
    if (follow) cam.setViewOffset(size.width, size.height, size.width * 0.17, 0, size.width, size.height)
    else cam.clearViewOffset()
    cam.updateProjectionMatrix()
  }, [camera, size, follow, stackTop])

  const v3 = useMemo(() => new THREE.Vector3(), [])
  useFrame((_, dt) => {
    const step = Math.min(dt, 1 / 30)
    since.current += step
    let moving = false
    let anchorsMoved = false
    const live = new Set<string>()
    slabs.forEach((s, i) => {
      live.add(s.key)
      const target = exploded ? groundY + LIFT + (s.height - 1) * GAP : groundY + i * 0.0004
      let m = motion.current.get(s.key) ?? { y: groundY, v: 0 }
      if (reduced) m = { y: target, v: 0 }
      else {
        // Stagger: the top slab leaves first when exploding, lands last when collapsing.
        const delay = (exploded ? i : slabs.length - 1 - i) * 0.07
        if (since.current >= delay) m = springStep(m, target, step)
        if (!atRest(m, target)) moving = true
      }
      motion.current.set(s.key, m)
      const g = groups.current.get(s.key)
      if (g) g.position.y = m.y
      // Card anchor: the slab's corner nearest the label column (the camera looks from the south-west), in pixels.
      v3.set(0.5, m.y, depth / 2).project(camera)
      const a = { x: ((v3.x + 1) / 2) * size.width, y: ((1 - v3.y) / 2) * size.height }
      const prev = anchors.current.get(s.key)
      if (!prev || Math.abs(prev.x - a.x) > 0.5 || Math.abs(prev.y - a.y) > 0.5) {
        anchors.current.set(s.key, a)
        anchorsMoved = true
      }
    })
    for (const k of [...motion.current.keys()]) if (!live.has(k)) motion.current.delete(k)
    if (anchorsMoved) notify.current()
    const r = collapseReport(collapse.current, exploded, moving)
    collapse.current = r.state
    if (r.report) done.current()
  })
  return null
}

// ---- label cards ----

function whenText(s: Slab): string | null {
  if (s.year != null) return `Year drawn: ${s.year}`
  if (s.period) return s.period[0] === s.period[1] ? `Year: ${s.period[0]}` : `Period: ${s.period[0]}–${s.period[1]}`
  return null
}

function SlabCard({
  slab, picture, active, onPick, onHover, cardRef,
}: {
  slab: Slab; picture: PictureStatus | undefined; active: boolean; onPick: (key: string) => void; onHover: (key: string | null) => void
  cardRef: (el: HTMLButtonElement | null) => void
}) {
  const when = whenText(slab)
  const st = slab.stamp ? (STATUS_WORDS[slab.stamp.status] ?? STATUS_WORDS.open) : null
  const cell = slab.texture.kind === 'cell'
  const stops = slab.legend?.stops ?? []
  return (
    <button
      type="button"
      ref={cardRef}
      className={`${styles.card} ${active ? styles.cardOn : ''}`}
      onClick={() => onPick(slab.key)}
      onMouseEnter={() => onHover(slab.key)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(slab.key)}
      onBlur={() => onHover(null)}
      aria-label={`${slab.title}${when ? `, ${when}` : ''}. Show it on the map.`}
    >
      <span className={styles.cardTitle}>{slab.title}</span>
      <span className={styles.cardLine}>
        {slab.source}
        {/* each figure once: a cell's label often already carries its size */}
        {slab.resolution && !slab.source.includes(slab.resolution) ? <> · {cell ? `cell ${slab.resolution}` : slab.resolution}</> : null}
      </span>
      {when && <span className={styles.cardLine}>{when}</span>}
      {cell && <span className={styles.cardMuted}>One value covers this whole cell; the outline is approximate.</span>}
      {stops.length >= 2 && (
        <span
          className={styles.cardRamp}
          role="img"
          aria-label={`Colour ramp${slab.legend?.unit ? ` for ${slab.legend.unit}` : ''}`}
          style={{ background: `linear-gradient(to right, ${stops.join(', ')})` }}
        />
      )}
      {slab.verdict && (
        <span className={styles.cardVerdict}>
          {slab.verdict.label && <span>{slab.verdict.label}:</span>}
          <Stamp verdict={slab.verdict.verdict} direction={slab.verdict.direction} />
        </span>
      )}
      {st && slab.stamp && (
        <span className={styles.cardStamp}>
          <span className={styles.cardStampMark}>
            <span aria-hidden="true">{st.icon}</span> {st.text}
          </span>
          <span>{slab.stamp.label}</span>
        </span>
      )}
      {picture === 'failed' && <span className={styles.cardMuted}>Picture unavailable: it did not load.</span>}
      {picture === 'empty' && <span className={styles.cardMuted}>Picture unavailable: no data for this date.</span>}
    </button>
  )
}

function BaseCard({ model, reliefFailed }: { model: StackModel; reliefFailed: boolean }) {
  const b = model.base
  if (!b) return null
  const relief = b.kind === 'relief' && !reliefFailed
  return (
    <div className={styles.baseCard} data-base="">
      <span className={styles.cardTitle}>{relief ? `Ground: ${b.title}` : b.kind === 'relief' ? 'Ground: flat (the relief did not load)' : b.title}</span>
      {relief && <span className={styles.cardLine}>{b.source} · heights ×{RELIEF_EXAGGERATION}</span>}
      {b.picture && (
        <span className={styles.cardLine}>
          Picture: {b.picture.title}
          {b.kind === 'flat' && b.picture.resolution ? ` · ${b.picture.resolution}` : ''}
        </span>
      )}
      {b.picture && b.picture.source !== b.source && <span className={styles.cardMuted}>{b.picture.source}</span>}
    </div>
  )
}

/** Spreads the cards down the column so they never overlap, each as close as it can be to its slab. */
function layoutCards(want: number[], heights: number[], top: number, bottom: number, gap: number): number[] {
  const order = want.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y)
  const out = new Array<number>(want.length).fill(0)
  let cursor = top
  for (const { y, i } of order) {
    const at = Math.max(cursor, y - heights[i] / 2)
    out[i] = at
    cursor = at + heights[i] + gap
  }
  const over = cursor - gap - bottom
  if (over > 0) for (let i = 0; i < out.length; i += 1) out[i] = Math.max(top, out[i] - over)
  return out
}

export default function EvidenceStack({ model, exploded, onPick, onClose, onCollapsed, reducedMotion }: EvidenceStackProps) {
  const box = model.bbox
  const depth = box ? boxAspect(box) : 1
  const [peak, setPeak] = useState(0)
  const [active, setActive] = useState<string | null>(null)
  const [pictures, setPictures] = useState<Record<string, PictureStatus>>({})
  const [wide, setWide] = useState(false)
  const [reliefFailed, setReliefFailed] = useState(false)
  const onReliefFailed = useMemo(() => () => setReliefFailed(true), [])
  // All keyed by slab key, never by position.
  const groups = useRef(new Map<string, THREE.Group>())
  const anchors = useRef(new Map<string, Anchor>())
  const cards = useRef(new Map<string, HTMLButtonElement>())
  const lines = useRef(new Map<string, SVGLineElement>())
  const canvasBox = useRef<HTMLDivElement>(null)
  const column = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const slabs = model.slabs
  const groundY = peak + SLAB_T

  useEffect(() => {
    const q = window.matchMedia(WIDE)
    setWide(q.matches)
    const on = (e: MediaQueryListEvent) => setWide(e.matches)
    q.addEventListener('change', on)
    return () => q.removeEventListener('change', on)
  }, [])

  useEffect(() => {
    closeRef.current?.focus({ preventScroll: true })
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.cursor = ''
    }
  }, [onClose])

  // Wide screens: each card follows its slab, joined by a leader line; when the cards do not fit the column
  // height, the column scrolls as a plain list instead. Narrow screens: a plain list under the stack.
  // Laid out only when something moved (an anchor, a resize, a card's content), never on an idle frame.
  const layoutRaf = useRef(0)
  const layout = useCallback(() => {
    const col = column.current
    const cv = canvasBox.current
    if (!col || !cv) return
    const plain = () => {
      for (const c of cards.current.values()) c.style.transform = ''
      for (const l of lines.current.values()) l.style.display = 'none'
    }
    if (!wide) {
      delete col.dataset.scroll
      plain()
      return
    }
    const heights = slabs.map((s) => cards.current.get(s.key)?.offsetHeight ?? 0)
    const baseH = (col.querySelector('[data-base]') as HTMLElement | null)?.offsetHeight ?? 0
    const room = col.clientHeight - baseH - 16
    const need = heights.reduce((a, h) => a + h, 0) + 10 * Math.max(0, slabs.length - 1)
    if (need > room) {
      col.dataset.scroll = ''
      plain()
      return
    }
    delete col.dataset.scroll
    const colRect = col.getBoundingClientRect()
    const cvRect = cv.getBoundingClientRect()
    const want = slabs.map((s) => (anchors.current.get(s.key)?.y ?? 0) + cvRect.top - colRect.top)
    const ys = layoutCards(want, heights, 0, room, 10)
    slabs.forEach((s, i) => {
      const c = cards.current.get(s.key)
      if (c) c.style.transform = `translateY(${ys[i]}px)`
      const l = lines.current.get(s.key)
      const a = anchors.current.get(s.key)
      if (l && a) {
        l.style.display = ''
        l.setAttribute('x1', String(a.x))
        l.setAttribute('y1', String(a.y))
        l.setAttribute('x2', String(colRect.left - cvRect.left))
        l.setAttribute('y2', String(ys[i] + heights[i] / 2 + colRect.top - cvRect.top))
      }
    })
  }, [wide, slabs])
  const scheduleLayout = useCallback(() => {
    if (layoutRaf.current) return
    layoutRaf.current = requestAnimationFrame(() => {
      layoutRaf.current = 0
      layout()
    })
  }, [layout])
  useEffect(() => {
    scheduleLayout()
    const ro = new ResizeObserver(scheduleLayout)
    if (column.current) ro.observe(column.current)
    return () => {
      ro.disconnect()
      cancelAnimationFrame(layoutRaf.current)
      layoutRaf.current = 0
    }
  }, [scheduleLayout, pictures, reliefFailed])

  const onTexture = useMemo(
    () => (key: string, status: PictureStatus) => setPictures((f) => (f[key] === status ? f : { ...f, [key]: status })),
    [],
  )
  const stackTop = groundY + LIFT + Math.max(0, slabs.length - 1) * GAP

  if (!box) return null
  return (
    <div
      className={`${styles.overlay} ${reducedMotion ? styles.still : ''}`}
      role="dialog"
      aria-modal="true"
      aria-labelledby="stack-title"
    >
      <div className={styles.head}>
        <div>
          <h2 id="stack-title" className={styles.title}>
            The evidence, layer by layer
          </h2>
          <p className={styles.lede}>Each slab is a layer drawn in this turn, over the same box. Pick one to see it on the map.</p>
        </div>
        <button type="button" ref={closeRef} className="btn" onClick={onClose}>
          Back to the map
        </button>
      </div>

      <div className={styles.body}>
        <div className={styles.canvasBox} ref={canvasBox}>
          <Canvas
            dpr={[1, 2]}
            camera={{ fov: 32, near: 0.01, far: 50, position: [-1.8, 1.4, 2.2] }}
            gl={{ antialias: true }}
            onCreated={({ scene }) => {
              scene.background = new THREE.Color('#0e1012')
            }}
            aria-label="The evidence layers stacked over the ground of the same box"
          >
            <ambientLight intensity={0.9} />
            <directionalLight position={[-2.2, 1.6, 1.1]} intensity={1.6} />
            <Base model={model} depth={depth} onPeak={setPeak} onFailed={onReliefFailed} />
            {slabs.map((s) => (
              <SlabMesh
                key={s.key}
                slab={s}
                box={box}
                depth={depth}
                groupRef={(g) => {
                  if (g) groups.current.set(s.key, g)
                  else groups.current.delete(s.key)
                }}
                active={active === s.key}
                onPick={onPick}
                onHover={setActive}
                onTexture={onTexture}
              />
            ))}
            <Rig
              slabs={slabs}
              groups={groups}
              exploded={exploded}
              reduced={reducedMotion}
              groundY={groundY}
              onCollapsed={onCollapsed}
              anchors={anchors}
              onAnchors={scheduleLayout}
              follow={wide}
              stackTop={stackTop}
              depth={depth}
            />
            <OrbitControls
              makeDefault
              enablePan={false}
              enableZoom={false}
              enableDamping={!reducedMotion}
              minPolarAngle={0.35}
              maxPolarAngle={1.35}
              target={[0, stackTop * 0.45, 0]}
            />
          </Canvas>
          {wide && (
            <svg className={styles.leaders} aria-hidden="true">
              {slabs.map((s) => (
                <line
                  key={s.key}
                  ref={(el) => {
                    if (el) lines.current.set(s.key, el)
                    else lines.current.delete(s.key)
                  }}
                  className={active === s.key ? styles.leaderOn : undefined}
                />
              ))}
            </svg>
          )}
        </div>

        <div className={styles.column} ref={column}>
          {slabs.map((s) => (
            <SlabCard
              key={s.key}
              slab={s}
              picture={pictures[s.key]}
              active={active === s.key}
              onPick={onPick}
              onHover={setActive}
              cardRef={(el) => {
                if (el) cards.current.set(s.key, el)
                else cards.current.delete(s.key)
              }}
            />
          ))}
          <BaseCard model={model} reliefFailed={reliefFailed} />
        </div>
      </div>
    </div>
  )
}
