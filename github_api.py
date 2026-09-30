import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("GITHUB_TOKEN")

owner = "selvamsekar66"
repo = "sre-zero-to-hero"

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10"
}


# -----------------------------------
# Repository Information
# -----------------------------------

repo_url = f"https://api.github.com/repos/{owner}/{repo}"

response = requests.get(repo_url, headers=headers)

print("Repository API Status:", response.status_code)

repo_data = response.json()

print("\nRepository Information")
print("----------------------")
print("Repository:", repo_data["name"])
print("Stars:", repo_data["stargazers_count"])
print("Forks:", repo_data["forks_count"])
print("Open Issues:", repo_data["open_issues_count"])
print("Default Branch:", repo_data["default_branch"])


# -----------------------------------
# Pull Request Information
# -----------------------------------

pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"

params = {
    "state": "all",
    "per_page": 10
}

pr_response = requests.get(
    pr_url,
    headers=headers,
    params=params
)

print("\nPull Request API Status:", pr_response.status_code)

pull_requests = pr_response.json()

print("\nPull Request Health")
print("-------------------")

total_prs = len(pull_requests)

open_prs = sum(
    1 for pr in pull_requests
    if pr["state"] == "open"
)

closed_prs = sum(
    1 for pr in pull_requests
    if pr["state"] == "closed"
)

merged_prs = sum(
    1 for pr in pull_requests
    if pr["merged_at"] is not None
)

unmerged_prs = closed_prs - merged_prs

print("Total PRs:", total_prs)
print("Open PRs:", open_prs)
print("Closed PRs:", closed_prs)
print("Merged PRs:", merged_prs)
print("Unmerged PRs:", unmerged_prs)

# -----------------------------------
# Issue Information
# -----------------------------------

issues_url = f"https://api.github.com/repos/{owner}/{repo}/issues"

issue_params = {
    "state": "all",
    "per_page": 100
}

issues_response = requests.get(
    issues_url,
    headers=headers,
    params=issue_params
)

print("\nIssues API Status:", issues_response.status_code)

issues_data = issues_response.json()

# GitHub returns pull requests through the Issues API.
# We exclude them because we only want actual issues.

actual_issues = [
    issue for issue in issues_data
    if "pull_request" not in issue
]

open_issues = sum(
    1 for issue in actual_issues
    if issue["state"] == "open"
)

closed_issues = sum(
    1 for issue in actual_issues
    if issue["state"] == "closed"
)

total_issues = len(actual_issues)

print("\nIssue Health")
print("------------")
print("Total Issues:", total_issues)
print("Open Issues:", open_issues)
print("Closed Issues:", closed_issues)


# -----------------------------------
# Commit Activity
# -----------------------------------

commits_url = f"https://api.github.com/repos/{owner}/{repo}/commits"

commit_params = {
    "per_page": 10
}

commits_response = requests.get(
    commits_url,
    headers=headers,
    params=commit_params
)

print("\nCommits API Status:", commits_response.status_code)

commits_data = commits_response.json()

print("\nRecent Commit Activity")
print("----------------------")

print("Recent Commits:", len(commits_data))

for commit in commits_data:
    sha = commit["sha"][:7]
    message = commit["commit"]["message"].split("\n")[0]
    author = commit["commit"]["author"]["name"]

    print(f"{sha} | {author} | {message}")