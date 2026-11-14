/**
 * Heights in metres, read at full precision. Browsers decode 16-bit PNGs to
 * 8 bits (256 steps, ~13 m terraces on Aletsch), so the PNG is parsed here:
 * zlib through DecompressionStream, then the five PNG scanline filters.
 * A Mapbox terrain-RGB file is used instead when the pipeline provides one.
 */
export interface HeightGrid {
  width: number
  height: number
  /** Row-major, north row first, metres above sea level. */
  data: Float32Array
  min: number
  max: number
}

async function inflate(bytes: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([bytes as BlobPart]).stream().pipeThrough(new DecompressionStream('deflate'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

function paeth(a: number, b: number, c: number): number {
  const p = a + b - c
  const pa = Math.abs(p - a)
  const pb = Math.abs(p - b)
  const pc = Math.abs(p - c)
  if (pa <= pb && pa <= pc) return a
  return pb <= pc ? b : c
}

/** 16-bit (or 8-bit) greyscale PNG -> raw sample values. */
export async function decodeGreyPng(buffer: ArrayBuffer): Promise<{ width: number; height: number; samples: Float32Array; maxSample: number }> {
  const view = new DataView(buffer)
  const bytes = new Uint8Array(buffer)
  let offset = 8
  let width = 0
  let height = 0
  let depth = 0
  let colour = 0
  let interlace = 0
  const idat: Uint8Array[] = []
  while (offset < bytes.length) {
    const length = view.getUint32(offset)
    const type = String.fromCharCode(...bytes.subarray(offset + 4, offset + 8))
    const body = bytes.subarray(offset + 8, offset + 8 + length)
    if (type === 'IHDR') {
      width = view.getUint32(offset + 8)
      height = view.getUint32(offset + 12)
      depth = body[8]
      colour = body[9]
      interlace = body[12]
    } else if (type === 'IDAT') {
      idat.push(body)
    } else if (type === 'IEND') {
      break
    }
    offset += 12 + length
  }
  if (colour !== 0 || interlace !== 0 || (depth !== 16 && depth !== 8)) {
    throw new Error(`Unsupported heightmap PNG (colour ${colour}, depth ${depth}, interlace ${interlace})`)
  }
  const joined = new Uint8Array(idat.reduce((n, c) => n + c.length, 0))
  let at = 0
  for (const chunk of idat) {
    joined.set(chunk, at)
    at += chunk.length
  }
  const raw = await inflate(joined)
  const bpp = depth / 8
  const stride = width * bpp
  const out = new Uint8Array(stride * height)
  for (let y = 0; y < height; y += 1) {
    const filter = raw[y * (stride + 1)]
    const src = y * (stride + 1) + 1
    const dst = y * stride
    for (let x = 0; x < stride; x += 1) {
      const value = raw[src + x]
      const left = x >= bpp ? out[dst + x - bpp] : 0
      const up = y > 0 ? out[dst - stride + x] : 0
      const upLeft = y > 0 && x >= bpp ? out[dst - stride + x - bpp] : 0
      let decoded = value
      if (filter === 1) decoded = value + left
      else if (filter === 2) decoded = value + up
      else if (filter === 3) decoded = value + ((left + up) >> 1)
      else if (filter === 4) decoded = value + paeth(left, up, upLeft)
      out[dst + x] = decoded & 0xff
    }
  }
  const samples = new Float32Array(width * height)
  if (depth === 16) {
    for (let i = 0; i < samples.length; i += 1) samples[i] = (out[i * 2] << 8) | out[i * 2 + 1]
  } else {
    for (let i = 0; i < samples.length; i += 1) samples[i] = out[i]
  }
  return { width, height, samples, maxSample: depth === 16 ? 65535 : 255 }
}

async function decodeTerrainRgb(url: string): Promise<HeightGrid> {
  const blob = await (await fetch(url)).blob()
  const bitmap = await createImageBitmap(blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' })
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height)
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) throw new Error('No 2D context for terrain-RGB')
  context.drawImage(bitmap, 0, 0)
  const pixels = context.getImageData(0, 0, bitmap.width, bitmap.height).data
  const data = new Float32Array(bitmap.width * bitmap.height)
  let min = Infinity
  let max = -Infinity
  for (let i = 0; i < data.length; i += 1) {
    const h = -10000 + (pixels[i * 4] * 65536 + pixels[i * 4 + 1] * 256 + pixels[i * 4 + 2]) * 0.1
    data[i] = h
    if (h < min) min = h
    if (h > max) max = h
  }
  return { width: bitmap.width, height: bitmap.height, data, min, max }
}

export async function loadHeights(
  urls: { rgb?: string; grey: string },
  rangeMetres: [number, number] | undefined,
): Promise<HeightGrid> {
  if (urls.rgb) {
    try {
      return await decodeTerrainRgb(urls.rgb)
    } catch {
      /* fall back to the greyscale file */
    }
  }
  const response = await fetch(urls.grey)
  if (!response.ok) throw new Error(`Could not load the heightmap (${response.status})`)
  const png = await decodeGreyPng(await response.arrayBuffer())
  const [lo, hi] = rangeMetres ?? [0, 1000]
  const scale = (hi - lo) / png.maxSample
  const data = new Float32Array(png.samples.length)
  for (let i = 0; i < data.length; i += 1) data[i] = lo + png.samples[i] * scale
  return { width: png.width, height: png.height, data, min: lo, max: hi }
}

/** Bilinear sample at u, v in [0, 1], v = 0 at the north edge. */
export function sampleHeight(grid: HeightGrid, u: number, v: number): number {
  const x = Math.min(Math.max(u, 0), 1) * (grid.width - 1)
  const y = Math.min(Math.max(v, 0), 1) * (grid.height - 1)
  const x0 = Math.floor(x)
  const y0 = Math.floor(y)
  const x1 = Math.min(x0 + 1, grid.width - 1)
  const y1 = Math.min(y0 + 1, grid.height - 1)
  const fx = x - x0
  const fy = y - y0
  const d = grid.data
  const w = grid.width
  const top = d[y0 * w + x0] * (1 - fx) + d[y0 * w + x1] * fx
  const bottom = d[y1 * w + x0] * (1 - fx) + d[y1 * w + x1] * fx
  return top * (1 - fy) + bottom * fy
}
