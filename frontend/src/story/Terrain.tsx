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
  /** Draw a water surface where the elevation model is flat (default on). */
  autoWater?: boolean
  /** Mesh resolution along the width. */
  segments?: number
}

/** Depth of the slab under the terrain, as a fraction of the plane width. */
export const SLAB = 0.045

/** Share of the width over which the edges ease down to the ground. */
const EDGE = 0.035

/**
 * Height of a still water surface in the elevation model, if there is one.
 * Radar elevation models record lakes and the sea as perfectly flat, so a
 * still surface shows up as one 1-metre bin holding a large share of the
 * pixels. Returns metres, or null when no such flat level exists.
 */
export function waterLevel(grid: HeightGrid): number | null {
  const counts = new Map<number, number>()
  const step = Math.max(1, Math.floor(grid.data.length / 400_000))
  let total = 0
  for (let i = 0; i < grid.data.length; i += step) {
    const bin = Math.round(grid.data[i])
    counts.set(bin, (counts.get(bin) ?? 0) + 1)
    total += 1
  }
  let best = 0
  let level = 0
  for (const [bin, n] of counts) {
    if (n > best) {
      best = n
      level = bin
    }
  }
  if (best / total < 0.03) return null
  // The surface is exactly flat: take the precise value, not the rounded bin.
  let sum = 0
  let flat = 0
  for (let i = 0; i < grid.data.length; i += step) {
    if (Math.abs(grid.data[i] - level) < 0.5) {
      sum += grid.data[i]
      flat += 1
    }
  }
  const exact = sum / Math.max(flat, 1)
  let onLevel = 0
  for (let i = 0; i < grid.data.length; i += step) if (Math.abs(grid.data[i] - exact) < WATER_TOLERANCE) onLevel += 1
  return onLevel / total > 0.03 ? exact : null
}

/**
 * Which pixels are open water: on the flat level, and part of a large compact
 * body (sea, lake, wide river). Isolated flat pixels, like dry marsh that the
 * radar also recorded at sea level, are left as land.
 */
export function waterMask(grid: HeightGrid, level: number): Uint8Array {
  const { width: w, height: h, data } = grid
  const flat = new Uint8Array(w * h)
  for (let i = 0; i < flat.length; i += 1) flat[i] = Math.abs(data[i] - level) < WATER_TOLERANCE ? 1 : 0
  // Erode by 2 px: thin and speckled patches disappear.
  const eroded = new Uint8Array(w * h)
  for (let y = 2; y < h - 2; y += 1) {
    for (let x = 2; x < w - 2; x += 1) {
      let all = 1
      for (let dy = -2; dy <= 2 && all; dy += 1) for (let dx = -2; dx <= 2; dx += 1) if (!flat[(y + dy) * w + x + dx]) { all = 0; break }
      eroded[y * w + x] = all
    }
  }
  // Keep only components bigger than 0.5% of the picture.
  const label = new Int32Array(w * h)
  const keep = new Uint8Array(w * h)
  const stack: number[] = []
  let next = 1
  for (let start = 0; start < eroded.length; start += 1) {
    if (!eroded[start] || label[start]) continue
    const members: number[] = []
    label[start] = next
    stack.push(start)
    while (stack.length) {
      const i = stack.pop() as number
      members.push(i)
      const x = i % w
      const neighbours = [x > 0 ? i - 1 : -1, x < w - 1 ? i + 1 : -1, i - w, i + w]
      for (const n of neighbours) {
        if (n >= 0 && n < eroded.length && eroded[n] && !label[n]) {
          label[n] = next
          stack.push(n)
        }
      }
    }
    if (members.length > eroded.length * 0.005) for (const i of members) keep[i] = 1
    next += 1
  }
  // Grow back by 2 px, but only over flat pixels, so shorelines stay where they were.
  const out = new Uint8Array(w * h)
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const i = y * w + x
      if (!flat[i]) continue
      let near = 0
      for (let dy = -2; dy <= 2 && !near; dy += 1) {
        const yy = y + dy
        if (yy < 0 || yy >= h) continue
        for (let dx = -2; dx <= 2; dx += 1) {
          const xx = x + dx
          if (xx >= 0 && xx < w && keep[yy * w + xx]) { near = 1; break }
        }
      }
      out[i] = near
    }
  }
  return out
}

/** Metres within which a height counts as the flat water surface. */
const WATER_TOLERANCE = 0.06
/** How far under the water surface flat pixels are pushed, in metres. */
const WATER_DEPTH = 2

