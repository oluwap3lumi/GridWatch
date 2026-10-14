import type { StyleSpecification } from 'maplibre-gl';

// Local style: no remote tiles, glyphs, or access tokens.
export const blankMapStyle: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{
    id: 'background',
    type: 'background',
    paint: { 'background-color': '#19383d' },
  }],
};
