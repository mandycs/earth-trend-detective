import { useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Sky } from '@react-three/drei'
import * as THREE from 'three'
import { Terrain } from '../Terrain'
import { sampleHeight } from '../heights'
import type { DetailAssets } from './useDetail'

const HAZE = '#c3cfdb'
const SUN: [number, number, number] = [-2.2, 1.0, 1.3]

export interface DroneSceneProps {
  detail: DetailAssets
  /** Lake level for the current year in metres, or null when it cannot be drawn. */
  level: number | null
  exaggeration: number
  onAltitude?: (metres: number) => void
}

function widthOf(bbox: [number, number, number, number]) {
  const [west, south, east, north] = bbox
  const midLat = ((south + north) / 2) * (Math.PI / 180)
  const width = Math.abs(east - west) * 111_320 * Math.cos(midLat)
  const depth = Math.abs(north - south) * 110_540
  return { width, depth }
}

/** Flat water at the year's level, easing between years. */
function Water({ level, min, scale, aspect }: { level: number | null; min: number; scale: number; aspect: number }) {
  const mesh = useRef<THREE.Mesh>(null)
  const material = useRef<THREE.MeshStandardMaterial>(null)
  const current = useRef(level ?? min)
  const shown = useRef(level == null ? 0 : 1)
  useFrame((_, delta) => {
    const k = Math.min(delta * 2.2, 1)
    if (level != null) current.current += (level - current.current) * k
    shown.current += ((level == null ? 0 : 1) - shown.current) * k
    if (mesh.current) {
      mesh.current.position.y = (current.current - min) * scale
      mesh.current.visible = shown.current > 0.02
    }
    if (material.current) material.current.opacity = 0.86 * shown.current
  })
  return (
    <mesh ref={mesh} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
      <planeGeometry args={[0.93, aspect * 0.93]} />
      <meshStandardMaterial ref={material} color="#245166" roughness={0.1} metalness={0.25} transparent opacity={0.86} />
    </mesh>
  )
}

/**
 * Low flight over the close-up. Keyboard: W/S or ↑/↓ forward and back, A/D or
 * ←/→ sideways, Q/E down and up. Mouse: drag to look, wheel for height.
 * Touch: drag up/down to fly, left/right to turn; pinch for height.
 */
