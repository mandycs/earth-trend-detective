import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { HeightGrid } from './heights'
import { sampleHeight } from './heights'

export interface TerrainProps {
  grid: HeightGrid
  base: THREE.Texture
  hillshade: THREE.Texture | null
  trend: THREE.Texture | null
  /** One texture per year, oldest first. */
  years: THREE.Texture[]
  /** Float position inside `years` (0 .. years.length-1). */
  yearProgress: () => number
  showYears: boolean
  /** Ground width in metres of the plane's x extent. */
  widthMetres: number
  exaggeration: number
  /** depth / width of the plane. */
  aspect: number
}

/** Depth of the slab under the terrain, as a fraction of the plane width. */
export const SLAB = 0.045

interface Uniforms {
  [key: string]: THREE.IUniform
  uTrend: THREE.IUniform<THREE.Texture | null>
  uYearA: THREE.IUniform<THREE.Texture | null>
  uYearB: THREE.IUniform<THREE.Texture | null>
  uShade: THREE.IUniform<THREE.Texture | null>
  uYearMix: THREE.IUniform<number>
  uTrendOn: THREE.IUniform<number>
  uYearOn: THREE.IUniform<number>
  uShadeOn: THREE.IUniform<number>
}

/**
 * Builds the relief on the CPU from full-precision heights, so normals,
 * shadows and silhouettes come from real metres, then cuts it out as a slab
 * with earth-coloured sides, like a museum relief model.
 */
function buildGeometry(grid: HeightGrid, aspect: number, scale: number) {
  const segX = Math.min(grid.width - 1, 420)
  const segZ = Math.max(8, Math.min(grid.height - 1, Math.round(segX * aspect)))
  const top = new THREE.PlaneGeometry(1, aspect, segX, segZ)
  top.rotateX(-Math.PI / 2)
  const position = top.attributes.position as THREE.BufferAttribute
  const uv = top.attributes.uv as THREE.BufferAttribute
  for (let i = 0; i < position.count; i += 1) {
    const u = uv.getX(i)
    const v = 1 - uv.getY(i) // 0 at the north edge
    position.setY(i, (sampleHeight(grid, u, v) - grid.min) * scale)
  }
  top.computeVertexNormals()

  // Four walls, from the terrain edge down to the slab floor.
  const wall: number[] = []
  const floor = -SLAB
  const edge = (fromU: number, fromV: number, toU: number, toV: number, steps: number) => {
    for (let s = 0; s < steps; s += 1) {
      const a = s / steps
      const b = (s + 1) / steps
      const u0 = fromU + (toU - fromU) * a
      const v0 = fromV + (toV - fromV) * a
      const u1 = fromU + (toU - fromU) * b
      const v1 = fromV + (toV - fromV) * b
      const x0 = u0 - 0.5
      const z0 = (v0 - 0.5) * aspect
      const x1 = u1 - 0.5
      const z1 = (v1 - 0.5) * aspect
      const h0 = (sampleHeight(grid, u0, v0) - grid.min) * scale
      const h1 = (sampleHeight(grid, u1, v1) - grid.min) * scale
      wall.push(x0, h0, z0, x0, floor, z0, x1, h1, z1)
      wall.push(x1, h1, z1, x0, floor, z0, x1, floor, z1)
    }
  }
  edge(0, 0, 1, 0, segX) // north
  edge(1, 0, 1, 1, segZ) // east
  edge(1, 1, 0, 1, segX) // south
  edge(0, 1, 0, 0, segZ) // west
  const sides = new THREE.BufferGeometry()
  sides.setAttribute('position', new THREE.Float32BufferAttribute(wall, 3))
  sides.computeVertexNormals()
  return { top, sides }
}

