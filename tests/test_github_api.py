from datetime import datetime, timedelta, timezone

import pytest
import requests

import github_api
from github_api import (
    calculate_actions_health,
    calculate_issue_health,
    calculate_open_pr_aging,
    calculate_pr_health,
    calculate_pr_merge_time,
    calculate_workflow_duration_metrics,
    get_pr_metrics_data,
    get_workflow_run_jobs,
    get_workflow_runs,
)


NOW = datetime(2025, 4, 1, tzinfo=timezone.utc)


def timestamp(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


def open_pr(number, days_ago, **overrides):
    pr = {
        "number": number,
        "title": f"PR {number}",
        "state": "open",
        "draft": False,
        "created_at": timestamp(days_ago),
        "html_url": f"https://github.com/example/repo/pull/{number}",
    }
    pr.update(overrides)
    return pr


def merged_pr(number, duration_days, merged_days_ago=1, **overrides):
    merged_at = NOW - timedelta(days=merged_days_ago)
    pr = {
        "number": number,
        "state": "closed",
        "created_at": (merged_at - timedelta(days=duration_days)).isoformat(),
        "closed_at": merged_at.isoformat(),
        "merged_at": merged_at.isoformat(),
    }
    pr.update(overrides)
    return pr


def test_open_pr_age_uses_created_at_and_returns_oldest_first():
    result = calculate_open_pr_aging(
        [
            open_pr(1, 2, updated_at=timestamp(100)),
            open_pr(2, 10),
        ],
        now=NOW,
    )

    assert result["valid_age_count"] == 2
    assert result["oldest_open_prs"][0]["number"] == 2
    assert result["oldest_open_prs"][0]["age_days"] == 10
    assert result["oldest_open_prs"][1]["age_days"] == 2


@pytest.mark.parametrize(
    ("age_days", "category"),
    [
        (0, "0-2 days"),
        (2, "0-2 days"),
        (3, "3-7 days"),
        (7, "3-7 days"),
        (8, "8-14 days"),
        (14, "8-14 days"),
        (15, "15+ days"),
    ],
)
def test_age_category_boundaries_are_exhaustive(age_days, category):
    result = calculate_open_pr_aging([open_pr(1, age_days)], now=NOW)

    assert result["category_counts"][category] == 1
    assert sum(result["category_counts"].values()) == 1


def test_open_aging_handles_invalid_future_timestamps_and_empty_data():
    result = calculate_open_pr_aging(
        [
            open_pr(1, 0, created_at=None),
            open_pr(2, 0, created_at="not-a-date"),
            open_pr(3, 0, created_at="2025-03-31T00:00:00"),
            open_pr(4, -1),
        ],
        now=NOW,
    )
    empty = calculate_open_pr_aging([], now=NOW)

    assert result["open_pr_count"] == 4
    assert result["invalid_timestamp_count"] == 4
    assert result["valid_age_count"] == 0
    assert sum(result["category_counts"].values()) == 0
    assert result["oldest_open_prs"] == []
    assert empty["open_pr_count"] == 0
    assert empty["oldest_open_prs"] == []


def test_merge_time_includes_only_valid_recent_merges():
    prs = [
        merged_pr(1, 1),
        merged_pr(2, 2),
        merged_pr(3, 3),
        {
            "number": 4,
            "state": "closed",
            "created_at": timestamp(4),
            "merged_at": None,
        },
        merged_pr(5, 4, merged_days_ago=91),
    ]

    result = calculate_pr_merge_time(prs, now=NOW, window_days=90)

    assert result["sample_size"] == 3
    assert result["median_days"] == 2
    assert result["p75_days"] == 2.5
    assert result["window_days"] == 90


def test_merge_time_requires_valid_nonnegative_timestamps():
    result = calculate_pr_merge_time(
        [
            merged_pr(1, 1, created_at="invalid"),
            merged_pr(2, 1, created_at="2025-03-30T00:00:00"),
            {
                "number": 3,
                "created_at": timestamp(1),
                "merged_at": timestamp(2),
            },
            merged_pr(4, 1, merged_at=None),
        ],
        now=NOW,
    )

    assert result["sample_size"] == 0
    assert result["median_days"] is None
    assert result["p75_days"] is None


def test_merge_time_returns_unavailable_for_empty_data():
    result = calculate_pr_merge_time([], now=NOW)

    assert result["sample_size"] == 0
    assert result["median_days"] is None
    assert result["p75_days"] is None


def test_duplicate_pr_numbers_are_counted_once():
    duplicate_open = open_pr(1, 2, title="duplicate")
    aging = calculate_open_pr_aging(
        [open_pr(1, 2), duplicate_open],
        now=NOW,
    )
    merging = calculate_pr_merge_time(
        [merged_pr(2, 1), merged_pr(2, 9)],
        now=NOW,
    )

    assert aging["open_pr_count"] == 1
    assert aging["oldest_open_prs"][0]["title"] == "PR 1"
    assert merging["sample_size"] == 1
    assert merging["median_days"] == 1


def test_api_retrieves_bounded_pages_with_expected_parameters(monkeypatch):
    pages = {
        ("open", 1): [{"number": 1}, {"number": 2}],
        ("open", 2): [{"number": 3}],
        ("closed", 1): [{"number": 4}, {"number": 5}],
        ("closed", 2): [],
    }
    calls = []

    class Response:
        def __init__(self, records):
            self.records = records

        def raise_for_status(self):
            pass

        def json(self):
            return self.records

    def fake_get(url, headers, params, timeout):
        calls.append((url, headers, params, timeout))
        return Response(pages[(params["state"], params["page"])])

    monkeypatch.setattr(github_api.requests, "get", fake_get)
    result = get_pr_metrics_data(max_pages=3, per_page=2)

    assert [pr["number"] for pr in result["open_pull_requests"]] == [1, 2, 3]
    assert [pr["number"] for pr in result["closed_pull_requests"]] == [4, 5]
    assert result["closed_sample_limit"] == 6
    assert len(calls) == 4
    assert all(call[2]["sort"] == "updated" for call in calls)
    assert all(call[2]["direction"] == "desc" for call in calls)
    assert all(call[2]["per_page"] == 2 for call in calls)
    assert all(call[3] == github_api.REQUEST_TIMEOUT_SECONDS for call in calls)


def test_api_projects_fields_deduplicates_and_stops_at_page_limit(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return [
                {
                    "number": 1,
                    "title": "Title",
                    "state": "open",
                    "draft": False,
                    "created_at": timestamp(1),
                    "closed_at": None,
                    "merged_at": None,
                    "html_url": "https://github.com/example/repo/pull/1",
                    "body": "not retained",
                }
            ]

    def fake_get(url, headers, params, timeout):
        calls.append(params)
        return Response()

    monkeypatch.setattr(github_api.requests, "get", fake_get)
    result = get_pr_metrics_data(max_pages=3, per_page=100)

    assert len(calls) == 2
    assert result["open_pull_requests"][0]["number"] == 1
    assert "body" not in result["open_pull_requests"][0]


def test_api_deduplicates_records_across_pages(monkeypatch):
    calls = []
    record = {
        "number": 1,
        "title": "First copy",
        "state": "open",
        "draft": False,
        "created_at": timestamp(1),
    }
    duplicate = {**record, "title": "Duplicate copy"}

    class Response:
        def __init__(self, records):
            self.records = records

        def raise_for_status(self):
            pass

        def json(self):
            return self.records

    def fake_get(url, headers, params, timeout):
        calls.append(params)
        if params["state"] == "open":
            return Response({1: [record], 2: [duplicate], 3: []}[params["page"]])
        return Response([])

    monkeypatch.setattr(github_api.requests, "get", fake_get)
    result = get_pr_metrics_data(max_pages=3, per_page=1)

    assert len(result["open_pull_requests"]) == 1
    assert result["open_pull_requests"][0]["title"] == "First copy"
    assert [call["page"] for call in calls[:3]] == [1, 2, 3]


@pytest.mark.parametrize(
    "invalid",
    [
        {"max_pages": 4, "per_page": 100},
        {"max_pages": 0, "per_page": 100},
        {"max_pages": 1, "per_page": 101},
    ],
)
def test_api_rejects_unbounded_pagination(invalid):
    with pytest.raises(ValueError):
        get_pr_metrics_data(**invalid)


def test_api_rejects_unexpected_response(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"workflow_runs": []}

    monkeypatch.setattr(
        github_api.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    with pytest.raises(ValueError, match="unexpected pull request response"):
        get_pr_metrics_data(max_pages=1, per_page=100)


def test_api_http_errors_propagate_for_dashboard_handling(monkeypatch):
    error = requests.HTTPError("rate limit")

    class Response:
        def raise_for_status(self):
            raise error

        def json(self):
            return []

    monkeypatch.setattr(
        github_api.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    with pytest.raises(type(error)):
        get_pr_metrics_data(max_pages=1, per_page=100)


def test_api_timeout_is_explicit_and_propagates(monkeypatch):
    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append(timeout)
        raise requests.Timeout("timed out")

    monkeypatch.setattr(github_api.requests, "get", fake_get)

    with pytest.raises(requests.Timeout):
        get_pr_metrics_data(max_pages=1, per_page=100)
    assert calls == [github_api.REQUEST_TIMEOUT_SECONDS]


def test_existing_pr_issue_and_actions_metrics_keep_their_definitions():
    pr_health = calculate_pr_health(
        [
            {"state": "open", "merged_at": None},
            {"state": "closed", "merged_at": "2025-01-01T00:00:00Z"},
            {"state": "closed", "merged_at": None},
        ]
    )
    issue_health = calculate_issue_health(
        [{"state": "open"}, {"state": "closed"}, {"state": "closed"}]
    )
    actions_health = calculate_actions_health(
        [
            {"status": "completed", "conclusion": "success"},
            {"status": "completed", "conclusion": "failure"},
            {"status": "queued", "conclusion": None},
            {"status": "completed", "conclusion": "cancelled"},
        ]
    )

    assert pr_health == {
        "total": 3,
        "open": 1,
        "closed": 2,
        "merged": 1,
        "unmerged": 1,
    }
    assert issue_health == {"total": 3, "open": 1, "closed": 2}
    assert actions_health == {
        "total": 4,
        "successful": 1,
        "failed": 1,
        "in_progress": 1,
        "success_rate": 50.0,
    }


def test_workflow_duration_summary_uses_completed_job_time_spans():
    workflow_runs = [
        {"id": 1, "status": "completed"},
        {"id": 2, "status": "completed"},
        {"id": 3, "status": "completed"},
        {"id": 4, "status": "completed"},
        {"id": 5, "status": "in_progress"},
        {"id": 6, "status": "completed"},
    ]
    jobs = {
        "1": [
            {
                "started_at": timestamp(0),
                "completed_at": (NOW + timedelta(seconds=60)).isoformat(),
            }
        ],
        "2": [
            {
                "started_at": timestamp(0),
                "completed_at": (NOW + timedelta(seconds=120)).isoformat(),
            }
        ],
        "3": [
            {
                "started_at": timestamp(0),
                "completed_at": (NOW + timedelta(seconds=180)).isoformat(),
            }
        ],
        "4": [
            {
                "started_at": timestamp(0),
                "completed_at": (NOW + timedelta(seconds=240)).isoformat(),
            }
        ],
        "5": [
            {
                "started_at": timestamp(0),
                "completed_at": (NOW + timedelta(seconds=900)).isoformat(),
            }
        ],
        "6": [
            {"started_at": timestamp(0), "completed_at": None},
            {"started_at": "malformed", "completed_at": timestamp(0)},
            {
                "started_at": (NOW + timedelta(seconds=30)).isoformat(),
                "completed_at": NOW.isoformat(),
            },
        ],
    }

    result = calculate_workflow_duration_metrics(workflow_runs, jobs)

    assert result["sample_size"] == 4
    assert result["average_seconds"] == 150
    assert result["median_seconds"] == 150
    assert result["p90_seconds"] == 222
    assert result["durations_by_run_id"] == {
        "1": 60,
        "2": 120,
        "3": 180,
        "4": 240,
    }


def test_workflow_duration_uses_earliest_start_and_latest_completion():
    result = calculate_workflow_duration_metrics(
        [{"id": 12, "status": "completed"}],
        {
            "12": [
                {
                    "started_at": (NOW + timedelta(seconds=10)).isoformat(),
                    "completed_at": (NOW + timedelta(seconds=80)).isoformat(),
                },
                {
                    "started_at": NOW.isoformat(),
                    "completed_at": (NOW + timedelta(seconds=60)).isoformat(),
                },
            ]
        },
    )

    assert result["durations_by_run_id"]["12"] == 80


def test_workflow_duration_is_unavailable_when_no_valid_completed_jobs():
    result = calculate_workflow_duration_metrics(
        [{"id": 1, "status": "in_progress"}, {"id": 2, "status": "completed"}],
        {"2": [{"started_at": None, "completed_at": None}]},
    )

    assert result["sample_size"] == 0
    assert result["average_seconds"] is None
    assert result["median_seconds"] is None
    assert result["p90_seconds"] is None
    assert result["durations_by_run_id"] == {}


def test_workflow_runs_are_fetched_with_bounded_pagination_and_timeout(monkeypatch):
    calls = []

    class Response:
        def __init__(self, runs):
            self.runs = runs

        def raise_for_status(self):
            pass

        def json(self):
            return {"workflow_runs": self.runs}

    def fake_get(url, headers, params, timeout):
        calls.append((url, params, timeout))
        if params["page"] == 1:
            return Response([{"id": run_id} for run_id in range(20)])
        return Response([{"id": 20}])

    monkeypatch.setattr(github_api.requests, "get", fake_get)
    result = get_workflow_runs()

    assert len(result) == 21
    assert [call[1]["page"] for call in calls] == [1, 2]
    assert all(call[1]["per_page"] == 20 for call in calls)
    assert all(call[2] == github_api.REQUEST_TIMEOUT_SECONDS for call in calls)


def test_workflow_jobs_are_paginated_and_timeout_is_set(monkeypatch):
    calls = []

    class Response:
        def __init__(self, jobs):
            self.jobs = jobs

        def raise_for_status(self):
            pass

        def json(self):
            return {"jobs": self.jobs}

    def fake_get(url, headers, params, timeout):
        calls.append((url, params, timeout))
        if params["page"] == 1:
            return Response([{"id": 1} for _ in range(100)])
        return Response([{"id": 101}])

    monkeypatch.setattr(github_api.requests, "get", fake_get)
    result = get_workflow_run_jobs(123)

    assert len(result) == 101
    assert "/actions/runs/123/jobs" in calls[0][0]
    assert [call[1]["page"] for call in calls] == [1, 2]
    assert all(call[1]["per_page"] == 100 for call in calls)
    assert all(call[2] == github_api.REQUEST_TIMEOUT_SECONDS for call in calls)
