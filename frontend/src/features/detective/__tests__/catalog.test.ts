import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { LAYER_CATALOG } from '../map/layerCatalog.generated.ts'
import { catalogLayer, dateFor, tileUrl, maxZoomOf } from '../map/catalog.ts'

const get = (id: string) => {
  const l = catalogLayer(id)
  assert.ok(l, `missing ${id}`)
  return l
}

test('catalog matches the yaml', () => {
  const yaml = readFileSync(join(import.meta.dirname, '../../../../../backend/catalog/map_layers.yaml'), 'utf8')
  const ids = [...yaml.matchAll(/^  - id: (\S+)/gm)].map((m) => m[1])
  const gibs = [...yaml.matchAll(/^    gibs_layer: (\S+)/gm)].map((m) => m[1])
  const fromYaml = ids.map((id, i) => [id, gibs[i]])
  assert.equal(fromYaml.length, 12)
  assert.deepEqual(fromYaml, LAYER_CATALOG.map((l) => [l.id, l.gibs_layer]))
})

test('dateFor', () => {
  assert.equal(dateFor(get('true_colour'), { year: 2003 }), '2003-07-01')
  assert.equal(dateFor(get('land_cover'), { year: 2023 }), '2023-01-01')
  assert.equal(dateFor(get('night_lights'), { year: 2012 }), '2012-01-01')
  assert.equal(dateFor(get('ndvi'), {}), '2026-10-01')
  assert.equal(dateFor(get('true_colour'), { date: '2010-05-04' }), '2010-05-04')
  assert.equal(dateFor(get('true_colour'), { date: '2030-01-01' }), get('true_colour').dates.end)
  assert.equal(dateFor(get('land_cover'), { year: 1990 }), get('land_cover').dates.start)
})

test('tileUrl wmts', () => {
  assert.equal(
    tileUrl(get('true_colour'), '2003-07-01'),
    'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/2003-07-01/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg',
  )
  assert.ok(tileUrl(get('land_cover'), '2023-01-01').endsWith('.png'))
})

test('tileUrl vector falls back to WMS png', () => {
  const u = tileUrl(get('active_fires'), '2026-11-14')
  assert.ok(u.startsWith('https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?'))
  assert.ok(u.includes('LAYERS=MODIS_Combined_Thermal_Anomalies_All'))
  assert.ok(u.includes('FORMAT=image%2Fpng'))
  assert.ok(u.includes('TIME=2026-11-14'))
  assert.ok(u.includes('{bbox-epsg-3857}'))
})

test('maxZoomOf', () => {
  assert.equal(maxZoomOf(get('true_colour')), 9)
  assert.equal(maxZoomOf(get('precipitation')), 6)
})

test('catalogLayer unknown id', () => {
  assert.equal(catalogLayer('nope'), null)
})
