from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = (
    PROJECT_ROOT
    / "tests"
    / "evaluation"
    / "gold"
    / "course_source_manifest_v1.json"
)
MEDIAWIKI_API = "https://fa.wikibooks.org/w/api.php"
USER_AGENT = (
    "WordCloudPhase10GoldMaterializer/1.1 "
    "(https://github.com/Amirmahdimtz/Word_Cloud) Python-urllib"
)
MAX_REQUEST_ATTEMPTS = 6
MIN_REQUEST_INTERVAL_SECONDS = 1.0
DEFAULT_RETRY_SECONDS = 5.0
MAX_RETRY_SECONDS = 60.0
_last_request_monotonic = 0.0


class CourseSourceMaterializationError(RuntimeError):
    pass


def normalize_heading(value: str) -> str:
    normalized = html.unescape(str(value))
    normalized = re.sub(r"<[^>]+>", " ", normalized)
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = normalized.replace("ي", "ی").replace("ك", "ک")
    normalized = "".join(
        " "
        if unicodedata.category(character) == "Cf"
        else character
        for character in normalized
    )
    normalized = normalized.replace("\u200c", " ")
    normalized = normalized.translate(
        str.maketrans(
            {
                "،": ",",
                "؛": ";",
                "：": ":",
                "（": "(",
                "）": ")",
            }
        )
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"\s*\(\s*", "(", normalized)
    normalized = re.sub(r"\s*\)", ")", normalized)
    normalized = re.sub(r"\s*([,:;])\s*", r"\1", normalized)
    return normalized.rstrip(":").strip()


def heading_key(value: str) -> tuple[str, ...]:
    normalized = normalize_heading(value).casefold()
    return tuple(
        token
        for token in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
        if token
    )


class _VisibleTextExtractor(HTMLParser):
    _SKIP_TAGS = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif self._skip_depth == 0 and tag in {
            "p", "br", "div", "li", "tr", "td", "th", "pre", "code",
            "h1", "h2", "h3", "h4", "h5", "h6",
        }:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif self._skip_depth == 0 and tag in {
            "p", "div", "li", "tr", "pre", "h1", "h2", "h3", "h4", "h5", "h6",
        }:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        value = html.unescape("".join(self._parts))
        value = value.replace("[ویرایش]", " ")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n[ \t]+", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def html_to_visible_text(value: str) -> str:
    parser = _VisibleTextExtractor()
    parser.feed(value)
    parser.close()
    return parser.text()


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "phase10-course-source-manifest-v1":
        raise CourseSourceMaterializationError("Unsupported COURSE source manifest schema")
    units = payload.get("units")
    if not isinstance(units, list) or len(units) != 30:
        raise CourseSourceMaterializationError("COURSE source manifest must contain exactly 30 units")
    return payload


def _retry_after_seconds(headers: Any, attempt: int) -> float:
    value = headers.get("Retry-After") if headers is not None else None
    if value is not None:
        try:
            seconds = float(value)
            if seconds >= 0:
                return seconds
        except (TypeError, ValueError):
            try:
                retry_at = parsedate_to_datetime(str(value))
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(
                    0.0,
                    (retry_at - datetime.now(timezone.utc)).total_seconds(),
                )
            except (TypeError, ValueError, OverflowError):
                pass
    return min(
        DEFAULT_RETRY_SECONDS * (2 ** attempt),
        MAX_RETRY_SECONDS,
    )


def _wait_for_request_slot() -> None:
    global _last_request_monotonic
    now = time.monotonic()
    remaining = MIN_REQUEST_INTERVAL_SECONDS - (now - _last_request_monotonic)
    if remaining > 0:
        time.sleep(remaining)
    _last_request_monotonic = time.monotonic()


def _request_json(parameters: dict[str, str | int]) -> dict[str, Any]:
    request_parameters = dict(parameters)
    request_parameters.setdefault("maxlag", 5)
    query = urllib.parse.urlencode(request_parameters)
    request = urllib.request.Request(
        f"{MEDIAWIKI_API}?{query}",
        headers={"User-Agent": USER_AGENT},
    )

    for attempt in range(MAX_REQUEST_ATTEMPTS):
        _wait_for_request_slot()
        response_headers = None
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_headers = response.headers
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 503} and attempt + 1 < MAX_REQUEST_ATTEMPTS:
                time.sleep(_retry_after_seconds(exc.headers, attempt))
                continue
            raise CourseSourceMaterializationError(
                "Failed to retrieve a pinned Persian Wikibooks revision"
            ) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt + 1 < MAX_REQUEST_ATTEMPTS:
                time.sleep(_retry_after_seconds(None, attempt))
                continue
            raise CourseSourceMaterializationError(
                "Failed to retrieve a pinned Persian Wikibooks revision"
            ) from exc

        error = payload.get("error")
        if isinstance(error, dict):
            if (
                error.get("code") == "maxlag"
                and attempt + 1 < MAX_REQUEST_ATTEMPTS
            ):
                time.sleep(_retry_after_seconds(response_headers, attempt))
                continue
            raise CourseSourceMaterializationError(
                "Persian Wikibooks API returned an error for a pinned revision"
            )
        return payload

    raise CourseSourceMaterializationError(
        "Failed to retrieve a pinned Persian Wikibooks revision after retries"
    )


