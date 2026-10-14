# Model card

M2 is under implementation. The prediction target is at least one outage in the
30 days beginning at a monthly UTC cutoff. Features use only strictly earlier
events and weather, with at least 365 days of available history before a cutoff.
Training, tuning, probability calibration, and final validation are chronological;
label windows crossing a partition boundary are purged. The final two months are
held out from selection and fitting.

Features include asset age, load stress, vegetation, log capacity, asset type,
trailing-year outage count, previous-30-day rainfall/wind/lightning aggregates,
weather coverage, and distance to a prior outage in the previous year. Distance is
a spherical approximation in meters, capped at 50 km with a separate missing-data
flag. Static synthetic attributes are assumed unchanged throughout the simulation.
Maintenance dates are excluded because their stored values may postdate a cutoff.
