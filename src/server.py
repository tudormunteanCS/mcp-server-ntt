import os
import re
import html
from typing import Optional

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
    """Get high-signal metadata for a GitHub repo."""
    gh = get_github_client()
    repo = gh.get_repo(repo_name)
    description = repo.description or "No description set"
    homepage = repo.homepage or "Not set"
    topics = ", ".join(repo.get_topics()) if repo.get_topics() else "None"
    default_branch = repo.default_branch or "unknown"
    visibility = "private" if repo.private else "public"

    return f"""
    Repository: {repo.full_name}
    Description: {description}
    Visibility: {visibility}
    Primary language: {repo.language or "Unknown"}
    Default branch: {default_branch}
    Stars: {repo.stargazers_count}
    Forks: {repo.forks_count}
    Open issues: {repo.open_issues_count}
    Topics: {topics}
    Homepage: {homepage}
    URL: {repo.html_url}
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
    if isinstance(content, list):
        entries = [f"- [{item.type}] {item.path}" for item in content[:20]]
        listing = "\n".join(entries) if entries else "(empty directory)"
        return (
            f"Path '{file_path}' este un director, nu un fișier.\n"
            "Alege un fișier din listă:\n"
            f"{listing}"
        )
    try:
        return content.decoded_content.decode("utf-8")
    except UnicodeDecodeError:
        return (
            f"Fișierul '{file_path}' nu este text UTF-8 (probabil binar). "
            "Te rog dă un path către un fișier text."
        )

@mcp.tool()
def whoami() -> str:
    """Check which GitHub account the token authenticates as."""
    gh = get_github_client()
    user = gh.get_user()
    return (
        f"GitHub identity\n"
        f"- Login: {user.login}\n"
        f"- Name: {user.name or 'Not set'}\n"
        f"- Account type: {user.type}\n"
        f"- Public repos: {user.public_repos}\n"
        f"- Followers: {user.followers} | Following: {user.following}\n"
        f"- Profile: {user.html_url}\n"
        f"- Status: Token is valid"
    )

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


def _clean_html(content: str) -> str:
    """Strip HTML tags, unescape entities, and collapse whitespace."""
    if not content:
        return ""
    text = re.sub(r"<[^>]+>", " ", content)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _escape_cql(value: str) -> str:
    """Escape characters that would break a CQL string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


@mcp.tool()
def search_confluence_pages(query: str, limit: int = 10) -> str:
    """
    Lightweight search over Confluence pages. Returns a ranked list of matches
    as 'id | space | title — excerpt' (no full page bodies).
    Use this first, then call `get_confluence_page` with the chosen id to read
    the full content. Prefer this over `search_confluence_content` when you
    only need to locate the right page.
    """
    cf = get_confluence_client()
    safe = _escape_cql(query)
    results = cf.cql(f'text ~ "{safe}" AND type = page', limit=limit)
    pages = results.get("results", [])

    if not pages:
        return f"No pages found matching: '{query}'"

    lines = [f'Found {len(pages)} page(s) for "{query}"', ""]
    for idx, p in enumerate(pages, start=1):
        content = p.get("content", {}) or {}
        page_id = content.get("id", "?")
        title = content.get("title", "(untitled)")
        space_key = (
            (content.get("space") or {}).get("key")
            or (p.get("resultGlobalContainer") or {}).get("displayName")
            or "N/A"
        )
        excerpt = _clean_html(p.get("excerpt", ""))
        if len(excerpt) > 200:
            excerpt = excerpt[:200].rstrip() + "…"
        if not excerpt:
            excerpt = "No excerpt available."
        lines.append(f"[{idx}]")
        lines.append(f"ID: {page_id}")
        lines.append(f"Space: {space_key}")
        lines.append(f"Title: {title}")
        lines.append(f"Excerpt: {excerpt}")
        # separator between entries
        if idx < len(pages):
            lines.append("---")
    return "\n".join(lines)


@mcp.tool()
def get_confluence_page(page_id: str, max_chars: int = 8000) -> str:
    """
    Fetch the full cleaned content of a single Confluence page by its ID.
    Use this after `search_confluence_pages` to read the selected page and
    answer from its content. `max_chars` caps the returned text length.
    """
    cf = get_confluence_client()
    page = cf.get_page_by_id(page_id, expand="body.storage,space,version")
    if not page:
        return f"No page found with id: {page_id}"

    title = page.get("title", "(untitled)")
    space_key = (page.get("space") or {}).get("key", "")
    body = ((page.get("body") or {}).get("storage") or {}).get("value", "")
    clean = _clean_html(body)
    truncated = len(clean) > max_chars
    if truncated:
        clean = clean[:max_chars].rstrip() + "…"

    header = f"--- {title} ---"
    if space_key:
        header = f"--- [{space_key}] {title} (id={page_id}) ---"
    footer = "\n[content truncated]" if truncated else ""
    return f"{header}\n{clean}{footer}"


