"""Expected domain failures, mapped to typed HTTP responses by API routes."""


class ScoringConflict(RuntimeError):
    """A competing operation or changed corpus prevents a consistent score update."""


class ScoringDefaultsRequired(ScoringConflict):
    """Explicit consent is required before substituting missing uploaded model inputs."""


class ModelNotFound(RuntimeError):
    """No registered model has passed the required evaluation gate."""


class ModelUnavailable(RuntimeError):
    """Registered artifacts are missing, corrupt, or incompatible with this application."""
