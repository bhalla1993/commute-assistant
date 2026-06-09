DRT AI TRANSIT ASSISTANT — AGENT MODE PROMPTS
===============================================
Use this file as a personal cheatsheet. DO NOT attach this to the agent.
Always attach #file:mvp1-plan.md alongside your prompt so the agent has full context.

Weeks 1–3 are COMPLETE. Use Week 4 prompts below to continue.

==============================================================
WEEK 4 — WEB FRONTEND + DEPLOYMENT
==============================================================

STEP 4.1 — Mount frontend/ in FastAPI
--------------------------------------
Paste this into Agent Mode:

  #file:mvp1-plan.md — Update api/main.py to mount the frontend/ folder as
  FastAPI StaticFiles at path "/". The index.html in that folder should be
  served when a user visits the root URL. Do not break any existing API routes:
  /chat, /stops/nearby, /delays, /alerts, /vehicle, /health. StaticFiles must
  be mounted AFTER all API routes.

--------------------------------------------------------------

STEP 4.2 — HTML shell + CSS
-----------------------------
Paste this into Agent Mode:

  #file:mvp1-plan.md — Create frontend/index.html and frontend/style.css.
  Layout has three sections top to bottom:
  1. A route status card (hidden by default, shown when a saved route exists)
  2. A scrollable chat message area (user bubbles right, assistant bubbles left)
  3. A sticky input bar at the bottom with a text field and a Send button
  Use mobile-first CSS flexbox. Must work on screens from 375px to 1280px wide.
  No JavaScript logic yet — just the HTML structure and CSS styles.

--------------------------------------------------------------

STEP 4.3 — Core JavaScript (chat + GPS + history)
---------------------------------------------------
Paste this into Agent Mode:

  #file:mvp1-plan.md — Create frontend/app.js with these functions:
  - sendMessage(): reads the text field, calls POST /chat with {message, history,
    latitude, longitude}, appends user and assistant chat bubbles to the chat area,
    updates the in-memory history array.
  - getLocation(): calls navigator.geolocation.getCurrentPosition on first send.
    If permission is denied or unavailable, show an inline text input labelled
    "Enter your area (e.g. Whitby, ON)" and use that text as location context
    appended to the message.
  - saveHistory(): writes the conversation history array to localStorage key
    "drt_chat_history" after every message.
  - loadHistory(): on page load, reads "drt_chat_history" from localStorage and
    renders any previous messages into the chat area.
  - clearChat(): wipes localStorage key "drt_chat_history" and clears the chat DOM.
    Wire this to a Clear button in the UI.

--------------------------------------------------------------

STEP 4.4 — Saved regular route feature
----------------------------------------
Paste this into Agent Mode:

  #file:mvp1-plan.md — Add saved route functionality to frontend/app.js:
  - saveRoute(originStopId, destStopId, routeId, label): saves these four values
    as an object to localStorage key "drt_saved_route".
  - checkSavedRoute(): called on page load. Reads "drt_saved_route" from
    localStorage. If it exists, calls GET /delays/{stop_id} and
    GET /alerts?route_id= using the saved values, then populates the route status
    card at the top of the page with on-time / delay / alert status text.
  - After the assistant returns a message that contains route results (detected by
    presence of origin_stop_id in the response JSON), show a "Save as my regular
    route" button inline in the assistant's chat bubble. Clicking it calls saveRoute().
  - The route status card must have an Edit button (clears saved route and prompts
    a new question) and a Remove button (deletes localStorage key, hides the card).

--------------------------------------------------------------

==============================================================
UI POLISH — ChatGPT-STYLE REDESIGN  (after Step 4.4, before 4.5)
==============================================================
Goal: make the UI look and feel like ChatGPT — dark sidebar, centred content
column, no-background assistant messages with avatar, rounded textarea input,
markdown rendering, smooth animations, dark/light mode toggle.
All changes are confined to the three frontend/ files only.
Run in order: UI-1 → UI-2 → UI-3 → UI-4.

