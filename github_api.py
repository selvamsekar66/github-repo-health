import requests

from config import (
    OWNER,
    REPOSITORY,
    BASE_URL,
    HEADERS
)


def get_repository():
    """Get repository information."""

    url = f"{BASE_URL}/repos/{OWNER}/{REPOSITORY}"

    response = requests.get(
        url,
        headers=HEADERS
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
        params=params
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
        params=params
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
        params=params
    )

    response.raise_for_status()

    return response.json()


def get_workflow_runs():
    """Get GitHub Actions workflow runs."""

    url = (
        f"{BASE_URL}/repos/"
        f"{OWNER}/{REPOSITORY}/actions/runs"
    )

    params = {
        "per_page": 20
    }

    response = requests.get(
        url,
        headers=HEADERS,
        params=params
    )

    response.raise_for_status()

    data = response.json()

    return data.get("workflow_runs", [])


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