export function Terrain({
  grid,
  base,
  hillshade,
  trend,
  years,
  yearProgress,
  showYears,
  widthMetres,
  exaggeration,
  aspect,
}: TerrainProps) {
  const uniforms = useRef<Uniforms | null>(null)
  const scale = exaggeration / Math.max(widthMetres, 1)

  const { top, sides } = useMemo(() => buildGeometry(grid, aspect, scale), [grid, aspect, scale])

  const material = useMemo(() => {
    const created = new THREE.MeshStandardMaterial({ map: base, roughness: 0.96, metalness: 0, dithering: true })
    created.onBeforeCompile = (shader) => {
      const own: Uniforms = {
        uTrend: { value: null },
        uYearA: { value: null },
        uYearB: { value: null },
        uShade: { value: null },
        uYearMix: { value: 0 },
        uTrendOn: { value: 0 },
        uYearOn: { value: 0 },
        uShadeOn: { value: 0 },
      }
      Object.assign(shader.uniforms, own)
      uniforms.current = own
      shader.fragmentShader = shader.fragmentShader
        .replace(
          '#include <common>',
          `#include <common>
           uniform sampler2D uTrend;
           uniform sampler2D uYearA;
           uniform sampler2D uYearB;
           uniform sampler2D uShade;
           uniform float uYearMix;
           uniform float uTrendOn;
           uniform float uYearOn;
           uniform float uShadeOn;`,
        )
        .replace(
          '#include <map_fragment>',
          `vec4 baseSample = texture2D( map, vMapUv );
           vec3 layer = baseSample.rgb;
           if ( uShadeOn > 0.5 ) {
             float shade = texture2D( uShade, vMapUv ).r;
             layer *= mix( 0.72, 1.12, shade );
           }
           if ( uTrendOn > 0.5 ) {
             vec4 t = texture2D( uTrend, vMapUv );
             layer = mix( layer, mix( layer * t.rgb * 1.12, t.rgb, 0.35 ), t.a * uTrendOn );
           }
           if ( uYearOn > 0.0 ) {
             vec4 a = texture2D( uYearA, vMapUv );
             vec4 b = texture2D( uYearB, vMapUv );
             vec4 y = mix( a, b, uYearMix );
             // Multiply, so the satellite picture (the lake, the ice) stays readable under the tint.
             layer = mix( layer, layer * y.rgb * 1.12, y.a * uYearOn );
           }
           diffuseColor.rgb *= layer;`,
        )
    }
    return created
  }, [base])

  const sideMaterial = useMemo(
    () => new THREE.MeshStandardMaterial({ color: '#2a241e', roughness: 1, metalness: 0, side: THREE.DoubleSide }),
    [],
  )

  useEffect(() => () => material.dispose(), [material])
  useEffect(() => () => sideMaterial.dispose(), [sideMaterial])
  useEffect(
    () => () => {
      top.dispose()
      sides.dispose()
    },
    [top, sides],
  )

  // Fade layers in and out instead of popping them.
  const yearFade = useRef(0)
  const trendFade = useRef(0)

  useFrame((_, delta) => {
    const own = uniforms.current
    if (!own) return
    const k = Math.min(delta * 4, 1)
    const wantYears = showYears && years.length > 1 ? 1 : 0
    yearFade.current += (wantYears - yearFade.current) * k
    trendFade.current += ((trend ? 1 : 0) - trendFade.current) * k
    own.uShade.value = hillshade
    own.uShadeOn.value = hillshade ? 1 : 0
    if (trend) own.uTrend.value = trend
    own.uTrendOn.value = trendFade.current > 0.01 ? trendFade.current : 0
    if (years.length > 0) {
      const progress = Math.min(Math.max(yearProgress(), 0), years.length - 1)
      const lower = Math.floor(progress)
      const upper = Math.min(lower + 1, years.length - 1)
      own.uYearA.value = years[lower]
      own.uYearB.value = years[upper]
      own.uYearMix.value = progress - lower
    }
    own.uYearOn.value = yearFade.current > 0.01 && years.length > 0 ? yearFade.current : 0
  })

  return (
    <group>
      <mesh geometry={top} material={material} castShadow receiveShadow />
      <mesh geometry={sides} material={sideMaterial} receiveShadow />
    </group>
  )
}
