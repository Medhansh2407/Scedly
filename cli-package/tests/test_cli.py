from unittest.mock import patch

import httpx
from click.testing import CliRunner

from scedly.cli import main


def _response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("GET", "http://localhost"),
    )


@patch("scedly.cli.get_api_key", return_value="sk-test")
@patch("scedly.cli.httpx.get")
def test_schedule_uses_calendar_range_endpoint(mock_get, _mock_key):
    mock_get.return_value = _response(
        200,
        {
            "blocks": [
                {
                    "title": "Deep work",
                    "start": "2026-01-01T09:00:00",
                    "end": "2026-01-01T10:00:00",
                }
            ]
        },
    )

    result = CliRunner().invoke(main, ["schedule"])

    assert result.exit_code == 0
    assert "09:00" in result.output
    assert mock_get.call_args.args[0].endswith("/calendar")
    assert set(mock_get.call_args.kwargs["params"]) == {"start_date", "end_date"}


@patch("scedly.cli.get_api_key", return_value="sk-test")
@patch("scedly.cli.httpx.get")
def test_tasks_flattens_grouped_api_response(mock_get, _mock_key):
    mock_get.return_value = _response(
        200,
        {
            "pending": [
                {
                    "title": "Plan week",
                    "duration_minutes": 30,
                    "priority": "High",
                    "status": "scheduled",
                }
            ],
            "in_progress": [],
            "done_this_week": [],
        },
    )

    result = CliRunner().invoke(main, ["tasks"])

    assert result.exit_code == 0
    assert "Plan week" in result.output


@patch("scedly.cli.get_api_key", return_value="sk-test")
@patch("scedly.cli.httpx.get")
def test_tasks_uses_backend_status_filter_name(mock_get, _mock_key):
    mock_get.return_value = _response(200, {"tasks": []})

    result = CliRunner().invoke(main, ["tasks", "--status", "completed"])

    assert result.exit_code == 0
    assert mock_get.call_args.kwargs["params"] == {"status_filter": "completed"}
