"""Small, retry-aware OpenAlex and Crossref API clients."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


class ApiRequestError(RuntimeError):
    """A safe, user-facing error for failed API calls."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ApiSettings:
    mailto: str
    openalex_api_key: str | None = None
    timeout_seconds: int = 60
    max_attempts: int = 6


def request_json(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    settings: ApiSettings,
) -> dict[str, Any]:
    """Fetch one JSON object, retrying transient failures with bounded backoff."""
    last_error: Exception | None = None
    for attempt in range(settings.max_attempts):
        try:
            response = session.get(url, params=params, timeout=settings.timeout_seconds)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 == settings.max_attempts:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After", "")
                delay = min(max(int(retry_after), 0), 30) if retry_after.isdigit() else min(2**attempt, 30)
                time.sleep(delay)
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ApiRequestError("API response must be a JSON object")
            return payload
        except requests.RequestException as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and status not in {429} and status < 500:
                break
            if attempt + 1 == settings.max_attempts:
                break
            time.sleep(min(2**attempt, 30))
        except ValueError as exc:
            raise ApiRequestError("API returned invalid JSON") from exc
    status = getattr(getattr(last_error, "response", None), "status_code", None)
    suffix = f" (HTTP {status})" if status else ""
    raise ApiRequestError(f"Request failed after {settings.max_attempts} attempts{suffix}", status_code=status) from last_error


class OpenAlexClient:
    def __init__(self, settings: ApiSettings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()

    def get_work(self, doi: str) -> dict[str, Any]:
        params: dict[str, Any] = {"select": "id,doi,title,publication_year,type,referenced_works"}
        if self.settings.openalex_api_key:
            params["api_key"] = self.settings.openalex_api_key
        payload = request_json(self.session, f"https://api.openalex.org/works/https://doi.org/{doi}", params, self.settings)
        return payload

    def get_reference_dois(self, work_ids: list[str]) -> dict[str, str | None]:
        missing = [item.rsplit("/", 1)[-1] for item in work_ids]
        resolved: dict[str, str | None] = {}
        for start in range(0, len(missing), 50):
            batch = missing[start : start + 50]
            params: dict[str, Any] = {
                "filter": "ids.openalex:" + "|".join(batch),
                "per-page": 50,
                "select": "id,doi",
            }
            if self.settings.openalex_api_key:
                params["api_key"] = self.settings.openalex_api_key
            payload = request_json(self.session, "https://api.openalex.org/works", params, self.settings)
            for item in payload.get("results", []):
                resolved[item.get("id", "").rsplit("/", 1)[-1]] = item.get("doi")
            for key in batch:
                resolved.setdefault(key, None)
        return resolved

    def fetch_citing_works(self, work: dict[str, Any]) -> list[dict[str, Any]]:
        work_id = str(work.get("id", "")).rsplit("/", 1)[-1]
        if not work_id:
            return []
        results: list[dict[str, Any]] = []
        cursor = "*"
        for _ in range(1000):
            params: dict[str, Any] = {
                "filter": f"cites:{work_id}",
                "per-page": 200,
                "cursor": cursor,
                "select": "id,doi,title,publication_year,type",
            }
            if self.settings.openalex_api_key:
                params["api_key"] = self.settings.openalex_api_key
            payload = request_json(self.session, "https://api.openalex.org/works", params, self.settings)
            page = payload.get("results", [])
            results.extend(item for item in page if isinstance(item, dict))
            next_cursor = payload.get("meta", {}).get("next_cursor")
            if not page or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
            time.sleep(0.05)
        else:
            raise ApiRequestError("OpenAlex citing-work pagination exceeded 1,000 pages")
        return results


class CrossrefClient:
    def __init__(self, settings: ApiSettings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": f"RefCompare/0.1.0 (mailto:{settings.mailto})"})

    def get_work(self, doi: str) -> dict[str, Any]:
        url = f"https://api.crossref.org/works/{requests.utils.quote(doi, safe='') }"
        try:
            payload = request_json(self.session, url, {"mailto": self.settings.mailto}, self.settings)
            return {"doi": doi, "status_code": 200, "message": payload.get("message", {})}
        except ApiRequestError as exc:
            return {"doi": doi, "status_code": exc.status_code, "error": str(exc)}
