import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

export interface TerrainProps {
  height: THREE.Texture
  base: THREE.Texture
  trend: THREE.Texture | null
  /** One texture per year, oldest first. */
  years: THREE.Texture[]
  /** Returns a float position inside `years` (0 .. years.length-1). */
  yearProgress: () => number
  /** Relief as a fraction of the plane width. */
  relief: number
  trendStrength: number
  yearStrength?: number
  aspect: number
}

interface TerrainUniforms {
  [key: string]: THREE.IUniform
  uHeight: THREE.IUniform<THREE.Texture | null>
  uBase: THREE.IUniform<THREE.Texture | null>
  uTrend: THREE.IUniform<THREE.Texture | null>
  uYearA: THREE.IUniform<THREE.Texture | null>
  uYearB: THREE.IUniform<THREE.Texture | null>
  uYearMix: THREE.IUniform<number>
  uRelief: THREE.IUniform<number>
  uTexel: THREE.IUniform<THREE.Vector2>
  uTrendStrength: THREE.IUniform<number>
  uYearStrength: THREE.IUniform<number>
  uHasTrend: THREE.IUniform<number>
  uHasYear: THREE.IUniform<number>
}

/**
 * Terrain mesh: a subdivided plane displaced by the heightmap in the vertex
 * shader, with normals recomputed from the heightmap so hillshading works
 * without a normal map. The fragment stage composites three layers that the
 * panel can switch on and off: satellite base, the trend (Sen slope per pixel,
 * transparent where not significant) and the yearly anomaly frames.
 */
export function Terrain({
  height,
  base,
  trend,
  years,
  yearProgress,
  relief,
  trendStrength,
  yearStrength = 0.85,
  aspect,
}: TerrainProps) {
  const uniforms = useRef<TerrainUniforms | null>(null)

  const material = useMemo(() => {
    const created = new THREE.MeshStandardMaterial({
      map: base,
      roughness: 0.93,
      metalness: 0.02,
      dithering: true,
    })

    const imageSize = height.image as { width?: number; height?: number } | undefined
    const texelWidth = 1 / (imageSize?.width || 512)
    const texelHeight = 1 / (imageSize?.height || 512)

    created.onBeforeCompile = (shader) => {
      const own: TerrainUniforms = {
        uHeight: { value: height },
        uBase: { value: base },
        uTrend: { value: trend },
        uYearA: { value: years[0] ?? null },
        uYearB: { value: years[1] ?? null },
        uYearMix: { value: 0 },
        uRelief: { value: relief },
        uTexel: { value: new THREE.Vector2(texelWidth, texelHeight) },
        uTrendStrength: { value: trendStrength },
        uYearStrength: { value: 0.85 },
        uHasTrend: { value: trend ? 1 : 0 },
        uHasYear: { value: years.length > 1 ? 1 : 0 },
      }
      Object.assign(shader.uniforms, own)
      uniforms.current = own

      shader.vertexShader = shader.vertexShader
        .replace(
          '#include <common>',
          `#include <common>
           uniform sampler2D uHeight;
           uniform float uRelief;
           uniform vec2 uTexel;`,
        )
        .replace(
          '#include <beginnormal_vertex>',
          `#include <beginnormal_vertex>
           {
             float hL = texture2D( uHeight, uv - vec2( uTexel.x, 0.0 ) ).r;
             float hR = texture2D( uHeight, uv + vec2( uTexel.x, 0.0 ) ).r;
             float hD = texture2D( uHeight, uv - vec2( 0.0, uTexel.y ) ).r;
             float hU = texture2D( uHeight, uv + vec2( 0.0, uTexel.y ) ).r;
             vec3 slope = vec3( ( hL - hR ), ( hD - hU ), 0.0 ) * uRelief * 2.0;
             slope.x /= max( uTexel.x, 1e-5 );
             slope.y /= max( uTexel.y, 1e-5 );
             objectNormal = normalize( vec3( slope.xy, 1.0 ) );
           }`,
        )
        .replace(
          '#include <begin_vertex>',
          `#include <begin_vertex>
           transformed.z += texture2D( uHeight, uv ).r * uRelief;`,
        )

      shader.fragmentShader = shader.fragmentShader
        .replace(
          '#include <common>',
          `#include <common>
           uniform sampler2D uBase;
           uniform sampler2D uTrend;
           uniform sampler2D uYearA;
           uniform sampler2D uYearB;
           uniform float uYearMix;
           uniform float uTrendStrength;
           uniform float uYearStrength;
           uniform float uHasTrend;
           uniform float uHasYear;`,
        )
        .replace(
          '#include <map_fragment>',
          `vec3 layer = texture2D( uBase, vMapUv ).rgb;

           if ( uHasTrend > 0.5 ) {
             vec4 trendSample = texture2D( uTrend, vMapUv );
             layer = mix( layer, trendSample.rgb, trendSample.a * uTrendStrength );
           }

           if ( uHasYear > 0.5 ) {
             vec4 yearA = texture2D( uYearA, vMapUv );
             vec4 yearB = texture2D( uYearB, vMapUv );
             vec4 yearSample = mix( yearA, yearB, uYearMix );
             layer = mix( layer, yearSample.rgb, yearSample.a * uYearStrength );
           }

           diffuseColor.rgb *= layer;`,
        )
    }

    return created
  }, [base, height])

  useEffect(() => {
    const own = uniforms.current
    if (own) {
      own.uTrend.value = trend
      own.uHasTrend.value = trend ? 1 : 0
    }
  }, [trend])

  useEffect(() => {
    const own = uniforms.current
    if (!own) return
    own.uRelief.value = relief
  }, [relief])

  useEffect(() => {
    return () => {
      material.dispose()
    }
  }, [material])

  useFrame(() => {
    const own = uniforms.current
    if (!own) return
    own.uTrendStrength.value = trendStrength
    own.uYearStrength.value = yearStrength
    if (years.length > 0) {
      const progress = Math.min(Math.max(yearProgress(), 0), years.length - 1)
      const lower = Math.floor(progress)
      const upper = Math.min(lower + 1, years.length - 1)
      own.uYearA.value = years[lower]
      own.uYearB.value = years[upper]
      own.uYearMix.value = progress - lower
      own.uHasYear.value = years.length > 1 ? 1 : 0
    }
  })

  return (
    <mesh material={material} rotation={[-Math.PI / 2, 0, 0]} scale={[1, aspect, 1]} receiveShadow>
      <planeGeometry args={[1, 1, 340, 340]} />
    </mesh>
  )
}
