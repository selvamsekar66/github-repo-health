from datetime import datetime, timedelta, timezone
from statistics import median

import requests

from config import (
    OWNER,
    REPOSITORY,
    BASE_URL,
    HEADERS
)

REQUEST_TIMEOUT_SECONDS = 10
WORKFLOW_RUNS_PER_PAGE = 20
WORKFLOW_RUN_MAX_PAGES = 2
WORKFLOW_JOBS_PER_PAGE = 100
WORKFLOW_JOBS_MAX_PAGES = 2
PR_METRICS_PER_PAGE = 100
PR_METRICS_MAX_PAGES = 3
PR_MERGE_WINDOW_DAYS = 90
OLDEST_OPEN_PR_LIMIT = 10
PR_METRIC_FIELDS = (
    "number",
    "title",
    "state",
    "draft",
    "created_at",
    "closed_at",
    "merged_at",
    "html_url",
)


def get_repository():
    """Get repository information."""

    url = f"{BASE_URL}/repos/{OWNER}/{REPOSITORY}"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT_SECONDS
    )

    response.raise_for_status()

    return response.json()


def get_pull_requests():
    """Get pull requests."""

    url = f"{BASE_URL}/repos/{OWNER}/{REPOSITORY}/pulls"

    params = {
        "state": "all",
        "per_page": 100
    }

    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS
    )

    response.raise_for_status()

    return response.json()


def get_issues():
    """Get issues excluding pull requests."""

    url = f"{BASE_URL}/repos/{OWNER}/{REPOSITORY}/issues"

    params = {
        "state": "all",
        "per_page": 100
    }

    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS
    )

    response.raise_for_status()

    issues = response.json()

    # GitHub returns pull requests through
    # the Issues API as well.
    actual_issues = [
        issue
        for issue in issues
        if "pull_request" not in issue
    ]

    return actual_issues


def get_commits():
    """Get recent commits."""

    url = f"{BASE_URL}/repos/{OWNER}/{REPOSITORY}/commits"

    params = {
        "per_page": 10
    }

    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS
    )

    response.raise_for_status()

    return response.json()


