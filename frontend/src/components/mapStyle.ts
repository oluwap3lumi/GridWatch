import type { StyleSpecification } from 'maplibre-gl';

// A local style keeps the M0 blank map independent of tile services or tokens.
export const blankMapStyle: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{
    id: 'background',
    type: 'background',
    paint: { 'background-color': '#dce8e4' },
  }],
};
