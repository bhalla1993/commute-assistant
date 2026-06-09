Here’s a comprehensive plan you can add to your smart-agent.md file. This plan covers both the **smart agent** (with skills, instructions, and knowledge base) and the **code agent** (Python logic for input scanning, relevance checking, and local GTFS/FAQ answering before LLM fallback).

---

# Smart Agent & Code Agent Implementation Plan

## Overview

This plan describes how to implement a robust agent system for the DRT AI Transit Assistant. The agent will:
- Validate and optimize user input before LLM calls.
- Answer as many queries as possible using local GTFS data and FAQ logic.
- Only call the LLM when necessary.
- Expand its knowledge base over time.
- Ensure the app remains useful even if the LLM is unavailable.

---

## 1. Agent Architecture

- **Agent Layer:** Python code that processes every user message before any LLM call.
- **Instructions:** Rules for validation, optimization, and routing.
- **Skills:** Modular Python classes/functions for answering specific types of queries (e.g., GTFS, FAQ, alerts).
- **Knowledge Base:** Stores common Q&A, user corrections, and facts for instant answers.
- **LLM Fallback:** Only invoked if the agent cannot answer locally.

---

## 2. Implementation Steps

### Step 1: File Structure

```
agent/
  agent.py             # Agent core logic (input scanning, routing, LLM fallback)
  instructions.py      # Rule definitions (or .yaml/.json)
  skills/
    __init__.py
    gtfs.py            # GTFS data parsing and answering
    faq.py             # FAQ logic
    alerts.py          # Service alert logic
  knowledge_base.py    # Q&A storage and retrieval
  utils.py             # Shared helpers (e.g., text normalization)
```

---

### Step 2: Agent Core Logic (`agent.py`)

- **TransitAgent class**
  - `handle(message, user_context)`: Main entry point.
  - `is_transit_question(message)`: Checks if the message is relevant (keywords, regex, intent classifier).
  - `try_local_answer(message, context)`: Tries all skills and knowledge base.
  - `optimize_request(message)`: Cleans and compresses the message for LLM.
  - `call_llm(message, context)`: Calls LLM if needed.
  - `fallback_response()`: Friendly message if LLM and local logic both fail.

---

### Step 3: Skills

- **GTFS Skill (`skills/gtfs.py`):**
  - Load static and real-time GTFS data on startup.
  - Functions: `get_next_departures(stop_id)`, `get_route_status(route_id)`, etc.
  - Parse user input for stop/route queries and answer directly.

- **FAQ Skill (`skills/faq.py`):**
  - Store common questions/answers.
  - Match user input to FAQ entries.

- **Alerts Skill (`skills/alerts.py`):**
  - Parse and return current service alerts for stops/routes.

- **Skill Loader:**
  - Try each skill in order; return the first valid answer.

---

### Step 4: Knowledge Base (`knowledge_base.py`)

- Store and retrieve Q&A pairs.
- On each request, check for similar past questions.
- Update with new facts or corrections from users/admin.

---

### Step 5: LLM Fallback

- If no skill or KB answer, optimize the message and call the LLM.
- Attach only minimal, relevant context to reduce token usage.

---

### Step 6: Fallback & User Experience

- If LLM is unavailable, always provide:
  - Local GTFS/FAQ/alerts answers if possible.
  - A clear, friendly fallback message and quick-access options if not.

---

### Step 7: Logging & Feedback

- Log all agent decisions, user feedback, and missed queries.
- Use logs to improve skills, instructions, and the knowledge base.

---

## 3. Example Agent Flow

1. User: “When is the next bus at Stop 123?”
   - Agent: Recognizes as transit query.
   - GTFS skill answers directly.
2. User: “What’s the weather?”
   - Agent: Not transit-related. Responds with a polite message.
3. User: “Is the 915 bus delayed?”
   - Agent: GTFS/alerts skill checks real-time data and answers.
4. User: “Write a poem about buses.”
   - Agent: Not transit-relevant. If LLM is up, forwards; if not, responds with fallback.

---

## 4. Agent Mode Instructions (for New Chat Session)

**When starting a new chat session for code agent implementation:**

1. Load all skills and the knowledge base.
2. For each user message:
   - Run `is_transit_question()`. If not relevant, reply with a polite message.
   - Run `try_local_answer()`. If a skill or KB can answer, reply instantly.
   - If not, run `optimize_request()` and call the LLM.
   - If LLM is unavailable, run `fallback_response()`.
3. Log all actions and user feedback for continuous improvement.

---

## 5. Error Handling & Robustness

- Always catch exceptions in skills and agent logic.
- If any skill or data source fails, continue to the next.
- Never crash or hang the user session—always provide a response.

---

## 6. Future Enhancements

- Add ML-based intent classification for better relevance detection.
- Use semantic search (embeddings) for knowledge base lookups.
- Allow admin review and curation of new knowledge base entries.

---

**This plan ensures your agent is robust, modular, and user-friendly, providing value even if the LLM is unavailable.**
