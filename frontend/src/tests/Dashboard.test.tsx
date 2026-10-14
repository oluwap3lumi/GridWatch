import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Dashboard } from '../pages/Dashboard';
import { blankMapStyle } from '../components/mapStyle';

describe('M0 dashboard', () => {
  it('renders the map container and honest empty-data status', () => {
    const html = renderToStaticMarkup(<Dashboard />);
    expect(html).toContain('GridWatch');
    expect(html).toContain('aria-label="MapLibre map of Lagos"');
    expect(html).toContain('role="status"');
    expect(html).toContain('No assets loaded');
  });

  it('provides a valid local blank style without remote data sources', () => {
    expect(blankMapStyle.version).toBe(8);
    expect(blankMapStyle.sources).toEqual({});
    expect(blankMapStyle.layers[0].type).toBe('background');
  });
});
