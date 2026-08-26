# Games boundary

Owns versioned Number and Color presets, palette metadata, validation,
injectable secure generation and pure evaluators. `registry.py` is the narrow
explicit adapter map used by Match orchestration; do not replace it with a
generic plugin framework. This app has no ORM model.
