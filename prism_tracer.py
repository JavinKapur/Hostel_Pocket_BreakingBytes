import os
import time
import json
import threading
from typing import List, Dict, Any, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

# PRISM Configuration loaded safely from environment / .env
PRISM_API_KEY = os.getenv("PRISMTRACE_API_KEY", "")
PRISM_PROJECT_ID = os.getenv("PRISMTRACE_PROJECT_ID", "")
PRISM_HOST = os.getenv("PRISMTRACE_HOST", "https://prism-api-prod.up.railway.app")

TELEMETRY_LOGS = []
_telemetry_lock = threading.Lock()

pt_client = None
if PRISM_API_KEY and PRISM_PROJECT_ID:
    try:
        from prismtrace import PRISMtrace
        pt_client = PRISMtrace(
            api_key=PRISM_API_KEY,
            host=PRISM_HOST,
            project_id=PRISM_PROJECT_ID,
        )
    except Exception as e:
        print(f"[PRISM Init Notice] Could not init PRISMtrace SDK: {e}")

def _record_local_telemetry(entry: Dict[str, Any]):
    with _telemetry_lock:
        TELEMETRY_LOGS.insert(0, entry)
        if len(TELEMETRY_LOGS) > 50:
            TELEMETRY_LOGS.pop()

def get_telemetry_history() -> List[Dict[str, Any]]:
    with _telemetry_lock:
        return list(TELEMETRY_LOGS)

def _send_http_telemetry(payload: Dict[str, Any]):
    """Bulletproof fallback HTTP ingestion stream"""
    if not PRISM_API_KEY:
        return
    try:
        headers = {
            "Content-Type": "application/json",
            "X-PRISMtrace-Key": PRISM_API_KEY,
        }
        url = f"{PRISM_HOST.rstrip('/')}/api/traces"
        requests.post(url, json=payload, headers=headers, timeout=3)
    except Exception:
        pass

def log_llm_call(
    model: str,
    input_messages: List[Dict[str, str]],
    output: str,
    latency_ms: int,
    session_id: str = "hostel-pocket-session-001",
    agent_id: str = "hostelpocket-agent",
    agent_name: str = "HostelPocket Core Agent",
    metadata: Optional[Dict[str, Any]] = None,
):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "timestamp": timestamp,
        "type": "llm_call",
        "model": model,
        "latency_ms": latency_ms,
        "session_id": session_id,
        "agent_name": agent_name,
        "input_preview": str(input_messages[-1].get("content", ""))[:120] if input_messages else "",
        "output_preview": str(output)[:120],
        "status": "success",
    }
    _record_local_telemetry(entry)

    def _async_worker():
        if pt_client:
            try:
                pt_client.trace_llm(
                    model=model,
                    input_messages=input_messages,
                    output=output,
                    latency_ms=latency_ms,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    session_id=session_id,
                    metadata=metadata or {},
                )
            except Exception:
                pass

        payload = {
            "project_id": PRISM_PROJECT_ID,
            "model": model,
            "input_messages": input_messages,
            "output_message": output,
            "latency_ms": latency_ms,
            "session_id": session_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "metadata": metadata or {},
        }
        _send_http_telemetry(payload)

    t = threading.Thread(target=_async_worker, daemon=True)
    t.start()

def log_agent_trajectory(
    steps: List[Dict[str, Any]],
    agent_name: str = "HostelPocket Expense Pipeline",
    conversation_id: str = "hostel-pocket-conv-001",
    model: str = "openai/gpt-oss-120b",
    final_status: str = "success",
):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "timestamp": timestamp,
        "type": "trajectory",
        "model": model,
        "steps_count": len(steps),
        "agent_name": agent_name,
        "conversation_id": conversation_id,
        "status": final_status,
        "steps": [s.get("label", "") for s in steps],
    }
    _record_local_telemetry(entry)

    def _async_worker():
        if pt_client and hasattr(pt_client, "submit_trajectory"):
            try:
                pt_client.submit_trajectory(
                    steps=steps,
                    agent_name=agent_name,
                    conversation_id=conversation_id,
                    model=model,
                    final_status=final_status,
                    async_send=True,
                )
            except Exception:
                pass

    t = threading.Thread(target=_async_worker, daemon=True)
    t.start()
