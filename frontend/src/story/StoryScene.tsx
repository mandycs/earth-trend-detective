import { useMemo } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import type { Site } from './types'
import { reliefUnits } from './types'
import type { StoryAssets } from './useSite'
import { Terrain } from './Terrain'

export interface StorySceneProps {
  site: Site
  assets: StoryAssets
  yearProgress: () => number
  showTrend: boolean
}

export function StoryScene({ site, assets, yearProgress, showTrend }: StorySceneProps) {

  const aspect = useMemo(() => {
    const [west, south, east, north] = site.bbox
    const midLat = ((south + north) / 2) * (Math.PI / 180)
    const width = Math.abs(east - west) * Math.cos(midLat)
    const height = Math.abs(north - south)
    return Math.min(Math.max(height / Math.max(width, 1e-6), 0.4), 2.5)
  }, [site.bbox])

  const relief = useMemo(() => reliefUnits(site), [site])

  if (!assets.height || !assets.base) return null

  return (
    <Canvas
      shadows={false}
      dpr={[1, 2]}
      camera={{ position: [0.62, 0.52, 0.66], fov: 38, near: 0.01, far: 20 }}
      gl={{ antialias: true, alpha: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' }}
    >
      <color attach="background" args={['#08111d']} />
      <fogExp2 attach="fog" args={['#08111d', 0.65]} />
      <ambientLight intensity={0.85} />
      <hemisphereLight args={['#9ec5ff', '#2b2118', 0.55]} />
      <directionalLight position={[-1.6, 2.1, 1.1]} intensity={3.1} color="#fff4e0" />
      <directionalLight position={[1.8, 0.9, -1.2]} intensity={0.55} color="#7fb0ff" />
      <Terrain
        height={assets.height}
        base={assets.base}
        trend={showTrend ? assets.trend : null}
        years={assets.years}
        yearProgress={yearProgress}
        relief={relief}
        trendStrength={showTrend ? 0.95 : 0}
        aspect={aspect}
      />
      <OrbitControls
        enablePan={false}
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.5}
        minDistance={0.55}
        maxDistance={1.9}
        minPolarAngle={0.18}
        maxPolarAngle={Math.PI / 2.15}
        target={[0, 0, 0]}
      />
      <GridGlow />
    </Canvas>
  )
}

/** Thin ring under the terrain that gives the object a plinth, no texture needed. */
function GridGlow() {
  const material = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: '#1b3550',
        transparent: true,
        opacity: 0.55,
        side: THREE.DoubleSide,
      }),
    [],
  )
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.12, 0]} material={material}>
      <ringGeometry args={[0.72, 0.74, 96]} />
    </mesh>
  )
}
