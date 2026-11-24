# Lyftr AI Chatbot

## 1. Live URLs

Not deployed yet. A zero-cost deployment can use an Oracle Cloud Always Free VM with Docker Compose; Nginx serves React and proxies API paths to FastAPI on the same origin, while SQLite stays in the named volume on the VM disk.

After creating an Always Free Ubuntu VM and allowing inbound TCP port 80, clone this public repository, copy `.env.example` to `.env`, add two provider keys, and set `FRONTEND_PORT=80`. Then run `docker compose up --build -d`. Check `http://<vm-public-ip>/health`. Use only Always Free eligible resources; Oracle may lack capacity in a region and may reclaim idle instances.

## 2. Run locally: with Docker and without

Copy `.env.example` to `.env` and set two valid provider keys in `LLM_API_KEYS`. The example model is Gemini through LiteLLM. Start with `make up`; the app is at http://localhost:3000 and API at http://localhost:8000. Stop with `make down`.

Without Docker, create a Python environment in `backend`, install `requirements.txt`, set `DATABASE_URL=sqlite:///./app.db`, `LLM_API_KEYS` and `ALLOWED_ORIGINS`, then run `uvicorn main:app --reload --port 8000`. In `frontend`, run `npm install`, then run `npm run dev -- --port 3000`; Vite proxies API calls to the backend.

## 3. Design decisions: key fallback, caching, SQLite session storage

The backend tries the ordered `LLM_API_KEYS` pool and retries on provider, rate-limit and quota failures. Key identifiers are positional (`key_1`, `key_2`) and secret values are never returned. LiteLLM's local cache is enabled; a response cache also preserves reply and per-request usage for exact repeat prompts. SQLite stores user and assistant turns with assistant metadata. Docker mounts a named volume at `/data`.

## 4. Verification: how to see failover, cache hits and per-message token usage

Check `/health`, send the same initial message in a fresh session twice to observe a cache hit, and send `X-Simulate-Failure: key_1=429` to exercise fallback. `X-Simulate-Failure: *=429` should return 503 without persisting the failed turn. The hook is enabled by `ENABLE_FAILURE_SIMULATION=true`. Assistant replies show source, model, latency, input tokens and output tokens.

## 5. Setup Used: your editor and AI tools

Visual Studio Code and OpenAI Codex were used to implement the app and run its checks.

## 6. Bonus features (if any): what you added beyond the requirements and why

Responsive interface, per-session system prompt, and a one-click new chat.