def get_workflow_runs(max_pages=WORKFLOW_RUN_MAX_PAGES):
    """Get a bounded, paginated sample of recent GitHub Actions runs."""
    if not isinstance(max_pages, int) or not 1 <= max_pages <= WORKFLOW_RUN_MAX_PAGES:
        raise ValueError(
            f"max_pages must be between 1 and {WORKFLOW_RUN_MAX_PAGES}."
        )
    url = (
        f"{BASE_URL}/repos/"
        f"{OWNER}/{REPOSITORY}/actions/runs"
    )
    workflow_runs = []
    for page in range(1, max_pages + 1):
        response = requests.get(
            url,
            headers=HEADERS,
            params={"per_page": WORKFLOW_RUNS_PER_PAGE, "page": page},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not isinstance(
            data.get("workflow_runs"), list
        ):
            raise ValueError("GitHub returned an unexpected workflow runs response.")
        page_runs = data["workflow_runs"]
        if any(not isinstance(run, dict) for run in page_runs):
            raise ValueError("GitHub returned an invalid workflow run record.")
        workflow_runs.extend(page_runs)
        if len(page_runs) < WORKFLOW_RUNS_PER_PAGE:
            break
    return workflow_runs


def get_workflow_run_jobs(run_id, max_pages=WORKFLOW_JOBS_MAX_PAGES):
    """Get a bounded sample of jobs for a workflow run."""
    if not isinstance(max_pages, int) or not 1 <= max_pages <= WORKFLOW_JOBS_MAX_PAGES:
        raise ValueError(
            f"max_pages must be between 1 and {WORKFLOW_JOBS_MAX_PAGES}."
        )

    url = f"{BASE_URL}/repos/{OWNER}/{REPOSITORY}/actions/runs/{run_id}/jobs"
    jobs = []
    for page in range(1, max_pages + 1):
        response = requests.get(
            url,
            headers=HEADERS,
            params={"per_page": WORKFLOW_JOBS_PER_PAGE, "page": page},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise ValueError("GitHub returned an unexpected workflow jobs response.")
        page_jobs = data["jobs"]
        if any(not isinstance(job, dict) for job in page_jobs):
            raise ValueError("GitHub returned an invalid workflow job record.")
        jobs.extend(page_jobs)
        if len(page_jobs) < WORKFLOW_JOBS_PER_PAGE:
            break
    return jobs


def calculate_workflow_duration_metrics(workflow_runs, jobs_by_run_id):
    """Summarize completed workflow durations from their job time intervals.

    A workflow duration is the elapsed span from its earliest valid job start
    to its latest valid job completion; queued time is not included.
    """
    durations_by_run_id = {}
    for run in workflow_runs:
        if not isinstance(run, dict) or run.get("status") != "completed":
            continue
        run_id = run.get("id")
        if not isinstance(run_id, (int, str)) or isinstance(run_id, bool):
            continue

        jobs = jobs_by_run_id.get(str(run_id), [])
        if not isinstance(jobs, list):
            continue
        valid_intervals = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            started_at = _parse_aware_timestamp(job.get("started_at"))
            completed_at = _parse_aware_timestamp(job.get("completed_at"))
            if (
                started_at is None
                or completed_at is None
                or completed_at < started_at
            ):
                continue
            valid_intervals.append((started_at, completed_at))

        if valid_intervals:
            start = min(interval[0] for interval in valid_intervals)
            completion = max(interval[1] for interval in valid_intervals)
            durations_by_run_id[str(run_id)] = (
                completion - start
            ).total_seconds()

    durations = sorted(durations_by_run_id.values())
    p90_seconds = None
    if durations:
        p90_index = (len(durations) - 1) * 0.9
        lower_index = int(p90_index)
        upper_index = min(lower_index + 1, len(durations) - 1)
        fraction = p90_index - lower_index
        p90_seconds = durations[lower_index] + (
            durations[upper_index] - durations[lower_index]
        ) * fraction

    return {
        "sample_size": len(durations),
        "average_seconds": sum(durations) / len(durations) if durations else None,
        "median_seconds": median(durations) if durations else None,
        "p90_seconds": p90_seconds,
        "durations_by_run_id": durations_by_run_id,
    }


def _get_pr_metrics_page(state, page, per_page):
    """Fetch one PR page and retain only fields used by the metrics."""
    url = f"{BASE_URL}/repos/{OWNER}/{REPOSITORY}/pulls"
    params = {
        "state": state,
        "sort": "updated",
        "direction": "desc",
        "per_page": per_page,
        "page": page,
    }
    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError("GitHub returned an unexpected pull request response.")
    if any(not isinstance(pr, dict) for pr in data):
        raise ValueError("GitHub returned an invalid pull request record.")
    return [
        {field: pr.get(field) for field in PR_METRIC_FIELDS}
        for pr in data
    ]


def _get_paginated_pr_metrics(state, max_pages, per_page):
    """Fetch at most max_pages of PR records for a given state."""
    if not isinstance(max_pages, int) or not 1 <= max_pages <= PR_METRICS_MAX_PAGES:
        raise ValueError(f"max_pages must be between 1 and {PR_METRICS_MAX_PAGES}.")
    if not isinstance(per_page, int) or not 1 <= per_page <= PR_METRICS_PER_PAGE:
        raise ValueError(f"per_page must be between 1 and {PR_METRICS_PER_PAGE}.")

    records = []
    for page in range(1, max_pages + 1):
        page_records = _get_pr_metrics_page(state, page, per_page)
        records.extend(page_records)
        if len(page_records) < per_page:
            break
    return deduplicate_pull_requests(records)


def deduplicate_pull_requests(pull_requests):
    """Keep the first record for each valid PR number."""
    unique = []
    seen = set()
    for pr in pull_requests:
        if not isinstance(pr, dict):
            continue
        number = pr.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or number in seen:
            continue
        seen.add(number)
        unique.append(pr)
    return unique


def get_pr_metrics_data(
    max_pages=PR_METRICS_MAX_PAGES,
    per_page=PR_METRICS_PER_PAGE,
):
    """Fetch bounded open PRs and recently updated closed PRs for v2 metrics.

    GitHub's PR listing endpoint cannot filter by merge date. The closed
    sample is therefore ordered by recent updates and limited to max_pages.
    """
    open_prs = _get_paginated_pr_metrics("open", max_pages, per_page)
    closed_prs = _get_paginated_pr_metrics("closed", max_pages, per_page)
    return {
        "open_pull_requests": open_prs,
        "closed_pull_requests": closed_prs,
        "closed_sample_limit": max_pages * per_page,
    }


def _parse_aware_timestamp(value):
    """Parse an ISO timestamp only when it includes a timezone."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _as_utc(now):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware.")
    return now.astimezone(timezone.utc)


def calculate_open_pr_aging(pull_requests, now=None, oldest_limit=OLDEST_OPEN_PR_LIMIT):
    """Calculate open PR ages and configurable age buckets.

    Bucket boundaries use completed 24-hour days: 0-2, 3-7, 8-14, and 15+.
    Invalid or future creation timestamps are omitted from age statistics.
    """
    if not isinstance(oldest_limit, int) or oldest_limit < 0:
        raise ValueError("oldest_limit must be a non-negative integer.")

    current_time = _as_utc(now)
    open_prs = [
        pr for pr in deduplicate_pull_requests(pull_requests)
        if pr.get("state") == "open"
    ]
    category_counts = {
        "0-2 days": 0,
        "3-7 days": 0,
        "8-14 days": 0,
        "15+ days": 0,
    }
    aged_prs = []
    invalid_timestamp_count = 0

    for pr in open_prs:
        created_at = _parse_aware_timestamp(pr.get("created_at"))
        if created_at is None or created_at > current_time:
            invalid_timestamp_count += 1
            continue

        age_days = (current_time - created_at).total_seconds() / 86400
        completed_days = int(age_days)
        if completed_days <= 2:
            category = "0-2 days"
        elif completed_days <= 7:
            category = "3-7 days"
        elif completed_days <= 14:
            category = "8-14 days"
        else:
            category = "15+ days"
        category_counts[category] += 1
        aged_prs.append({
            "number": pr["number"],
            "title": pr.get("title") or "",
            "age_days": age_days,
            "draft": pr.get("draft") is True,
            "html_url": pr.get("html_url") or "",
        })

    aged_prs.sort(key=lambda pr: (-pr["age_days"], pr["number"]))
    return {
        "open_pr_count": len(open_prs),
        "valid_age_count": len(aged_prs),
        "invalid_timestamp_count": invalid_timestamp_count,
        "category_counts": category_counts,
        "oldest_open_prs": aged_prs[:oldest_limit],
    }


def calculate_pr_merge_time(
    pull_requests,
    now=None,
    window_days=PR_MERGE_WINDOW_DAYS,
):
    """Calculate median and linearly interpolated P75 PR time-to-merge.

    Only valid merged_at timestamps in the inclusive trailing window count.
    """
    if not isinstance(window_days, int) or window_days <= 0:
        raise ValueError("window_days must be a positive integer.")

    current_time = _as_utc(now)
    window_start = current_time - timedelta(days=window_days)
    durations = []

    for pr in deduplicate_pull_requests(pull_requests):
        created_at = _parse_aware_timestamp(pr.get("created_at"))
        merged_at = _parse_aware_timestamp(pr.get("merged_at"))
        if created_at is None or merged_at is None:
            continue
        if merged_at < window_start or merged_at > current_time:
            continue
        duration_seconds = (merged_at - created_at).total_seconds()
        if duration_seconds < 0:
            continue
        durations.append(duration_seconds / 86400)

    durations.sort()
    p75_days = None
    if durations:
        p75_index = (len(durations) - 1) * 0.75
        lower_index = int(p75_index)
        upper_index = min(lower_index + 1, len(durations) - 1)
        fraction = p75_index - lower_index
        p75_days = durations[lower_index] + (
            durations[upper_index] - durations[lower_index]
        ) * fraction

    return {
        "sample_size": len(durations),
        "median_days": median(durations) if durations else None,
        "p75_days": p75_days,
        "window_days": window_days,
        "window_start": window_start.isoformat(),
        "window_end": current_time.isoformat(),
    }


def calculate_pr_health(pull_requests):
    """Calculate pull request metrics."""

    total = len(pull_requests)

    open_prs = sum(
        1
        for pr in pull_requests
        if pr["state"] == "open"
    )

    closed_prs = sum(
        1
        for pr in pull_requests
        if pr["state"] == "closed"
    )

    merged_prs = sum(
        1
        for pr in pull_requests
        if pr["merged_at"] is not None
    )

    unmerged_prs = closed_prs - merged_prs

    return {
        "total": total,
        "open": open_prs,
        "closed": closed_prs,
        "merged": merged_prs,
        "unmerged": unmerged_prs
    }


def calculate_issue_health(issues):
    """Calculate issue metrics."""

    total = len(issues)

    open_issues = sum(
        1
        for issue in issues
        if issue["state"] == "open"
    )

    closed_issues = sum(
        1
        for issue in issues
        if issue["state"] == "closed"
    )

    return {
        "total": total,
        "open": open_issues,
        "closed": closed_issues
    }


def calculate_actions_health(workflow_runs):
    """Calculate GitHub Actions metrics."""

    successful = sum(
        1
        for run in workflow_runs
        if run["conclusion"] == "success"
    )

    failed = sum(
        1
        for run in workflow_runs
        if run["conclusion"] == "failure"
    )

    in_progress = sum(
        1
        for run in workflow_runs
        if run["status"] in [
            "queued",
            "in_progress"
        ]
    )

    completed = successful + failed

    if completed > 0:
        success_rate = (
            successful / completed
        ) * 100
    else:
        success_rate = 0

    return {
        "total": len(workflow_runs),
        "successful": successful,
        "failed": failed,
        "in_progress": in_progress,
        "success_rate": success_rate
    }


def calculate_repository_health(
    pr_health,
    issue_health,
    actions_health
):
    """Determine overall repository health."""

    reasons = []

    if pr_health["open"] > 0:
        reasons.append(
            f"{pr_health['open']} open pull request(s)"
        )

    if issue_health["open"] > 0:
        reasons.append(
            f"{issue_health['open']} open issue(s)"
        )

    if actions_health["failed"] > 0:
        reasons.append(
            f"{actions_health['failed']} failed workflow run(s)"
        )

    if reasons:
        status = "NEEDS ATTENTION"
    else:
        status = "HEALTHY"

    return {
        "status": status,
        "reasons": reasons
    }


def get_workflow_details(workflow_runs):
    """Extract useful details from workflow runs."""

    workflow_details = []

    for run in workflow_runs:

        workflow_details.append({
            "name": run["name"],
            "branch": run["head_branch"],
            "status": run["status"],
            "conclusion": run["conclusion"],
            "created_at": run["created_at"],
            "updated_at": run["updated_at"]
        })

    return workflow_details


def display_report(
    repository,
    pr_health,
    issue_health,
    commits,
    actions_health,
    repository_health,
    workflow_details
):
    """Display repository health report."""

    print()
    print("=" * 45)
    print("       GITHUB REPOSITORY HEALTH")
    print("=" * 45)

    print(
        "Repository Health:",
        repository_health["status"]
    )

    if repository_health["reasons"]:
        print("\nAttention Required:")

        for reason in repository_health["reasons"]:
            print("-", reason)

    print("\nRepository")
    print("-" * 45)

    print("Name:", repository["name"])
    print("Stars:", repository["stargazers_count"])
    print("Forks:", repository["forks_count"])

    print(
        "Default Branch:",
        repository["default_branch"]
    )

    print("\nPull Requests")
    print("-" * 45)

    print("Total:", pr_health["total"])
    print("Open:", pr_health["open"])
    print("Closed:", pr_health["closed"])
    print("Merged:", pr_health["merged"])
    print("Unmerged:", pr_health["unmerged"])

    print("\nIssues")
    print("-" * 45)

    print("Total:", issue_health["total"])
    print("Open:", issue_health["open"])
    print("Closed:", issue_health["closed"])

    print("\nCommit Activity")
    print("-" * 45)

    print("Recent Commits:", len(commits))

    print("\nGitHub Actions")
    print("-" * 45)

    print(
        "Workflow Runs:",
        actions_health["total"]
    )

    print(
        "Successful:",
        actions_health["successful"]
    )

    print(
        "Failed:",
        actions_health["failed"]
    )

    print(
        "In Progress:",
        actions_health["in_progress"]
    )

    print(
        "CI Success Rate:",
        f"{actions_health['success_rate']:.1f}%"
    )

    print("\nRecent Workflow Runs")
    print("-" * 45)

    for workflow in workflow_details[:5]:

        print("Workflow:", workflow["name"])
        print("Branch:", workflow["branch"])
        print("Status:", workflow["status"])
        print("Conclusion:", workflow["conclusion"])
        print("Updated:", workflow["updated_at"])
        print()

    print("=" * 45)


def main():
    """Run the repository health application."""

    repository = get_repository()

    pull_requests = get_pull_requests()

    issues = get_issues()

    commits = get_commits()

    workflow_runs = get_workflow_runs()

    pr_health = calculate_pr_health(
        pull_requests
    )

    issue_health = calculate_issue_health(
        issues
    )

    actions_health = calculate_actions_health(
        workflow_runs
    )

    repository_health = calculate_repository_health(
        pr_health,
        issue_health,
        actions_health
    )

    workflow_details = get_workflow_details(
        workflow_runs
    )

    display_report(
        repository,
        pr_health,
        issue_health,
        commits,
        actions_health,
        repository_health,
        workflow_details
    )


if __name__ == "__main__":
    main()