/** Mean colour of a picture, for the ground that runs on to the horizon. */
export function meanColour(texture: THREE.Texture): THREE.Color {
  const image = texture.image as CanvasImageSource | undefined
  const colour = new THREE.Color('#6b5a48')
  if (!image || typeof document === 'undefined') return colour
  try {
    const canvas = document.createElement('canvas')
    canvas.width = 16
    canvas.height = 16
    const context = canvas.getContext('2d')
    if (!context) return colour
    context.drawImage(image, 0, 0, 16, 16)
    const data = context.getImageData(0, 0, 16, 16).data
    let r = 0
    let g = 0
    let b = 0
    for (let i = 0; i < data.length; i += 4) {
      r += data[i]
      g += data[i + 1]
      b += data[i + 2]
    }
    const n = data.length / 4
    colour.setRGB(r / n / 255, g / n / 255, b / n / 255, THREE.SRGBColorSpace)
  } catch {
    /* keep the fallback */
  }
  return colour
}

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
  uGround: THREE.IUniform<THREE.Color>
}

/**
 * Builds the relief on the CPU from full-precision heights, so normals,
 * shadows and silhouettes come from real metres, then cuts it out as a slab
 * with earth-coloured sides, like a museum relief model.
 */
function buildGeometry(grid: HeightGrid, aspect: number, scale: number, water: number | null, segments = 512) {
  const mask = water == null ? null : waterMask(grid, water)
  const segX = Math.min(grid.width - 1, segments)
  const segZ = Math.max(8, Math.min(grid.height - 1, Math.round(segX * aspect)))
  const top = new THREE.PlaneGeometry(1, aspect, segX, segZ)
  top.rotateX(-Math.PI / 2)
  const position = top.attributes.position as THREE.BufferAttribute
  const uv = top.attributes.uv as THREE.BufferAttribute
  for (let i = 0; i < position.count; i += 1) {
    const u = uv.getX(i)
    const v = 1 - uv.getY(i) // 0 at the north edge
    // Ease the last few percent of each edge down to the surrounding ground,
    // so the relief meets the horizon instead of ending in a cut-out block.
    const edge = Math.min(u, 1 - u, v, 1 - v)
    const t = Math.min(edge / EDGE, 1)
    const taper = t * t * (3 - 2 * t)
    let h = sampleHeight(grid, u, v)
    if (water != null && mask) {
      const px = Math.min(grid.width - 1, Math.round(u * (grid.width - 1)))
      const py = Math.min(grid.height - 1, Math.round(v * (grid.height - 1)))
      if (mask[py * grid.width + px]) h = water - WATER_DEPTH
      else if (h < water + WATER_TOLERANCE) h = water + WATER_TOLERANCE * 2
    }
    position.setY(i, (h - grid.min) * scale * taper)
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
  autoWater = true,
  segments = 512,
}: TerrainProps) {
  const uniforms = useRef<Uniforms | null>(null)
  const scale = exaggeration / Math.max(widthMetres, 1)

  const water = useMemo(() => (autoWater ? waterLevel(grid) : null), [grid, autoWater])
  const { top, sides } = useMemo(() => buildGeometry(grid, aspect, scale, water, segments), [grid, aspect, scale, water, segments])

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
        uGround: { value: meanColour(base) },
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
           uniform float uShadeOn;
           uniform vec3 uGround;`,
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
           float border = min( min( vMapUv.x, 1.0 - vMapUv.x ), min( vMapUv.y, 1.0 - vMapUv.y ) );
           layer = mix( uGround, layer, smoothstep( 0.0, 0.03, border ) );
           diffuseColor.rgb *= layer;`,
        )
    }
    return created
    // The material is built once; later pictures only swap its map below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    material.map = base
    material.needsUpdate = false
  }, [material, base])

  const groundColour = useMemo(() => meanColour(base), [base])
  const waterY = water == null ? null : (water - grid.min + 0.05) * scale

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
      {waterY != null ? (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, waterY, 0]} receiveShadow>
          <planeGeometry args={[1 - EDGE * 1.6, aspect * (1 - EDGE * 1.6)]} />
          <meshStandardMaterial color="#21465c" roughness={0.12} metalness={0.25} transparent opacity={0.88} />
        </mesh>
      ) : null}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.0005, 0]} receiveShadow>
        <planeGeometry args={[60, 60]} />
        <meshStandardMaterial color={groundColour} roughness={1} metalness={0} />
      </mesh>
    </group>
  )
}
