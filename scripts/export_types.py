"""Export all component and operation types from the actual OpenAPI schema."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

from scripts.openapi_types import generate_types  # noqa: E402


def main() -> None:
    """No dependencies or handwritten API contracts; unsupported schema shapes fail loudly."""
    output = generate_types(app.openapi())
    (ROOT / "frontend/src/api/generated.ts").write_text(output, encoding="utf-8")
    print("Generated frontend/src/api/generated.ts")


if __name__ == "__main__":
    main()
