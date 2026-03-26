import os
from dotenv import load_dotenv
from github import Github
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("github-server")
token = os.getenv("GITHUB_TOKEN")
print(f"Token: {token}")
if not token:
    raise ValueError("GITHUB_TOKEN is not set or .env file not found")

def get_github_client() -> Github:
    token = os.getenv("GITHUB_TOKEN")
    print(f"Token: {token}")
    if not token:
        raise ValueError("GITHUB_TOKEN is not set or .env file not found")
    return Github(token)

@mcp.tool()
def get_repo_info(repo_name = "tudormunteanCS/lawgentic") -> str:
    """Get basic info about a hardcoded GitHub repo."""
    gh = get_github_client()
    repo = gh.get_repo(repo_name)
    return f"""
    Name: {repo.name}
    Description: {repo.description}
    Stars: {repo.stargazers_count}
    Forks: {repo.forks_count}
    Language: {repo.language}
    """

@mcp.tool()
def list_open_issues(repo_name = "tudormunteanCS/lawgentic") -> str:
    """List open issues for a GitHub repo. Format: 'owner/repo'"""
    gh = get_github_client()
    repo = gh.get_repo(repo_name)
    issues = repo.get_issues(state="open")
    return "\n".join([f"#{i.number}: {i.title}" for i in issues])

@mcp.tool()
def get_file_content(repo_name = "tudormunteanCS/lawgentic", file_path: str) -> str:
    """Get the content of a file from a GitHub repo."""
    gh = get_github_client()
    repo = gh.get_repo(repo_name)
    content = repo.get_contents(file_path)
    return content.decoded_content.decode("utf-8")

@mcp.tool()
def whoami() -> str:
    """Check which GitHub account the token authenticates as."""
    gh = get_github_client()
    user = gh.get_user()
    return f"Authenticated as: {user.login} ({user.name})"




    
if __name__ == "__main__":
    mcp.run()
    print("integrated confluence")