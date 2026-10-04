from __future__ import annotations

import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


_DEFAULT_READINESS_URL = "http://api:5000/api/v1/health/ready"
_DEFAULT_TIMEOUT_SECONDS = 5.0


def _is_healthy() -> bool:
    try:
        os.kill(1, 0)
    except (OSError, PermissionError):
        return False

    readiness_url = os.getenv(
        "WORKER_READINESS_URL",
        _DEFAULT_READINESS_URL,
    ).strip()
    if not readiness_url:
        return False

    request = Request(
        readiness_url,
        headers={"Host": "localhost"},
        method="GET",
    )
    try:
        with urlopen(
            request,
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        ) as response:
            return response.status == 200
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def main() -> None:
    raise SystemExit(0 if _is_healthy() else 1)


if __name__ == "__main__":
    main()
