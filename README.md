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
    !!! After modifying script.py you have to reload the process of server.py using (Ctrl/CMD + Shift + P)
        and select the Developer: Reload Window.

How to check that you mcp server is actually up and running.
    Go to Settings -> Tools & MCP -> Check that "github-server" has a green mark

