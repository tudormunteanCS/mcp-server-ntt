import os
import re
import html
import anthropic

from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from github import Github
from atlassian import Confluence

load_dotenv()

app = FastAPI(title="Law-Agent Internal Tool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this to your frontend URL in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

def get_github_client() -> Github:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN is not set")
    return Github(token)


def get_confluence_client() -> Confluence:
    url = os.getenv("CONFLUENCE_URL")
    email = os.getenv("CONFLUENCE_EMAIL")
    token = os.getenv("CONFLUENCE_API_TOKEN")
    if not all([url, email, token]):
        raise ValueError("Confluence credentials not set in .env")
    return Confluence(url=url, username=email, password=token, cloud=True)


def get_anthropic_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# Tool implementations  (plain functions, no MCP decorator needed)
# ---------------------------------------------------------------------------

def get_repo_info(repo_name: str = "tudormunteanCS/Law-Agent") -> str:
    gh = get_github_client()
    repo = gh.get_repo(repo_name)
    return (
        f"Name: {repo.name}\n"
        f"Description: {repo.description}\n"
        f"Stars: {repo.stargazers_count}\n"
        f"Forks: {repo.forks_count}\n"
        f"Language: {repo.language}"
    )



def get_file_content(file_path: str, repo_name: str = "tudormunteanCS/Law-Agent") -> str:
    gh = get_github_client()
    repo = gh.get_repo(repo_name)
    content = repo.get_contents(file_path)
    return content.decoded_content.decode("utf-8")


def whoami() -> str:
    gh = get_github_client()
    user = gh.get_user()
    return f"Authenticated as: {user.login} ({user.name})"


def list_confluence_spaces() -> str:
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
    return value.replace("\\", "\\\\").replace('"', '\\"')


def search_confluence_pages(query: str, limit: int = 10) -> str:
    cf = get_confluence_client()
    safe = _escape_cql(query)
    results = cf.cql(f'text ~ "{safe}" AND type = page', limit=limit)
    pages = results.get("results", [])

    if not pages:
        return f"No pages found matching: '{query}'"

    lines = []
    for p in pages:
        content = p.get("content", {}) or {}
        page_id = content.get("id", "?")
        title = content.get("title", "(untitled)")
        space_key = (content.get("space") or {}).get("key") or (p.get("resultGlobalContainer") or {}).get("displayName", "")
        excerpt = _clean_html(p.get("excerpt", ""))
        if len(excerpt) > 240:
            excerpt = excerpt[:240].rstrip() + "…"
        space_part = f"[{space_key}] " if space_key else ""
        lines.append(f"{page_id} | {space_part}{title}" + (f" — {excerpt}" if excerpt else ""))

    return "\n".join(lines)


def get_confluence_page(page_id: str, max_chars: int = 8000) -> str:
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

    header = f"--- [{space_key}] {title} (id={page_id}) ---" if space_key else f"--- {title} ---"
    footer = "\n[content truncated]" if truncated else ""
    return f"{header}\n{clean}{footer}"


def get_confluence_page_by_title(title: str, space_key: Optional[str] = None) -> str:
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

    lines = ["Multiple pages match that title — call get_confluence_page with one of these ids:"]
    for p in pages:
        content = p.get("content", {}) or {}
        pid = content.get("id", "?")
        sp = (content.get("space") or {}).get("key", "")
        lines.append(f"{pid} | [{sp}] {content.get('title', title)}")
    return "\n".join(lines)


def list_confluence_pages_in_space(space_key: str, limit: int = 25) -> str:
    cf = get_confluence_client()
    pages = cf.get_all_pages_from_space(space_key, start=0, limit=limit)
    if not pages:
        return f"No pages found in space '{space_key}'."
    return "\n".join(f"{p['id']} | {p['title']}" for p in pages)


def search_confluence_content(query: str, limit: int = 3, max_chars: int = 3000) -> str:
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
        if len(clean) > max_chars:
            clean = clean[:max_chars].rstrip() + "…"
        output.append(f"--- {full_page['title']} (id={page_id}) ---\n{clean}")

    return "\n\n".join(output)


# ---------------------------------------------------------------------------
# Tool registry — maps name → function and defines schemas for Claude
# ---------------------------------------------------------------------------

TOOL_MAP = {
    "get_repo_info": get_repo_info,
    "get_file_content": get_file_content,
    "whoami": whoami,
    "list_confluence_spaces": list_confluence_spaces,
    "list_confluence_pages_in_space": list_confluence_pages_in_space,
    "search_confluence_pages": search_confluence_pages,
    "get_confluence_page": get_confluence_page,
    "get_confluence_page_by_title": get_confluence_page_by_title,
    "search_confluence_content": search_confluence_content,
}

TOOLS = [
    {
        "name": "get_repo_info",
        "description": "Get basic info about a GitHub repo: name, description, stars, forks, and language.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo_name": {
                    "type": "string",
                    "description": "GitHub repo in owner/repo format. Defaults to tudormunteanCS/Law-Agent.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_file_content",
        "description": "Read the full content of a file from a GitHub repo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file, e.g. src/main.py"},
                "repo_name": {
                    "type": "string",
                    "description": "GitHub repo in owner/repo format. Defaults to tudormunteanCS/Law-Agent.",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "whoami",
        "description": "Check which GitHub account the server is authenticated as.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_confluence_spaces",
        "description": "List all Confluence spaces the account has access to.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_confluence_pages",
        "description": (
            "Lightweight Confluence search. Returns a ranked list of matches as "
            "'id | [space] title — excerpt' with NO full page bodies. Use this "
            "first to locate the right page, then call get_confluence_page with "
            "the chosen id to read its content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords or natural-language search terms"},
                "limit": {"type": "integer", "description": "Max number of results (default 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_confluence_page",
        "description": (
            "Fetch the full cleaned content of a single Confluence page by its "
            "id. Use this after search_confluence_pages to read the selected "
            "page and answer strictly from its content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "The Confluence page id"},
                "max_chars": {"type": "integer", "description": "Cap on returned characters (default 8000)"},
            },
            "required": ["page_id"],
        },
    },
    {
        "name": "get_confluence_page_by_title",
        "description": (
            "Fetch a Confluence page by its exact title. Optionally scope the "
            "lookup to a single space via space_key. Returns the cleaned full "
            "content, or a list of candidate ids if the title is ambiguous."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Exact page title"},
                "space_key": {"type": "string", "description": "Optional space key to scope the lookup, e.g. 'ENG'"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "list_confluence_pages_in_space",
        "description": (
            "List pages in a Confluence space as 'id | title'. Useful when "
            "search queries don't match well and you want to browse a space. "
            "Get space keys from list_confluence_spaces."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "space_key": {"type": "string", "description": "Confluence space key, e.g. 'ENG'"},
                "limit": {"type": "integer", "description": "Max number of pages to list (default 25)"},
            },
            "required": ["space_key"],
        },
    },
    {
        "name": "search_confluence_content",
        "description": (
            "Heavy Confluence search: returns the full cleaned content of "
            "several matching pages at once. Prefer search_confluence_pages + "
            "get_confluence_page for concise answers; use this only when you "
            "truly need to compare multiple pages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "limit": {"type": "integer", "description": "Max number of pages to include (default 3)"},
                "max_chars": {"type": "integer", "description": "Per-page character cap (default 3000)"},
            },
            "required": ["query"],
        },
    },
]

SYSTEM_PROMPT = """You are an internal assistant for the Law-Agent engineering team.
You can ONLY answer questions related to the team's GitHub repository and Confluence documentation.
If a question is unrelated to GitHub or Confluence, politely decline and explain your scope.
Always use the available tools to fetch live data — never make up repo details or documentation content.
When you are asked to search Confluence, you can only search the lawgentic documentation.
When you are asked to search GitHub, you can only search the repository with the value: tudormunteanCS/Law-Agent

Confluence tool strategy (prefer this order):
1. Call `search_confluence_pages` to find candidate pages (returns ids + titles + excerpts, no bodies).
2. Pick the single most relevant id and call `get_confluence_page` to read its full content.
3. If the user gives an exact page title, use `get_confluence_page_by_title` instead.
4. Use `list_confluence_spaces` / `list_confluence_pages_in_space` when search doesn't find a good match.
5. Only fall back to `search_confluence_content` (heavy) when comparing several pages is genuinely needed.
Answer strictly from the fetched page(s). All responses should be short and concise."""


# ---------------------------------------------------------------------------
# Agentic loop — handles multi-step tool calling
# ---------------------------------------------------------------------------

def run_agent(user_message: str) -> str:
    client = get_anthropic_client()
    messages = [{"role": "user", "content": user_message}]

    while True:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # If Claude is done, return the final text response
        if response.stop_reason == "end_turn":
            return next(
                (block.text for block in response.content if hasattr(block, "text")),
                "No response generated.",
            )

        # If Claude wants to call tools, execute them all and loop back
        if response.stop_reason == "tool_use":
            # Append Claude's response (with tool_use blocks) to messages
            messages.append({"role": "assistant", "content": response.content})

            # Execute every tool Claude requested
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    try:
                        fn = TOOL_MAP[block.name]
                        result = fn(**block.input)
                    except Exception as e:
                        result = f"Error running {block.name}: {str(e)}"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            # Feed results back to Claude and continue the loop
            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason
        break

    return "Something went wrong in the agent loop."


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    try:
        answer = run_agent(request.message)
        return ChatResponse(response=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend:app", host="0.0.0.0", port=8001, reload=True)