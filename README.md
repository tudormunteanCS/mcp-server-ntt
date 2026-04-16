This content is hand-written - not AI generated.

How to run the project

1. Make sure that you are in root folder opened as workspace folder in cursor
2. Create a ".env" file containing:
    GITHUB_TOKEN=github_pat_11B....
3. Make sure to run "uv sync" so your venv is synced with the latest dependencies from the pyproject.toml file


How to test the tools locally - Just their raw tool calling output.

Method 1 (raw output of the tools)
    npx @modelcontextprotocol/inspector uv run src/server.py

Method 2 (structured content modeled by built-in Cursor agent) - be careful with the prompts, free version of
cursor may be dummier.
    You do not have to run the server.py in order to prompt the agent.
    !!! After modifying server.py you have to reload the process of server.py using (Ctrl/CMD + Shift + P)
        and select the Developer: Reload Window.

How to check that you mcp server is actually up and running.
    Go to Settings -> Tools & MCP -> Check that "github-server" has a green mark and you can check the tools that the server has access to.



You can run in cursor agent the next prompt that shows that confluence is integrated:
    "Search confluence to find the lawgentic documentation and fetch me the story about the pig"

---------------------
Tested Tools

`Who am I authentificated as?`
Authenticated as: tudormunteanCS (Muntean Tudor)

`Get repo info for tudormunteanCS/Law-Agent*`
Name: Law-Agent
Description: None
Stars: 0
Forks: 0
Language: Python

`List Confluence spaces`
~7120206dc0765a1fbe4a2c9c46af95e637a359: Darius Toasca
~6411ee036b29c052ab2c9bbb: Robert Barbulescu
SD: Software development
~712020cc8a634f65b74ee3b1dd1af89ef2fb47: Tudor Muntean

`Search Confluence for 'pig'`
--- Lawgentic - documentation ---
Polymorphism for lawgentic:A pig is like a tale, a pig can have tail and not be pale.

`Search Confluence for 'architecture'`
Conversational RAG agent for Romanian legislation, built on Flask + Qdrant + OpenAI...

The search results are noisy and need polishing to provide more concise and organised answers.

`List open issues for tudormunteanCS/Law-Agent`
<empty string> - this one is usable but noisy, the fix would be an output like "No open issues"


    

