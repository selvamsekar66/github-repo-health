import requests

url = "https://api.github.com/repos/selvamsekar66/sre-zero-to-hero"

response = requests.get(url)

print("Status Code:", response.status_code)

data = response.json()

print("Repository:", data["name"])
print("Description:", data["description"])
print("Stars:", data["stargazers_count"])
print("Forks:", data["forks_count"])
print("Open Issues:", data["open_issues_count"])
print("Default Branch:", data["default_branch"])