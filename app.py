import html
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

from config import OWNER, REPOSITORY
from github_api import (
    get_repository,
    get_pull_requests,
    get_issues,
    get_commits,
    get_workflow_runs,
    calculate_pr_health,
    calculate_issue_health,
    calculate_actions_health,
)

st.write("GitHub token loaded:", bool(os.getenv("GITHUB_TOKEN")))

st.set_page_config(
    page_title="RepoPulse | Engineering Intelligence",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
:root {color-scheme: dark;}
.stApp {background: #0b1220; color: #e2e8f0;}
[data-testid="stHeader"] {background: #0b1220;}
[data-testid="stSidebar"] {background: #111c30; border-right: 1px solid #27344b;}
.block-container {max-width: 1550px; padding-top: 1.4rem; padding-bottom: 2.5rem;}
h1, h2, h3, p {color: #e2e8f0;}
[data-testid="stMetric"] {background: #172338; border: 1px solid #2b3b55; padding: 1rem 1.2rem; border-radius: 14px; min-height: 115px;}
[data-testid="stMetricLabel"] {color: #94a3b8;}
[data-testid="stMetricValue"] {color: #f8fafc; font-weight: 750;}
[data-testid="stDataFrame"] {border: 1px solid #2b3b55; border-radius: 12px; overflow: hidden;}
[data-testid="stAlert"] {border-radius: 12px;}
div.stButton > button {border: 1px solid #2563eb; background: #1d4ed8; color: white; border-radius: 10px; font-weight: 600;}
div.stButton > button:hover {background: #2563eb; color: white; border-color: #60a5fa;}
.hero {background: linear-gradient(110deg,#172b4a,#12213a 58%,#102d38); border: 1px solid #2c4664; border-radius: 20px; padding: 1.5rem 1.8rem; margin-bottom: 1rem;}
.eyebrow {color:#38bdf8; font-size:.75rem; font-weight:800; letter-spacing:.15em; margin-bottom:.45rem;}
.hero-title {font-size:2.05rem; line-height:1.2; font-weight:800; color:#f8fafc; margin:0 0 .4rem 0;}
.hero-sub {color:#a8bed4; font-size:.95rem; margin:0;}
.section-title {color:#f1f5f9; font-size:1.13rem; font-weight:750; margin:1.35rem 0 .65rem;}
.pill {display:inline-block; padding:.35rem .7rem; border-radius:100px; font-size:.78rem; font-weight:750; margin:.15rem .35rem .25rem 0;}
.pill-green {background:#123e34; color:#6ee7b7; border:1px solid #216a56;}
.pill-amber {background:#47341a; color:#fcd34d; border:1px solid #866128;}
.pill-blue {background:#19395d; color:#93c5fd; border:1px solid #275e99;}
.pill-red {background:#4b222a; color:#fca5a5; border:1px solid #85404a;}
.panel {background:#172338; border:1px solid #2b3b55; border-radius:14px; padding:1rem 1.2rem; margin:.3rem 0 .7rem;}
.panel-title {font-size:.8rem; color:#94a3b8; font-weight:700; letter-spacing:.04em;}
.panel-big {font-size:1.65rem; font-weight:800; color:#f8fafc; margin:.3rem 0;}
.panel-foot {font-size:.78rem; color:#a8bed4;}
a {color:#7dd3fc !important;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=120, show_spinner=False)
def load_data():
    """Cache GitHub responses for two minutes to reduce repeated API calls."""
    return {
        "repository": get_repository(),
        "pull_requests": get_pull_requests(),
        "issues": get_issues(),
        "commits": get_commits(),
        "workflow_runs": get_workflow_runs(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def readable_time(timestamp):
    if not timestamp:
        return "—"
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime("%d %b %Y · %H:%M UTC")
    except (ValueError, AttributeError):
        return "—"


def section(text):
    st.markdown(f'<div class="section-title">{html.escape(text)}</div>', unsafe_allow_html=True)


with st.sidebar:
    st.markdown("## 📡 RepoPulse")
    st.caption("Engineering intelligence / v1.0")
    st.divider()
    st.caption("MONITORED REPOSITORY")
    st.code(f"{OWNER}/{REPOSITORY}", language=None)
    if st.button("↻ Refresh GitHub data", use_container_width=True):
        load_data.clear()
        st.rerun()
    st.caption("Data cache: 120 seconds. Refresh clears the cache.")
    st.divider()
    st.markdown("**Data sources**")
    st.caption("GitHub REST API · Pull Requests · Issues · Commits · Actions")
    st.divider()
    st.caption("Repository health is a configurable engineering assessment, not a service availability SLO.")

try:
    with st.spinner("Fetching GitHub repository data..."):
        data = load_data()
except requests.exceptions.RequestException as exc:
    st.error("Unable to retrieve GitHub data. Check network access, repository permissions, and API credentials.")
    with st.expander("Technical details"):
        st.code(str(exc))
    st.stop()
except Exception as exc:
    st.error("Unable to load the dashboard. Review the terminal output and configuration.")
    with st.expander("Technical details"):
        st.code(str(exc))
    st.stop()

repository = data["repository"]
prs = data["pull_requests"]
issues = data["issues"]
commits = data["commits"]
runs = data["workflow_runs"]
pr_health = calculate_pr_health(prs)
issue_health = calculate_issue_health(issues)
actions_health = calculate_actions_health(runs)

# An open PR is normal engineering activity, not a reliability incident.
# Treat failed CI runs and open issues as attention signals for this starter app.
# These are heuristic indicators, not a production SLO or a DORA metric.
attention = []
if actions_health["failed"]:
    attention.append(f'{actions_health["failed"]} failed workflow run(s) in the fetched sample')
if issue_health["open"]:
    attention.append(f'{issue_health["open"]} open issue(s) to triage')
assessment = "REVIEW NEEDED" if attention else "NO FLAGS DETECTED"
assessment_class = "pill-amber" if attention else "pill-green"
repo_url = repository.get("html_url") or f"https://github.com/{OWNER}/{REPOSITORY}"

st.markdown(
    '<div class="hero">'
    '<div class="eyebrow">REPOPULSE / ENGINEERING INTELLIGENCE</div>'
    '<div class="hero-title">Repository Command Center</div>'
    '<p class="hero-sub">GitHub delivery, CI/CD and engineering activity in one view.</p>'
    '</div>',
    unsafe_allow_html=True,
)
left, right = st.columns([3, 1], vertical_alignment="center")
with left:
    st.markdown(f"**Repository:** [{OWNER}/{REPOSITORY}]({repo_url})")
with right:
    st.caption(f"Updated: {readable_time(data['fetched_at'])}")

section("Operational overview")
a, b, c, d = st.columns(4)
with a:
    st.metric("CI success (sample)", f'{actions_health["success_rate"]:.1f}%' if actions_health["successful"] + actions_health["failed"] else "N/A")
with b:
    st.metric("Open pull requests", pr_health["open"])
with c:
    st.metric("Open issues", issue_health["open"])
with d:
    st.metric("Recent commits fetched", len(commits))

st.markdown(
    f'<span class="pill {assessment_class}">{html.escape(assessment)}</span>'
    '<span class="pill pill-blue">Live GitHub API · 2-minute cache</span>',
    unsafe_allow_html=True,
)
if attention:
    st.warning(" · ".join(attention))
else:
    st.info("No issues or failed CI runs detected in the fetched sample. This does not establish production service health.")

section("Delivery and CI/CD")
left, right = st.columns(2, gap="medium")
with left:
    st.markdown('<div class="panel"><div class="panel-title">PULL REQUEST FLOW</div><div class="panel-big">' + str(pr_health["merged"]) + ' merged</div><div class="panel-foot">' + str(pr_health["open"]) + ' open · ' + str(pr_health["unmerged"]) + ' closed without merge · ' + str(pr_health["total"]) + ' fetched PRs</div></div>', unsafe_allow_html=True)
    st.progress(pr_health["merged"] / pr_health["total"] if pr_health["total"] else 0, text="Merged share of fetched PRs")
with right:
    st.markdown('<div class="panel"><div class="panel-title">GITHUB ACTIONS</div><div class="panel-big">' + str(actions_health["successful"]) + ' successful</div><div class="panel-foot">' + str(actions_health["failed"]) + ' failed · ' + str(actions_health["in_progress"]) + ' in progress · ' + str(actions_health["total"]) + ' fetched runs</div></div>', unsafe_allow_html=True)
    completed = actions_health["successful"] + actions_health["failed"]
    st.progress(actions_health["successful"] / completed if completed else 0, text=f"Success share of {completed} success/failure runs" if completed else "No success/failure runs")

section("Recent pull requests")
pr_rows = [
    {
        "PR": f'#{pr.get("number", "?")}',
        "Title": pr.get("title", ""),
        "State": "Merged" if pr.get("merged_at") else ("Open" if pr.get("state") == "open" else "Closed"),
        "Branch": (pr.get("head") or {}).get("ref", "—"),
        "Updated (UTC)": readable_time(pr.get("updated_at")),
        "GitHub": pr.get("html_url", ""),
    }
    for pr in prs[:10]
]
if pr_rows:
    st.dataframe(
        pd.DataFrame(pr_rows),
        hide_index=True,
        use_container_width=True,
        column_config={"GitHub": st.column_config.LinkColumn("Open PR", display_text="View ↗")},
    )
else:
    st.info("No pull requests found in the fetched sample.")

section("Recent workflow runs")
run_rows = [
    {
        "Workflow": run.get("name") or "Unnamed workflow",
        "Branch": run.get("head_branch") or "—",
        "Status": run.get("status") or "—",
        "Result": (run.get("conclusion") or "pending").upper(),
        "Updated (UTC)": readable_time(run.get("updated_at")),
        "GitHub": run.get("html_url", ""),
    }
    for run in runs[:10]
]
if run_rows:
    st.dataframe(
        pd.DataFrame(run_rows),
        hide_index=True,
        use_container_width=True,
        column_config={"GitHub": st.column_config.LinkColumn("Open run", display_text="View ↗")},
    )
else:
    st.info("No GitHub Actions workflow runs found.")

section("Recent engineering activity")
commit_rows = []
for commit in commits[:10]:
    details = commit.get("commit") or {}
    author = details.get("author") or {}
    commit_rows.append({
        "Commit": (details.get("message") or "").splitlines()[0],
        "Author": author.get("name") or "Unknown",
        "Committed (UTC)": readable_time(author.get("date")),
        "GitHub": commit.get("html_url", ""),
    })
if commit_rows:
    st.dataframe(
        pd.DataFrame(commit_rows),
        hide_index=True,
        use_container_width=True,
        column_config={"GitHub": st.column_config.LinkColumn("Open commit", display_text="View ↗")},
    )
else:
    st.info("No recent commits found.")

with st.expander("About these metrics and limitations"):
    st.markdown(
        "- **CI success rate** = successful runs / (successful + failed runs) in the fetched sample. "
        "Cancelled, skipped and pending runs are excluded from this denominator.\n"
        "- **Pull requests, issues, commits and workflow runs** are limited by the existing API fetch sizes "
        "(100 PRs, 100 issue records, 10 commits, 20 workflow runs); pagination is not yet implemented.\n"
        "- **Assessment** is a simple triage indicator based on fetched open issues and failed workflow runs. "
        "Open PRs alone are not treated as unhealthy.\n"
        "- **Not measured:** production uptime, SLO compliance, deployment frequency, lead time, change failure rate or MTTR."
    )

st.divider()
st.caption("RepoPulse v1.0 · Python · GitHub REST API · Streamlit · SRE learning project")
