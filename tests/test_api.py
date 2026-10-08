from unittest.mock import Mock

import pytest
import requests

from refcompare.api import ApiRequestError, ApiSettings, request_json


def test_request_json_retries_429_then_returns_payload(monkeypatch):
    monkeypatch.setattr("refcompare.api.time.sleep", lambda _: None)
    session = Mock(spec=requests.Session)
    session.get.side_effect = [Mock(status_code=429, headers={"Retry-After": "0"}), Mock(status_code=200, json=lambda: {"ok": True})]
    assert request_json(session, "https://example.test", {}, ApiSettings("a@example.org")) == {"ok": True}
    assert session.get.call_count == 2


def test_request_json_does_not_retry_not_found():
    session = Mock(spec=requests.Session)
    response = Mock(status_code=404)
    response.raise_for_status.side_effect = requests.HTTPError("404", response=response)
    session.get.return_value = response
    with pytest.raises(ApiRequestError) as error:
        request_json(session, "https://example.test", {}, ApiSettings("a@example.org"))
    assert session.get.call_count == 1
    assert error.value.status_code == 404
