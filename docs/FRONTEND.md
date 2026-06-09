Frontend — UI & LocalStorage
============================

Files
- `transit-backend/frontend/index.html` — single-page shell
- `transit-backend/frontend/style.css` — mobile-first styles
- `transit-backend/frontend/app.js` — UI logic: chat, GPS, localStorage

Key UI behaviors
- On load: check `drt_saved_route` in localStorage. If present, auto-fetch `/delays/{stop_id}` and `/alerts?route_id=` to populate the route status card.
- Chat history saved in localStorage key `drt_chat_history` as an array of message objects.
- Location: on first send the app should request `navigator.geolocation`. If denied, show a small inline fallback text input labelled "Enter your area (e.g. Whitby, ON)" and append the text to the chat request.

LocalStorage keys
- `drt_chat_history` — array of message objects `{role, content, timestamp}`
- `drt_saved_route` — object `{originStopId, destStopId, routeId, label}` saved via "Save as my regular route"
- `drt_theme` — "dark" or "light" (UI theme preference)

Suggested frontend dev steps
1. Start the backend server locally (see README).
2. Open `http://localhost:8000` in browser — the static files are served by FastAPI.
3. Use browser devtools to test localStorage keys and network calls.

UI feature checklist (To implement / verify)
- Route status card: shows saved route status and Edit / Remove actions.
- Chat area: messages rendered with user/assistant bubbles; assistant supports basic markdown rendering.
- Input bar: sticky bottom, textarea auto-resize, location icon, Send button.
- Theme toggle: persist choice in `drt_theme`.