UI-1 — Dark/light theme + full CSS redesign
--------------------------------------------
Paste this into Agent Mode:

  #file:mvp1-plan.md — Rewrite frontend/style.css with a ChatGPT-style theme.
  Requirements:
  - Dark mode by default. Add [data-theme="dark"] on <html> for dark mode and
    [data-theme="light"] for light mode. Toggle is handled by JS (UI-4).
  - Dark tokens:  --bg #212121, --sidebar-bg #171717, --surface #2f2f2f,
    --border #3f3f3f, --text #ececec, --text-muted #8e8ea0,
    --input-bg #2f2f2f, --btn-send-bg #ececec, --btn-send-color #212121.
  - Light tokens: --bg #f9f9f9, --sidebar-bg #f0f0f0, --surface #ffffff,
    --border #e5e5e5, --text #0d0d0d, --text-muted #6b6b6b,
    --input-bg #ffffff, --btn-send-bg #0d0d0d, --btn-send-color #ffffff.
  - Body layout: flex row, height 100dvh, overflow hidden.
    Left sidebar (#sidebar) 260px wide, right #main fills remaining space.
  - User bubble: right-aligned pill, bg var(--surface), no shadow.
  - Assistant bubble: NO background, NO border — plain flowing text.
    Bot row (#bubble-row--bot) has a 32×32 circle avatar to the left
    containing a 🚌 emoji (use ::before pseudo-element on .bubble-row--bot).
  - Chat area: scrollable flex column, max-width 760px centred in #main.
  - Input box: a single rounded rectangle (.input-bar__box) containing a
    <textarea>, location icon on the left, send button on the right inside
    the box. Textarea has no border/bg, auto-grows up to ~5 lines (120px).
  - Sidebar (#sidebar): flex column, contains header, nav area, footer.
    Hidden off-screen on mobile via transform: translateX(-100%); visible
    on desktop (≥ 640px). Add .sidebar--open class to show on mobile.
  - Mobile header (#mobile-header): display none on desktop, flex on mobile.
  - Keep all existing class names app.js depends on:
    .bubble--user, .bubble--bot, .bubble-row--user, .bubble-row--bot,
    .status-card, .hidden, .btn--save-route, .input, .input--location,
    .btn, .btn--ghost, .btn--sm, .btn--danger.
  - Bubble fade-in: new .bubble-row elements animate opacity 0→1 +
    translateY(8px)→0 over 200ms ease-out via a keyframe animation.
  - Sidebar slide transition: 250ms ease transform.
  - Send button: scale(0.93) on :active, opacity 0.45 when disabled.

--------------------------------------------------------------

UI-2 — Sidebar + header layout (HTML restructure)
---------------------------------------------------
Paste this into Agent Mode:

  #file:mvp1-plan.md — Rewrite frontend/index.html with the ChatGPT-style
  layout structure. Requirements:
  - <html data-theme="dark"> (dark by default).
  - Left sidebar <aside id="sidebar">:
      • Header row: 🚌 icon + "DRT Assistant" title
      • <button id="btn-new-chat" class="btn-new-chat">New Chat</button>
      • The route status card (move #status-card here from top of page)
      • Footer: <button id="btn-theme-toggle"> with a sun/moon SVG icon
  - Right main <div id="main">:
      • <header id="mobile-header"> (mobile only): hamburger button
        <button id="btn-hamburger">, "DRT Assistant" title, and a second
        theme toggle <button id="btn-theme-toggle-mobile">
      • <main id="chat-area"> scrollable chat area (same id as before)
      • <div class="input-bar">
          <div class="input-bar__box">
            location icon button (#btn-location, same as before)
            location fallback div (#location-fallback, same as before)
            <textarea id="message-input" rows="1"> (replaces old <input>)
            send button (#btn-send, same as before)
          </div>
        </div>
  - <div id="sidebar-overlay" class="sidebar-overlay"></div> at end of body
    (semi-transparent dark overlay behind open sidebar on mobile).
  - Do not rename any existing ids that app.js depends on.

--------------------------------------------------------------

UI-3 — Markdown rendering in assistant replies
------------------------------------------------
Paste this into Agent Mode:

  #file:mvp1-plan.md — Add a parseMarkdown(text) function to frontend/app.js.
  Requirements:
  - No external libraries. Pure JS regex + string operations.
  - Input is plain text (the AI reply string). Output is safe HTML string.
  - Step 1: escape HTML — replace &, <, > with &amp; &lt; &gt;
  - Step 2: inline rules on escaped text:
      **bold** → <strong>bold</strong>
      *italic* → <em>italic</em>
      `code` → <code>code</code>
  - Step 3: process line-by-line for block elements:
      Lines starting with "- " or "• " → wrapped in <ul><li>
      Lines starting with "N. " (digit+dot+space) → wrapped in <ol><li>
      Blank lines → <br>
      Other lines → plain text + <br>
      Close open <ul> or <ol> when a non-list line is encountered.
  - Update appendBubble(): for role === 'assistant', set
    bubbleEl.innerHTML = parseMarkdown(text) instead of innerText.
    Keep bubbleEl.innerText = text for user role (XSS safety).
  - onAssistantMessage() reads bubbleEl.innerText (which strips HTML tags)
    so the route-detection regex continues working unchanged.

--------------------------------------------------------------

UI-4 — Animations + new button wiring
---------------------------------------
Paste this into Agent Mode:

  #file:mvp1-plan.md — Add the following wiring and polish to frontend/app.js:
  New DOM refs: btnNewChat (#btn-new-chat), btnThemeToggle (#btn-theme-toggle),
    btnThemeToggleMobile (#btn-theme-toggle-mobile), btnHamburger (#btn-hamburger),
    sidebarEl (#sidebar), sidebarOverlay (#sidebar-overlay).
  New functions:
  - toggleTheme(): reads current data-theme attribute on <html>, switches
    between "dark" and "light", saves to localStorage key "drt_theme".
    Updates the sun/moon icon text in both theme toggle buttons:
    ☀️ when in dark mode (click to go light), 🌙 when in light mode.
  - toggleSidebar(): toggles class "sidebar--open" on #sidebar and class
    "active" on #sidebar-overlay.
  New event listeners:
  - btnNewChat → clearChat()
  - btnThemeToggle → toggleTheme()
  - btnThemeToggleMobile → toggleTheme()
  - btnHamburger → toggleSidebar()
  - sidebarOverlay → toggleSidebar() (close sidebar when overlay is tapped)
  Textarea auto-resize:
  - Add an "input" event listener on messageInput that sets
    messageInput.style.height = "auto" then clamps to scrollHeight (max 120px).
  - In sendMessage(), after clearing messageInput.value, also reset
    messageInput.style.height = "auto".
  On init (bottom of file):
  - Read localStorage "drt_theme"; if set, apply it with
    document.documentElement.setAttribute("data-theme", savedTheme).
  - Call toggleTheme's icon-update logic on load to set correct icon.

--------------------------------------------------------------

STEP 4.5 — Dockerfile
-----------------------
Paste this into Agent Mode:

  #file:mvp1-plan.md — Create a Dockerfile for the transit-backend project.
  Requirements:
  - Base image: python:3.12-slim
  - Working directory: /app
  - Install dependencies from requirements.txt
  - Copy the entire project including the frontend/ folder
  - Expose port 8000
  - CMD: run uvicorn api.main:app with host 0.0.0.0 and port 8000
  - The SQLite database will live at /app/data/transit.db on a mounted volume,
    so do not bake any .db file into the image.

--------------------------------------------------------------

STEP 4.6 — Fly.io config
--------------------------
Paste this into Agent Mode:

  #file:mvp1-plan.md — Create a fly.toml file to deploy this FastAPI app on Fly.io.
  Requirements:
  - App runs on internal port 8000
  - A persistent volume named "transit_data" mounted at /app/data inside the
    container so the SQLite file at data/transit.db survives redeploys
  - Single shared-cpu-1x machine with 256MB RAM
  - Health check against GET /health
  - Force HTTPS (http_checks or tls options)

--------------------------------------------------------------

STEP 4.7 — End-to-end smoke test
----------------------------------
Paste this into Agent Mode:

  #file:mvp1-plan.md — Create test_e2e.py at the project root. This script:
  - Uses httpx to send a POST /chat request to http://localhost:8000/chat
  - Payload: { "message": "What buses run near Oshawa GO Station?",
               "history": [], "latitude": 43.8975, "longitude": -78.8631 }
  - Prints the full JSON response
  - Asserts that response["reply"] is a non-empty string
  - Asserts that HTTP status is 200
  Run it with: python test_e2e.py (server must already be running locally)

--------------------------------------------------------------

STEP 4.8 — First Fly.io deploy
--------------------------------
This step is manual terminal work, not Agent Mode. Run in order:

  cd transit-backend
  fly launch          # first time only — follow prompts, choose region: Toronto (yyz)
  fly volumes create transit_data --region yyz --size 3
  fly secrets set OPENAI_API_KEY=<your_key> OPENAI_BASE_URL=https://api.groq.com/openai/v1 \
    OPENAI_MODEL=llama-3.3-70b-versatile \
    GTFS_RT_TRIP_UPDATES_URL=<url> \
    GTFS_RT_VEHICLE_POSITIONS_URL=<url> \
    GTFS_RT_ALERTS_URL=<url>
  fly deploy
  fly open            # opens the live URL in browser

After deploy, test on your phone browser at the Fly.io URL.

==============================================================
FUTURE WORK (not in current plan)
==============================================================
These were explicitly placed out of scope. Add to a new plan file when ready:

- User accounts + server-side saved routes (needs login system + new DB tables)
- Cross-device history sync (needs accounts first)
- Push notifications / morning route check emails
  (needs a scheduled job + notification service e.g. web push or email via Resend)
- Native iOS or Android app (use the same /chat API backend — just swap the frontend)
- GO Transit or TTC integration (new GTFS feeds + agency-aware agent prompting)
- Historical delay trend charts
