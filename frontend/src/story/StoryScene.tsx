import { useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
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

const GROUND = '#0b0d10'

/** Low oblique view the camera settles into, scaled to the slab's depth. */
function restingView(aspect: number, peak: number): THREE.Vector3 {
  const distance = 1.3 + Math.max(aspect - 1, 0) * 0.45
  return new THREE.Vector3(-0.2 * distance, 0.42 * distance + peak * 0.5, 0.84 * distance)
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
      minDistance={0.45}
      maxDistance={2.4}
      minPolarAngle={0.12}
      maxPolarAngle={Math.PI / 2.25}
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
    cam.left = -0.9
    cam.right = 0.9
    cam.top = 0.9
    cam.bottom = -0.9
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
      position={[-1.9, 1.05, -0.9]}
      intensity={3.4}
      color="#ffe9c9"
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
      camera={{ position: [0, 2.6, 0.02], fov: 34, near: 0.01, far: 30 }}
      gl={{ antialias: true, alpha: false, powerPreference: 'high-performance', toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.22 }}
    >
      <color attach="background" args={[GROUND]} />
      <fog attach="fog" args={[GROUND, 2.2, 5.5]} />
      <hemisphereLight args={['#a9c4e6', '#3a2c20', 0.75]} />
      <ambientLight intensity={0.18} />
      <Sun />
      <directionalLight position={[1.6, 0.7, 1.4]} intensity={0.35} color="#8fb4ff" />
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
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.0451, 0]} receiveShadow>
        <circleGeometry args={[3, 64]} />
        <shadowMaterial opacity={0.45} />
      </mesh>
      <CameraRig siteId={site.id} aspect={aspect} peak={peak} />
    </Canvas>
  )
}
