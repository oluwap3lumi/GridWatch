# Data dictionary

Only synthetic or public data is permitted. Demo data originates in `data/generator`.

M1 schema: all geometry uses EPSG:4326 and explicit GiST indexes. Feeder assets
are LineStrings; transformers and poles are Points. `assets.feeder_id` links point
assets to a feeder and is null for feeders. A database trigger enforces parent type.
Asset IDs, observation IDs, and outage IDs are deterministic generator-assigned integers.

| Table | Fields and units |
| --- | --- |
| `assets` | id, type, feeder_id, geom, install_date, capacity_kva (kVA), load_factor (ratio, 0–2), material, vegetation_index (0–1), last_maintenance_date |
| `outage_events` | id, asset_id, started_at (UTC), duration_min (minutes), cause, geom (Point) |
| `weather_obs` | id, observed_at (UTC), geom (Point), rainfall_mm (mm), wind_kph (km/h), temp_c (°C), lightning_density (flashes/km²/day) |
| `risk_scores` | asset_id (primary key), score (0–1), band, model_version (foreign key), scored_at (UTC), top_factors (JSONB) |
| `model_runs` | id, unique model_version, trained_at (UTC), data_hash (SHA-256), features (JSONB string list), metrics (JSONB), git_sha |

M1 creates the model/risk tables for the planned schema, but leaves them empty.
Training and scoring belong to M2/M3. Foreign keys and database constraints reject
invalid geometry, asset parentage, date ordering, and physical-value ranges.

The generator defaults to seed 42, 3,000 assets (20 feeders, 700 transformers,
2,280 poles), and 730 daily scenarios ending on 2025-12-31. This creates 14,600
weather records at invented feeder stations inside a Lagos-area bounding box
(3.25, 6.42, 3.55, 6.65). Coordinates describe an invented network, not real assets.
`WeatherRecord.feeder_id` is internal station identity and is not a database field.

Asset points cluster along generated feeder lines. Age and vegetation correlate;
outage probability increases with age, load stress, vegetation, rainfall, wind,
and lightning. Daily storms are shared regionally with local variation. These are
designed demonstration signals, not validated physical models or utility forecasts.
Poles have zero capacity; their load factor is a synthetic feeder-utilization proxy.

Each component uses an independent local seeded PRNG. Canonical JSON includes the
configuration, ordered records, rounded finite values, and ISO dates/timestamps.
SHA-256 identifies that complete corpus. Reproducibility targets the pinned Python
3.12 runtime. No wall clock, external network, or real-world records are inputs.

`make seed` prints `data_hash` for canonical generated records/configuration and
`database_hash` for every persisted row (including geometry) in stable ID order
with UTC timestamps. They identify different representations, so they need not
match each other. Each is stable across identical reloads. Reseeding replaces only
assets/weather/outages in one transaction and refuses to invalidate existing
model runs or risk scores. The model/risk tables remain empty in M1 demo loads.
