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
