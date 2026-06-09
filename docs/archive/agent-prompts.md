# Agent Prompts (archived)

1) Mount frontend as StaticFiles
--------------------------------
Use-case: Mount the `transit-backend/frontend/` directory at `/` using FastAPI StaticFiles so the SPA is served.

Prompt to the assistant:
```
Open the FastAPI app in transit-backend/api/main.py and mount StaticFiles for transit-backend/frontend/ at '/'.
Ensure you mount after routers to avoid route conflicts. Use app.mount('/', StaticFiles(directory=str(FRONTEND_PATH), html=True), name='frontend')
Add an environment variable FRONTEND_PATH defaulting to Path(__file__).parents[2] / 'frontend'
```

2) Add saved route UI
---------------------
Use-case: Show a saved route card on page load if `drt_saved_route` exists in localStorage.

Prompt to the assistant:
```
Update transit-backend/frontend/app.js to load drt_saved_route from localStorage on startup and call /delays/<stop_id> and /alerts?route_id=<route_id> to populate the status card.
Render the status card at the top of the chat UI with edit/remove buttons.
```

3) Add ad gating flow
---------------------
Use-case: Implement the ad watch token flow—get /ads/token before showing the result.

Prompt to the assistant:
```
Implement ad gating in the frontend: before sending a chat request, call POST /ads/token to get a token. Show a modal with the ad. After ad completes, call POST /ads/complete with the token. Then proceed to send the chat request.
```

4) Background poller deployment notes
------------------------------------
Use-case: Ensure the poller runs in background when running under uvicorn in production.

Prompt to the assistant:
```
Ensure uvicorn lifespan event in transit-backend/api/main.py spawns the poller thread. The poller should check for an existing running thread and not spawn duplicates. Also add a health endpoint /health that checks poller last-run timestamp and DB connectivity.
```

5) Agent behavior instructions
-----------------------------
Use-case: Instruct the LLM agent never to hallucinate schedule data.

Prompt to the assistant:
```
Create or update transit-backend/agent/prompt.py to include a system message: the agent must never invent stop ids, route numbers, or times. It must call the provided tools for any schedule or stop/route data. If no data is available, respond: "I don't have live data for that right now." Keep responses concise.
```
