# Synthetic upload samples

Every coordinate and attribute here comes from `data/generator/assets.py`, using
seed 42, 40 assets, two feeders, and ten transformers. The selected files contain
eight transformers, eight poles, and two feeders; no real network data is used.
Model dates predate the demo cutoff. Generator loads are capped at the upload
contract's 1.5 maximum. Shapefile header/ZIP dates are fixed for reproducibility.

| File | Layer | Features | CRS / expected result |
| --- | --- | ---: | --- |
| `transformers.csv` | transformer | 8 | EPSG:4326; lat/lon and parent external IDs |
| `poles.geojson` | pole | 8 | EPSG:4326; valid point features |
| `feeder_lines.geojson` | feeder_line | 2 | EPSG:4326; valid line features |
| `poles_shapefile.zip` | pole | 8 | EPSG:32631; `.prj` drives reprojection; IDs match poles GeoJSON |
| `broken_transformers.csv` | transformer | 5 | One valid row; four invalid (zero coordinates, bad date/capacity, duplicate IDs) |

First seed/train/rescore a new demo. Upload the transformers, then poles, then
feeder lines through **Upload**. References initially warn and resolve when the
parents arrive. Re-upload transformers or import the Shapefile poles to update
the same assets; there should still be 18 imported assets. Enable rescoring on
the final import, or use **Rescore network** afterward. These complete samples
need no model-attribute defaults. Estimates still use synthetic historical context.

Try the broken file and download the error CSV. Commit its one valid row only
after explicitly accepting partial success, or close without committing. Its IDs
overlap the clean sample so a committed valid row updates that existing asset.
Rollback in reverse batch order, then rescore to restore derived risk scores.

Regenerate or check using approved host development tools:

```sh
uv run --project backend python -m data.generator.samples
uv run --project backend python -m data.generator.samples --check
```

The samples inherit the repository's MIT licence.