function Flight({ detail, scale, aspect, onAltitude }: { detail: DetailAssets; scale: number; aspect: number; onAltitude?: (m: number) => void }) {
  const { camera, gl } = useThree()
  const keys = useRef(new Set<string>())
  const state = useRef({ x: -0.05, z: aspect * 0.42, agl: 450, yaw: 0.15, pitch: -0.32 })
  const lastReport = useRef(0)

  useEffect(() => {
    const isField = (t: EventTarget | null) => t instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)
    const down = (e: KeyboardEvent) => {
      if (isField(e.target)) return
      const k = e.key.toLowerCase()
      if (['w', 'a', 's', 'd', 'q', 'e', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(k)) {
        keys.current.add(k)
        e.preventDefault()
      }
    }
    const up = (e: KeyboardEvent) => keys.current.delete(e.key.toLowerCase())
    const blur = () => keys.current.clear()
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', blur)

    const el = gl.domElement
    const pointers = new Map<number, { x: number; y: number }>()
    let pinch = 0
    const onDown = (e: PointerEvent) => {
      el.setPointerCapture(e.pointerId)
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()]
        pinch = Math.hypot(a.x - b.x, a.y - b.y)
      }
    }
    const onMove = (e: PointerEvent) => {
      const prev = pointers.get(e.pointerId)
      if (!prev) return
      const dx = e.clientX - prev.x
      const dy = e.clientY - prev.y
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
      const s = state.current
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()]
        const d = Math.hypot(a.x - b.x, a.y - b.y)
        if (pinch > 0) s.agl = THREE.MathUtils.clamp(s.agl * (pinch / Math.max(d, 1)), 60, 1500)
        pinch = d
        return
      }
      if (e.pointerType === 'touch') {
        s.yaw -= dx * 0.005
        const step = (dy * Math.max(s.agl, 150) * 0.004) * scale
        s.x -= Math.sin(s.yaw) * step
        s.z -= Math.cos(s.yaw) * step
      } else {
        s.yaw -= dx * 0.004
        s.pitch = THREE.MathUtils.clamp(s.pitch - dy * 0.004, -1.35, 0.25)
      }
    }
    const onUp = (e: PointerEvent) => {
      pointers.delete(e.pointerId)
      pinch = 0
    }
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      state.current.agl = THREE.MathUtils.clamp(state.current.agl * (1 + e.deltaY * 0.0012), 60, 1500)
    }
    el.addEventListener('pointerdown', onDown)
    el.addEventListener('pointermove', onMove)
    el.addEventListener('pointerup', onUp)
    el.addEventListener('pointercancel', onUp)
    el.addEventListener('wheel', onWheel, { passive: false })
    el.style.touchAction = 'none'
    el.style.cursor = 'grab'
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', blur)
      el.removeEventListener('pointerdown', onDown)
      el.removeEventListener('pointermove', onMove)
      el.removeEventListener('pointerup', onUp)
      el.removeEventListener('pointercancel', onUp)
      el.removeEventListener('wheel', onWheel)
    }
  }, [gl, scale])

  const euler = useMemo(() => new THREE.Euler(0, 0, 0, 'YXZ'), [])

  useFrame((_, delta) => {
    const s = state.current
    const k = keys.current
    const dt = Math.min(delta, 0.05)
    const speed = Math.max(s.agl, 150) * 0.9 * scale * dt
    const fwd = (k.has('w') || k.has('arrowup') ? 1 : 0) - (k.has('s') || k.has('arrowdown') ? 1 : 0)
    const side = (k.has('d') || k.has('arrowright') ? 1 : 0) - (k.has('a') || k.has('arrowleft') ? 1 : 0)
    s.x += (-Math.sin(s.yaw) * fwd + Math.cos(s.yaw) * side) * speed
    s.z += (-Math.cos(s.yaw) * fwd - Math.sin(s.yaw) * side) * speed
    if (k.has('e')) s.agl = Math.min(s.agl * (1 + dt * 0.9), 1500)
    if (k.has('q')) s.agl = Math.max(s.agl * (1 - dt * 0.9), 60)
    s.x = THREE.MathUtils.clamp(s.x, -0.55, 0.55)
    s.z = THREE.MathUtils.clamp(s.z, -aspect * 0.55, aspect * 0.55)

    const u = s.x + 0.5
    const v = s.z / aspect + 0.5
    const inside = u >= 0 && u <= 1 && v >= 0 && v <= 1
    const ground = inside ? (sampleHeight(detail.grid, u, v) - detail.grid.min) * scale : 0
    const targetY = ground + s.agl * scale
    camera.position.x += (s.x - camera.position.x) * Math.min(dt * 6, 1)
    camera.position.z += (s.z - camera.position.z) * Math.min(dt * 6, 1)
    camera.position.y += (targetY - camera.position.y) * Math.min(dt * 3, 1)
    euler.set(s.pitch, s.yaw, 0)
    camera.quaternion.setFromEuler(euler)

    const now = performance.now()
    if (onAltitude && now - lastReport.current > 250) {
      lastReport.current = now
      onAltitude(Math.round((camera.position.y - ground) / scale))
    }
  })
  return null
}

export function DroneScene({ detail, level, exaggeration, onAltitude }: DroneSceneProps) {
  const { width, depth } = widthOf(detail.info.bbox)
  const aspect = depth / width
  const scale = exaggeration / width

  return (
    <Canvas
      shadows="soft"
      dpr={[1, 2]}
      camera={{ position: [0, 0.1, aspect * 0.42], fov: 55, near: 0.0008, far: 60 }}
      gl={{ antialias: true, alpha: false, powerPreference: 'high-performance', toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 0.9 }}
    >
      <Sky distance={30} sunPosition={SUN} turbidity={6} rayleigh={1.4} mieCoefficient={0.006} mieDirectionalG={0.8} />
      <fog attach="fog" args={[HAZE, 0.5, 4.5]} />
      <hemisphereLight args={['#bcd3ee', '#6f6253', 0.85]} />
      <directionalLight position={SUN} intensity={3} color="#fff3e2" />
      <Terrain
        grid={detail.grid}
        base={detail.base}
        hillshade={detail.hillshade}
        trend={null}
        years={[]}
        yearProgress={() => 0}
        showYears={false}
        widthMetres={width}
        exaggeration={exaggeration}
        aspect={aspect}
        autoWater={false}
        segments={900}
      />
      <Water level={level} min={detail.grid.min} scale={scale} aspect={aspect} />
      <Flight detail={detail} scale={scale} aspect={aspect} onAltitude={onAltitude} />
    </Canvas>
  )
}
