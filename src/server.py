import os
from dotenv import load_dotenv
from github import Github
from mcp.server.fastmcp import FastMCP
from atlassian import Confluence

load_dotenv()

mcp = FastMCP("github-server")
token = os.getenv("GITHUB_TOKEN")
if not token:
    raise ValueError("GITHUB_TOKEN is not set or .env file not found")

def get_github_client() -> Github:
    token = os.getenv("GITHUB_TOKEN")
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
def get_file_content(file_path: str, repo_name: str = "tudormunteanCS/lawgentic") -> str:
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


def get_confluence_client() -> Confluence:
    url = os.getenv("CONFLUENCE_URL")
    email = os.getenv("CONFLUENCE_EMAIL")
    token = os.getenv("CONFLUENCE_API_TOKEN")
    if not all([url, email, token]):
        raise ValueError("Confluence credentials not set in .env")
    return Confluence(url=url, username=email, password=token, cloud=True)

@mcp.tool()
def list_confluence_spaces() -> str:
    """List all Confluence spaces available."""
    cf = get_confluence_client()
    spaces = cf.get_all_spaces(start=0, limit=50)
    return "\n".join([f"{s['key']}: {s['name']}" for s in spaces["results"]])


@mcp.tool()
def search_confluence_content(query: str) -> str:
    """
    Search Confluence pages by natural language and return their full content.
    Use this to find explanations, documentation, or implementation details.
    """
    cf = get_confluence_client()
    
    # Step 1: Search for matching pages via CQL
    results = cf.cql(f'text ~ "{query}" AND type = page', limit=5)
    pages = results.get("results", [])
    
    if not pages:
        return f"No pages found matching: '{query}'"
    
    # Step 2: For each match, fetch the full page body
    import re
    output = []
    for p in pages:
        page_id = p["content"]["id"]
        full_page = cf.get_page_by_id(page_id, expand="body.storage")
        body = full_page["body"]["storage"]["value"]
        clean = re.sub(r"<[^>]+>", "", body).strip()
        output.append(
        f"""
        --- {full_page['title']} ---
        {clean}
        """)
    
    return "\n".join(output)
    
if __name__ == "__main__":
    mcp.run()