@lru_cache(maxsize=32)
def _sections_for_revision(
    revision_id: int,
) -> tuple[tuple[str, str], ...]:
    payload = _request_json(
        {
            "action": "parse",
            "format": "json",
            "formatversion": 2,
            "oldid": revision_id,
            "prop": "sections",
        }
    )
    parse = payload.get("parse") or {}
    if int(parse.get("revid", 0)) != revision_id:
        raise CourseSourceMaterializationError(
            "Retrieved revision id does not match manifest"
        )
    return tuple(
        (
            normalize_heading(str(section.get("line", ""))),
            str(section["index"]),
        )
        for section in parse.get("sections", [])
    )


def _section_index(revision_id: int, section_title: str) -> str:
    wanted = heading_key(section_title)
    matches = [
        index
        for normalized_title, index in _sections_for_revision(revision_id)
        if heading_key(normalized_title) == wanted
    ]
    if len(matches) != 1:
        raise CourseSourceMaterializationError(
            "Pinned revision does not contain exactly one requested section heading"
        )
    return matches[0]


def materialize_unit(unit: dict[str, Any]) -> dict[str, Any]:
    revision_id = int(unit["revision_id"])
    section_title = str(unit["section_title"])
    index = _section_index(revision_id, section_title)
    payload = _request_json(
        {
            "action": "parse",
            "format": "json",
            "formatversion": 2,
            "oldid": revision_id,
            "section": index,
            "prop": "text",
        }
    )
    parse = payload.get("parse") or {}
    if int(parse.get("revid", 0)) != revision_id:
        raise CourseSourceMaterializationError("Retrieved section revision does not match manifest")

    raw_html = parse.get("text")
    if not isinstance(raw_html, str):
        raise CourseSourceMaterializationError("Pinned revision section did not return HTML text")
    text = html_to_visible_text(raw_html)
    minimum_chars = int(unit.get("minimum_materialized_chars", 200))
    if len(text) < minimum_chars:
        raise CourseSourceMaterializationError(
            "Materialized COURSE source section is below the minimum length"
        )

    return {
        "source_unit_id": unit["source_unit_id"],
        "case_group_id": unit["case_group_id"],
        "split": unit["split"],
        "domain": unit["domain"],
        "page_title": unit["page_title"],
        "revision_id": revision_id,
        "section_title": section_title,
        "permanent_url": unit["permanent_url"],
        "attribution_url": unit["attribution_url"],
        "license_label": (
            "Wikimedia text licensing with page-specific notices; "
            "verify applicable terms before redistribution"
        ),
        "license_policy_url": (
            "https://foundation.wikimedia.org/wiki/Terms_of_Use"
        ),
        "license_review_required_before_redistribution": True,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "character_count": len(text),
        "text": text,
    }


def materialize(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    output_path = output_path.expanduser().resolve()
    if PROJECT_ROOT.resolve() in output_path.parents:
        raise CourseSourceMaterializationError(
            "Materialized COURSE source text must be written outside the repository"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for unit in manifest["units"]:
        try:
            rows.append(materialize_unit(unit))
        except CourseSourceMaterializationError as exc:
            raise CourseSourceMaterializationError(
                f"Failed to materialize source unit {unit['source_unit_id']}: {exc}"
            ) from exc

    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    fingerprint = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return {
        "manifest_id": manifest["manifest_id"],
        "manifest_version": manifest["manifest_version"],
        "source_unit_count": len(rows),
        "tuning_unit_count": sum(row["split"] == "tuning" for row in rows),
        "holdout_unit_count": sum(row["split"] == "holdout" for row in rows),
        "materialized_file_sha256": fingerprint,
        "output_path": str(output_path),
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize pinned Persian Wikibooks COURSE source sections "
            "outside the repository for human Gold annotation."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    report = materialize(args.manifest, args.output)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
