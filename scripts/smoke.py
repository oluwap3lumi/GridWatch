"""HTTP and real PostGIS smoke checks for the running M0 stack."""

import json
import os
import subprocess
from urllib.request import urlopen


def main() -> None:
    """Verify both health paths, the browser entry point, proxy, and PostGIS."""
    api = f"http://localhost:{os.getenv('API_PORT', '8000')}"
    web = f"http://localhost:{os.getenv('WEB_PORT', '5173')}"
    for url in (f"{api}/health", f"{api}/api/v1/health", f"{web}/api/v1/health"):
        with urlopen(url, timeout=10) as response:
            assert response.status == 200
            assert json.load(response) == {"status": "ok"}
        print(f"PASS {url}")
    with urlopen(web, timeout=10) as response:
        assert response.status == 200
        assert 'id="root"' in response.read().decode()
    print(f"PASS {web} entry point")
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT PostGIS_Version()"',
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip().startswith("3.")
    print(f"PASS PostGIS: {result.stdout.strip()}")


if __name__ == "__main__":
    main()