@mcp.tool()
def search_confluence_excerpts(query: str) -> str:
    """
    Search Confluence pages and return concise, readable excerpts with URLs.
    Use this to find documentation or implementation details without dumping full pages.
    """
    cf = get_confluence_client()
    safe = _escape_cql(query)
    results = cf.cql(f'text ~ "{safe}" AND type = page', limit=5)
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
            f"Title: {full_page['title']}\nURL: {page_url}\nExcerpt:\n{excerpt}"
        )

    return "\n\n".join(output) if output else f"No relevant excerpts found for: '{query}'"


@mcp.tool()
def get_confluence_page_by_title(title: str, space_key: Optional[str] = None) -> str:
    """
    Fetch a Confluence page by its exact title. Optionally scope the lookup to
    a single space via `space_key`.
    """
    cf = get_confluence_client()

    if space_key:
        page = cf.get_page_by_title(space=space_key, title=title, expand="body.storage,space")
        if not page:
            return f"No page titled '{title}' found in space '{space_key}'."
        return get_confluence_page(page["id"])

    safe_title = _escape_cql(title)
    results = cf.cql(f'title = "{safe_title}" AND type = page', limit=5)
    pages = results.get("results", [])
    if not pages:
        return f"No page titled '{title}' found."

    if len(pages) == 1:
        return get_confluence_page(pages[0]["content"]["id"])

    lines = ["Multiple pages match that title — call `get_confluence_page` with one of these ids:"]
    for p in pages:
        content = p.get("content", {}) or {}
        pid = content.get("id", "?")
        sp = (content.get("space") or {}).get("key", "")
        lines.append(f"{pid} | [{sp}] {content.get('title', title)}")
    return "\n".join(lines)


@mcp.tool()
def list_confluence_pages_in_space(space_key: str, limit: int = 25) -> str:
    """
    List pages in a Confluence space with useful metadata.
    Output includes: id, title, status, last update time, and page URL.
    """
    cf = get_confluence_client()

    # We use CQL because it returns rich metadata and links in one call.
    safe_space = _escape_cql(space_key)
    results = cf.cql(
        f'space = "{safe_space}" AND type = page ORDER BY title',
        limit=limit,
    )
    pages = results.get("results", [])

    if not pages:
        return f"No pages found in space '{space_key}'."

    base_url = os.getenv("CONFLUENCE_URL", "").rstrip("/")
    lines = [
        f"Space: {space_key}",
        f"Returned: {len(pages)} page(s) (limit={limit})",
        "",
    ]

    for idx, p in enumerate(pages, start=1):
        content = p.get("content", {}) or {}
        page_id = content.get("id", "?")
        title = content.get("title", "(untitled)")
        status = content.get("status", "unknown")

        version = content.get("version") or {}
        updated_at = version.get("when", "unknown")

        links = content.get("_links") or {}
        webui = links.get("webui", "")
        page_url = f"{base_url}{webui}" if base_url and webui else "URL unavailable"

        lines.append(f"[{idx}] ID: {page_id}")
        lines.append(f"Title: {title}")
        lines.append(f"Status: {status}")
        lines.append(f"Updated: {updated_at}")
        lines.append(f"URL: {page_url}")
        if idx < len(pages):
            lines.append("---")

    return "\n".join(lines)


@mcp.tool()
def search_confluence_content(
    query: str,
    limit: int = 3,
    max_chars: int = 3000,
    max_words: int = 500,
) -> str:
    """Search Confluence and return cleaned page content (with word/char truncation)."""
    cf = get_confluence_client()
    safe = _escape_cql(query)
    results = cf.cql(f'text ~ "{safe}" AND type = page', limit=limit)
    pages = results.get("results", [])
    if not pages:
        return f"No pages found matching: '{query}'"
    output = []
    for p in pages:
        page_id = p["content"]["id"]
        full_page = cf.get_page_by_id(page_id, expand="body.storage")
        body = full_page["body"]["storage"]["value"]
        clean = _clean_html(body)
        truncated = False

        words = clean.split()
        if len(words) > max_words:
            clean = " ".join(words[:max_words])
            truncated = True

        if len(clean) > max_chars:
            clean = clean[:max_chars].rstrip()
            truncated = True
        if truncated:
            clean += "… [truncated]"
        output.append(f"--- {full_page['title']} (id={page_id}) ---\n{clean}")
    return "\n\n".join(output)
    

if __name__ == "__main__":
    mcp.run(transport="stdio")