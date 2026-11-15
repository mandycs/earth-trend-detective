// The land cover classes a viewer can read on the map, in plain words. Colors copied from the GIBS colormap of
// MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual:
//   https://gibs.earthdata.nasa.gov/colormaps/v1.3/MODIS_IGBP_Land_Cover_Type.xml (fetched 2026-11-15)
// A class that has several IGBP colors (five forest types, two shrublands, crops and the crop mosaic) keeps all of
// them, so the swatch shows every color it stands for. Savannas, wetlands and "unclassified" are left out: the
// legend names the classes people look for, it is not the full table.

export interface LandCoverClass { name: string; colours: string[] }

export const LAND_COVER_LAYER_IDS: ReadonlySet<string> = new Set(["land_cover"]);

export const LAND_COVER_CLASSES: readonly LandCoverClass[] = [
  { name: "Water", colours: ["rgb(134,202,227)"] }, // Water Bodies
  {
    name: "Forest",
    // Evergreen needleleaf, evergreen broadleaf, deciduous needleleaf, deciduous broadleaf, mixed forests
    colours: ["rgb(33,138,33)", "rgb(49,204,49)", "rgb(152,204,49)", "rgb(150,250,150)", "rgb(141,186,141)"],
  },
  { name: "Shrubland", colours: ["rgb(186,141,141)", "rgb(245,222,179)"] }, // Closed, Open Shrublands
  { name: "Grassland", colours: ["rgb(240,185,103)"] }, // Grasslands
  { name: "Cropland", colours: ["rgb(250,239,115)", "rgb(153,147,86)"] }, // Croplands, Cropland/Natural Vegetation Mosaics
  { name: "Urban / built-up", colours: ["rgb(255,0,0)"] }, // Urban and Built-up Lands
  { name: "Snow and ice", colours: ["rgb(255,255,255)"] }, // Permanent Snow and Ice
  { name: "Barren", colours: ["rgb(191,191,189)"] }, // Barren
];

/** The readable classes of a layer, or none when it is not the land cover layer. */
export function landCoverClasses(layerId: string): readonly LandCoverClass[] {
  return LAND_COVER_LAYER_IDS.has(layerId) ? LAND_COVER_CLASSES : [];
}

/** A CSS background for a swatch: one color, or hard stripes of each. */
export function swatchBackground(c: LandCoverClass): string {
  if (c.colours.length === 1) return c.colours[0];
  const step = 100 / c.colours.length;
  const parts = c.colours.map((col, i) => `${col} ${(i * step).toFixed(1)}% ${((i + 1) * step).toFixed(1)}%`);
  return `linear-gradient(to right, ${parts.join(", ")})`;
}
