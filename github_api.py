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