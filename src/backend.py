import os
import re
import anthropic

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


def search_confluence_content(query: str) -> str:
    cf = get_confluence_client()
    results = cf.cql(f'text ~ "{query}" AND type = page', limit=5)
    pages = results.get("results", [])

    if not pages:
        return f"No pages found matching: '{query}'"

    output = []
    for p in pages:
        page_id = p["content"]["id"]
        full_page = cf.get_page_by_id(page_id, expand="body.storage")
        body = full_page["body"]["storage"]["value"]
        clean = re.sub(r"<[^>]+>", "", body).strip()[:3000]
        output.append(f"--- {full_page['title']} ---\n{clean}")

    return "\n\n".join(output)


# ---------------------------------------------------------------------------
# Tool registry — maps name → function and defines schemas for Claude
# ---------------------------------------------------------------------------

TOOL_MAP = {
    "get_repo_info": get_repo_info,
    "get_file_content": get_file_content,
    "whoami": whoami,
    "list_confluence_spaces": list_confluence_spaces,
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
        "name": "search_confluence_content",
        "description": "Search Confluence by natural language and return the full content of matching pages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"}
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
All responses should be short and concise."""


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