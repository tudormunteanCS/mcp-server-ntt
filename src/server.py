import os
import re

from atlassian import Confluence
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from github import Github
from mcp.server.fastmcp import FastMCP

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
def get_repo_info(repo_name = "tudormunteanCS/Law-Agent") -> str:
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
def list_open_issues(repo_name = "tudormunteanCS/Law-Agent") -> str:
    """List open issues for a GitHub repo. Format: 'owner/repo'"""
    gh = get_github_client()
    repo = gh.get_repo(repo_name)
    issues = repo.get_issues(state="open")
    return "\n".join([f"#{i.number}: {i.title}" for i in issues])

@mcp.tool()
def get_file_content(file_path: str, repo_name: str = "tudormunteanCS/Law-Agent") -> str:
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


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    non_empty_lines = [line for line in lines if line]
    return "\n".join(non_empty_lines)


def _best_excerpt(text: str, query: str, max_chars: int = 600) -> str:
    normalized_query = query.strip().lower()
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    if not paragraphs:
        return text[:max_chars].strip()

    def score(paragraph: str) -> tuple[int, int]:
        lower = paragraph.lower()
        occurrences = lower.count(normalized_query) if normalized_query else 0
        # Prefer shorter relevant chunks over huge page dumps.
        return (occurrences, -abs(len(paragraph) - 350))

    ranked = sorted(paragraphs, key=score, reverse=True)
    best = ranked[0]
    if normalized_query and normalized_query not in best.lower():
        for paragraph in paragraphs:
            if normalized_query in paragraph.lower():
                best = paragraph
                break

    if len(best) <= max_chars:
        return best

    if normalized_query:
        match = re.search(re.escape(normalized_query), best, flags=re.IGNORECASE)
        if match:
            start = max(0, match.start() - (max_chars // 2))
            end = min(len(best), start + max_chars)
            snippet = best[start:end].strip()
            if start > 0:
                snippet = "..." + snippet
            if end < len(best):
                snippet = snippet + "..."
            return snippet

    return best[:max_chars].strip() + "..."

@mcp.tool()
def list_confluence_spaces() -> str:
    """List all Confluence spaces available."""
    cf = get_confluence_client()
    spaces = cf.get_all_spaces(start=0, limit=50)
    return "\n".join([f"{s['key']}: {s['name']}" for s in spaces["results"]])


@mcp.tool()
def search_confluence_content(query: str) -> str:
    """
    Search Confluence pages and return concise, readable excerpts.
    Use this to find documentation or implementation details without dumping full pages.
    """
    cf = get_confluence_client()

    escaped_query = query.replace('"', '\\"')
    results = cf.cql(f'text ~ "{escaped_query}" AND type = page', limit=5)
    pages = results.get("results", [])

    if not pages:
        return f"No relevant Confluence pages found for query: '{query}'"

    output = []
    for p in pages:
        page_id = p["content"]["id"]
        full_page = cf.get_page_by_id(page_id, expand="body.storage")
        body = full_page["body"]["storage"]["value"]
        clean = _html_to_text(body)
        excerpt = _best_excerpt(clean, query)
        webui = full_page.get("_links", {}).get("webui", "")
        base_url = os.getenv("CONFLUENCE_URL", "").rstrip("/")
        page_url = f"{base_url}{webui}" if webui and base_url else "URL unavailable"

        if len(excerpt) < 40:
            continue

        output.append(
            "\n".join(
                [
                    f"Title: {full_page['title']}",
                    f"URL: {page_url}",
                    "Excerpt:",
                    excerpt,
                ]
            )
        )

    if not output:
        return f"No relevant Confluence pages found for query: '{query}'"

    return "\n".join(output)
    
if __name__ == "__main__":
    mcp.run()