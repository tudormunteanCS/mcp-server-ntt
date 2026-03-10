import os
from dotenv import load_dotenv
from github import Github
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("github-server")
token = os.getenv("GITHUB_TOKEN")
gh = Github(token)

@mcp.tool()
def get_repo_info(repo_name: str) -> str:
    """Get basic info about a GitHub repo. Format: 'owner/repo'"""
    repo = gh.get_repo(repo_name)
    return f"""
    Name: {repo.name}
    Description: {repo.description}
    Stars: {repo.stargazers_count}
    Forks: {repo.forks_count}
    Language: {repo.language}
    """

@mcp.tool()
def list_open_issues(repo_name: str) -> str:
    """List open issues for a GitHub repo. Format: 'owner/repo'"""
    repo = gh.get_repo(repo_name)
    issues = repo.get_issues(state="open")
    return "\n".join([f"#{i.number}: {i.title}" for i in issues])

@mcp.tool()
def get_file_content(repo_name: str, file_path: str) -> str:
    """Get the content of a file from a GitHub repo."""
    repo = gh.get_repo(repo_name)
    content = repo.get_contents(file_path)
    return content.decoded_content.decode("utf-8")

if __name__ == "__main__":
    mcp.run()