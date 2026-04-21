import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from src.server import (
    get_file_content,
    get_repo_info,
    list_confluence_spaces,
    list_open_issues,
    search_confluence_content,
    whoami,
)

load_dotenv()

DEFAULT_REPO = "tudormunteanCS/Law-Agent"

try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
except ImportError:
    openai_client = None

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Message]] = []

class ChatResponse(BaseModel):
    tool: str
    response: str
    history: Optional[List[Dict[str, str]]] = None

app = FastAPI(title="MCP Agent Web Chat")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")

def _extract_repo_name(text: str) -> str:
    match = re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", text)
    return match.group(1) if match else DEFAULT_REPO

def _extract_file_path(text: str) -> str | None:
    quoted = re.findall(r'"([^"]+)"', text)
    if quoted:
        return quoted[0]
    single = re.findall(r"'([^']+)'", text)
    if single:
        return single[0]
    path_like = re.search(r"\b[\w./-]+\.[A-Za-z0-9]+\b", text)
    return path_like.group(0) if path_like else None

def route_message_fallback(message: str) -> tuple[str, str]:
    lower = message.lower()
    if "who am i" in lower or "whoami" in lower or "authenticated as" in lower:
        return "whoami", whoami()
    if "confluence spaces" in lower or ("list spaces" in lower and "confluence" in lower):
        return "list_confluence_spaces", list_confluence_spaces()
    if "confluence" in lower or "search docs" in lower or "documentation" in lower:
        query = message
        if "confluence" in lower:
            query = re.sub(r"(?i)\bconfluence\b", "", message).strip() or message
        return "search_confluence_content", search_confluence_content(query=query)
    if "open issues" in lower or "issues" in lower:
        repo = _extract_repo_name(message)
        return "list_open_issues", list_open_issues(repo_name=repo) or f"No open issues found for {repo}."
    if "repo info" in lower or "repository info" in lower or "describe repo" in lower:
        repo = _extract_repo_name(message)
        return "get_repo_info", get_repo_info(repo_name=repo)
    if "file content" in lower or "read file" in lower or "show file" in lower:
        repo = _extract_repo_name(message)
        file_path = _extract_file_path(message)
        if not file_path:
            return ("helper", "Please provide a file path, e.g.: Show file README.md from tudormunteanCS/Law-Agent")
        return "get_file_content", get_file_content(file_path=file_path, repo_name=repo)

    return ("helper", "Without OPENAI_API_KEY, I can only run basic commands: whoami, repo info, open issues, file content, confluence search.")

def call_llm(message: str, history: List[Message]) -> tuple[str, str, List[Dict[str, str]]]:
    if not openai_client:
        tool, resp = route_message_fallback(message)
        return tool, resp, [{"role": "user", "content": message}, {"role": "assistant", "content": resp}]
        
    tools = [
        {
            "type": "function",
            "function": {
                "name": "whoami",
                "description": "Check which GitHub account the token authenticates as."
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_repo_info",
                "description": "Get basic info about a GitHub repo.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_name": {"type": "string", "description": "Owner and repo name, e.g. tudormunteanCS/Law-Agent"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_open_issues",
                "description": "List open issues for a GitHub repo.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_name": {"type": "string", "description": "Owner and repo name, e.g. tudormunteanCS/Law-Agent"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_file_content",
                "description": "Get the content of a file from a GitHub repo.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the file to read."},
                        "repo_name": {"type": "string", "description": "Owner and repo name, e.g. tudormunteanCS/Law-Agent"}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_confluence_spaces",
                "description": "List all Confluence spaces available."
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_confluence_content",
                "description": "Search Confluence pages and return concise, readable excerpts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query."}
                    },
                    "required": ["query"]
                }
            }
        }
    ]

    messages = [{"role": "system", "content": "You are a helpful assistant with access to GitHub and Confluence tools. Answer the user's questions clearly."}]
    for h in history:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": message})
    
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    
    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls
    
    used_tool = "llm"
    if tool_calls:
        messages.append(response_message)
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
            used_tool = function_name
            function_response = "Error calling tool."
            
            try:
                if function_name == "whoami":
                    function_response = whoami()
                elif function_name == "get_repo_info":
                    function_response = get_repo_info(args.get("repo_name", DEFAULT_REPO))
                elif function_name == "list_open_issues":
                    function_response = list_open_issues(args.get("repo_name", DEFAULT_REPO))
                elif function_name == "get_file_content":
                    function_response = get_file_content(args.get("file_path", ""), args.get("repo_name", DEFAULT_REPO))
                elif function_name == "list_confluence_spaces":
                    function_response = list_confluence_spaces()
                elif function_name == "search_confluence_content":
                    function_response = search_confluence_content(args.get("query", ""))
            except Exception as e:
                function_response = str(e)
            
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": str(function_response),
            })
            
        second_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
        )
        final_answer = second_response.choices[0].message.content
        return used_tool, final_answer, [{"role": "user", "content": message}, {"role": "assistant", "content": final_answer}]
    
    final_answer = response_message.content or "No response from model."
    return used_tool, final_answer, [{"role": "user", "content": message}, {"role": "assistant", "content": final_answer}]


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        tool, response, new_history = call_llm(payload.message, payload.history)
        return ChatResponse(tool=tool, response=response, history=new_history)
    except Exception as exc:
        return ChatResponse(
            tool="error",
            response=f"Tool execution failed: {type(exc).__name__}: {exc}",
        )
