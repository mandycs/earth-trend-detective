// Picking a slab of the stack shows that one layer on the main map. Pure: a fresh view, the input untouched.
import type { MapView } from "../map/mapView.ts";
import type { Slab } from "./stackModel.ts";

/** The view with only the picked slab drawn: a layer in its own slot (no curtain). */
export function showSlab(view: MapView, slab: Slab): MapView {
  const lv = slab.show.layer;
  // One coloured layer at a time: a context layer is shown alone, an evidence layer over the context.
  if (lv.role === "context") return { ...view, curtain: null, evidence: null, context: lv, footprints: [] };
  return { ...view, curtain: null, evidence: lv, footprints: [] };
}

/** "True colour (MODIS Terra), 2024": the title and the drawn year or period, as on the slab's card. */
export function slabCaption(slab: Slab): string {
  if (slab.year != null) return `${slab.title}, ${slab.year}`;
  if (slab.period) return `${slab.title}, ${slab.period[0]}–${slab.period[1]}`;
  return slab.title;
}
