import { useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Sky } from '@react-three/drei'
import * as THREE from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import type { Site } from './types'
import { bboxWidthMeters } from './types'
import type { StoryAssets } from './useSite'
import { Terrain } from './Terrain'

export interface StorySceneProps {
  site: Site
  assets: StoryAssets
  yearProgress: () => number
  showYears: boolean
  exaggeration: number
}

/** Haze at the horizon; the fog fades the far ground into it. */
const HAZE = '#c3cfdb'
/** Sun direction: low afternoon light from the west-south-west, about 28° up. */
const SUN: [number, number, number] = [-2.2, 1.25, 1.1]

/** Low oblique view the camera settles into, scaled to the slab's depth. */
function restingView(aspect: number, peak: number): THREE.Vector3 {
  // An aircraft's view: low and oblique, the horizon in frame.
  const distance = 0.78 + Math.max(aspect - 1, 0) * 0.3
  return new THREE.Vector3(-0.22 * distance, 0.24 * distance + peak * 0.9, 0.92 * distance)
}

function easeOutCubic(t: number) {
  return 1 - Math.pow(1 - t, 3)
}

/**
 * Flies the camera in from straight overhead, the way a satellite would see
 * the place, down to a low angle where the relief reads. Then hands control
 * to the visitor, with a slow drift until they touch it.
 */
function CameraRig({ siteId, aspect, peak }: { siteId: string; aspect: number; peak: number }) {
  const { camera } = useThree()
  const controls = useRef<OrbitControlsImpl | null>(null)
  const start = useRef(0)
  const done = useRef(false)
  const reduced = useRef(false)
  const from = useMemo(() => new THREE.Vector3(0.001, 2.6, 0.02), [])
  const to = useMemo(() => restingView(aspect, peak), [aspect, peak])
  const target = useMemo(() => new THREE.Vector3(0, peak * 0.35, 0), [peak])

  useEffect(() => {
    reduced.current = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    start.current = performance.now()
    done.current = false
    camera.position.copy(reduced.current ? to : from)
    camera.lookAt(target)
  }, [siteId, camera, from, to, target])

  useFrame(() => {
    const c = controls.current
    if (!c) return
    if (!done.current) {
      const t = reduced.current ? 1 : Math.min((performance.now() - start.current) / 2600, 1)
      camera.position.lerpVectors(from, to, easeOutCubic(t))
      c.target.copy(target)
      if (t >= 1) {
        done.current = true
        c.enabled = true
      } else {
        c.enabled = false
      }
    }
    c.update()
  })

  return (
    <OrbitControls
      ref={controls}
      enablePan={false}
      enableDamping
      dampingFactor={0.08}
      rotateSpeed={0.55}
      minDistance={0.18}
      maxDistance={2.4}
      minPolarAngle={0.12}
      maxPolarAngle={Math.PI / 2.08}
      autoRotate
      autoRotateSpeed={0.35}
      onStart={() => {
        if (controls.current) controls.current.autoRotate = false
      }}
    />
  )
}

/** Low raking sun with a soft shadow, so ridges and valleys read. */
function Sun() {
  const light = useRef<THREE.DirectionalLight>(null)
  useEffect(() => {
    const l = light.current
    if (!l) return
    const cam = l.shadow.camera as THREE.OrthographicCamera
    cam.left = -0.75
    cam.right = 0.75
    cam.top = 0.75
    cam.bottom = -0.75
    cam.near = 0.1
    cam.far = 6
    cam.updateProjectionMatrix()
    l.shadow.mapSize.set(2048, 2048)
    l.shadow.bias = -0.0004
    l.shadow.normalBias = 0.002
    l.target.position.set(0, 0, 0)
    l.target.updateMatrixWorld()
  }, [])
  return (
    <directionalLight
      ref={light}
      position={SUN}
      intensity={3.1}
      color="#fff3e2"
      castShadow
    />
  )
}

export function StoryScene({ site, assets, yearProgress, showYears, exaggeration }: StorySceneProps) {
  const [west, south, east, north] = site.bbox
  const midLat = ((south + north) / 2) * (Math.PI / 180)
  const widthMetres = Math.abs(east - west) * 111_320 * Math.cos(midLat)
  const depthMetres = Math.abs(north - south) * 110_540
  const aspect = Math.min(Math.max(depthMetres / Math.max(widthMetres, 1), 0.4), 2.5)

  const grid = assets.grid
  const peak = grid ? ((grid.max - grid.min) * exaggeration) / Math.max(widthMetres || bboxWidthMeters(site.bbox), 1) : 0.1

  if (!grid || !assets.base) return null

  return (
    <Canvas
      shadows="soft"
      dpr={[1, 2]}
      camera={{ position: [0, 2.6, 0.02], fov: 42, near: 0.003, far: 80 }}
      gl={{ antialias: true, alpha: false, powerPreference: 'high-performance', toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 0.9 }}
    >
      <Sky distance={30} sunPosition={SUN} turbidity={6} rayleigh={1.4} mieCoefficient={0.006} mieDirectionalG={0.8} />
      <fog attach="fog" args={[HAZE, 0.9, 7]} />
      <hemisphereLight args={['#bcd3ee', '#6f6253', 0.85]} />
      <Sun />
      <group position={[0, 0, 0]}>
        <Terrain
          grid={grid}
          base={assets.base}
          hillshade={assets.hillshade}
          trend={assets.trend}
          years={assets.years}
          yearProgress={yearProgress}
          showYears={showYears}
          widthMetres={widthMetres}
          exaggeration={exaggeration}
          aspect={aspect}
        />
      </group>
      <CameraRig siteId={site.id} aspect={aspect} peak={peak} />
    </Canvas>
  )
}
