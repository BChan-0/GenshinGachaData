from github import Github
import pandas as pd

TOKEN = "YOUR_GITHUB_TOKEN"

g = Github(TOKEN)

queries = [
    "uigf genshin",
    "wish history genshin",
    "genshin wishes json",
    "genshin gacha dataset"
]

rows = []

for query in queries:

    repos = g.search_repositories(query)

    for repo in repos:

        rows.append({
            "name": repo.full_name,
            "stars": repo.stargazers_count,
            "url": repo.html_url
        })

df = pd.DataFrame(rows)

df.drop_duplicates().to_csv(
    "../csv/github_repos.csv",
    index=False
)
