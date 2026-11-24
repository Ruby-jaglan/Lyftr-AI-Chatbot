import asyncio
import json
import os
import re
import time
from contextlib import asynccontextmanager
from functools import lru_cache

import litellm
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import SessionLocal, create_tables, get_session_messages, save_message, get_or_create_session
from models import ChatRequest, ChatResponse, HealthResponse, MessageResponse, SessionHistoryResponse

KEYS = [value.strip() for value in os.getenv("LLM_API_KEYS", "").split(",") if value.strip()]
MODEL = os.getenv("LLM_MODEL", "gemini/gemini-3.5-flash-lite")
DEFAULT_SYSTEM_PROMPT = os.getenv("DEFAULT_SYSTEM_PROMPT", "You are a helpful assistant.")
ENABLE_FAILURE_SIMULATION = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"
CACHE_ENABLED = True
# LiteLLM cache stores provider responses. The response cache below also preserves exact usage metadata.
litellm.enable_cache(type="local")
_response_cache = {}

def _failure_map(value):
    result = {}
    if value:
        for item in value.split(","):
            match = re.fullmatch(r"\s*(key_\d+|\*)\s*=\s*(429|500|502|503)\s*", item)
            if match:
                result[match.group(1)] = int(match.group(2))
    return result

def _cache_key(messages):
    return json.dumps([MODEL, messages], sort_keys=True, ensure_ascii=False, separators=(",", ":"))

@asynccontextmanager
async def lifespan(app):
    create_tables()
    yield

app = FastAPI(title="Lyftr AI Chatbot", lifespan=lifespan)
origins = [item.strip() for item in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Simulate-Failure"])

@app.get("/health", response_model=HealthResponse)
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    if not KEYS:
        raise HTTPException(status_code=503, detail="provider keys unavailable")
    return {"status": "ok", "keys_configured": len(KEYS), "cache_enabled": CACHE_ENABLED}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, x_simulate_failure: str | None = Header(default=None)):
    message = request.message.strip()
    if not message or len(message) > 4000:
        raise HTTPException(status_code=422, detail="message must contain 1-4000 non-whitespace characters")
    if not KEYS:
        raise HTTPException(status_code=503, detail="all providers unavailable")
    with SessionLocal() as db:
        session = get_or_create_session(db, request.session_id, request.system_prompt.strip() if request.system_prompt else None)
        prior = get_session_messages(db, request.session_id)
        history = [{"role": row.role, "content": row.content} for row in prior]
        system = (session.system_prompt or DEFAULT_SYSTEM_PROMPT).strip()
        messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": message}]
        key = _cache_key(messages)
        if key in _response_cache and not x_simulate_failure:
            cached = _response_cache[key]
            save_message(db, request.session_id, "user", message)
            save_message(db, request.session_id, "assistant", cached["reply"], cached["metadata"])
            return {"session_id": request.session_id, "reply": cached["reply"], "metadata": {**cached["metadata"], "resolution_source": "LLM_CACHE", "key_id": None, "fallback_attempts": 0, "latency_ms": 0}}
        failures = _failure_map(x_simulate_failure) if ENABLE_FAILURE_SIMULATION else {}
        started = time.perf_counter()
        attempts = 0
        result = None
        successful_key = None
        for index, api_key in enumerate(KEYS, start=1):
            key_id = f"key_{index}"
            status = failures.get("*", failures.get(key_id))
            if status:
                attempts += 1
                continue
            try:
                result = await litellm.acompletion(model=MODEL, api_key=api_key, messages=messages)
                successful_key = key_id
                break
            except Exception as exc:
                code = getattr(exc, "status_code", None)
                if code in (429, 500, 502, 503) or "quota" in str(exc).lower() or "rate" in str(exc).lower():
                    attempts += 1
                    continue
                # Treat provider failures as unavailable and try the next key.
                attempts += 1
        if result is None:
            raise HTTPException(status_code=503, detail="all providers unavailable")
        reply = (result.choices[0].message.content or "").strip()
        if not reply:
            raise HTTPException(status_code=503, detail="all providers unavailable")
        usage = result.usage
        metadata = {"resolution_source": "LIVE_INFERENCE", "model": getattr(result, "model", None) or MODEL, "latency_ms": max(0, int((time.perf_counter()-started)*1000)), "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0), "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0), "key_id": successful_key, "fallback_attempts": attempts}
        _response_cache[key] = {"reply": reply, "metadata": metadata}
        save_message(db, request.session_id, "user", message)
        save_message(db, request.session_id, "assistant", reply, metadata)
        return {"session_id": request.session_id, "reply": reply, "metadata": metadata}

@app.get("/sessions/{session_id}/messages", response_model=SessionHistoryResponse)
def session_messages(session_id: str):
    with SessionLocal() as db:
        rows = get_session_messages(db, session_id)
        if not rows:
            raise HTTPException(status_code=404, detail="session not found")
        messages = []
        for row in rows:
            metadata = json.loads(row.metadata_json) if row.metadata_json else None
            item = {"role": row.role, "content": row.content}
            if metadata is not None:
                item["metadata"] = metadata
            messages.append(item)
        return {"session_id": session_id, "messages": messages}
