import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Dashboard } from '../pages/Dashboard';
import { blankMapStyle } from '../components/mapStyle';

describe('dashboard foundation', () => {
  it('renders the map container and honest empty-data status', () => {
    const html = renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}><Dashboard /></QueryClientProvider>);
    expect(html).toContain('GridWatch');
    expect(html).toContain('aria-label="MapLibre map of Lagos"');
    expect(html).toContain('role="status"');
    expect(html).toContain('Loading the complete network');
  });

  it('provides a valid local blank style without remote data sources', () => {
    expect(blankMapStyle.version).toBe(8);
    expect(blankMapStyle.sources).toEqual({});
    expect(blankMapStyle.layers[0].type).toBe('background');
  });
});
