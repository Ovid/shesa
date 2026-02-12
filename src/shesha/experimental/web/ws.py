"""WebSocket handlers for query execution and citation checking."""

from __future__ import annotations

import asyncio
import threading

from fastapi import WebSocket, WebSocketDisconnect

from shesha.experimental.web.dependencies import AppState
from shesha.experimental.web.session import WebConversationSession
from shesha.rlm.trace import StepType, TokenUsage


async def websocket_handler(ws: WebSocket, state: AppState) -> None:
    """Handle WebSocket connections for queries and citation checks."""
    await ws.accept()
    cancel_event: threading.Event | None = None

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "cancel":
                if cancel_event is not None:
                    cancel_event.set()
                await ws.send_json({"type": "cancelled"})

            elif msg_type == "query":
                cancel_event = await _handle_query(ws, state, data)

            else:
                await ws.send_json(
                    {"type": "error", "message": f"Unknown message type: {msg_type}"}
                )
    except WebSocketDisconnect:
        if cancel_event is not None:
            cancel_event.set()


async def _handle_query(
    ws: WebSocket, state: AppState, data: dict[str, object]
) -> threading.Event:
    """Execute a query and stream progress. Returns the cancel_event."""
    topic = str(data.get("topic", ""))
    question = str(data.get("question", ""))

    project_id = state.topic_mgr.resolve(topic)
    if not project_id:
        await ws.send_json({"type": "error", "message": f"Topic '{topic}' not found"})
        return threading.Event()

    docs = state.topic_mgr._storage.list_documents(project_id)
    if not docs:
        await ws.send_json({"type": "error", "message": "No papers in topic"})
        return threading.Event()

    project = state.shesha.get_project(project_id)
    cancel_event = threading.Event()

    # Load session for history prefix
    project_dir = state.topic_mgr._storage.project_dir(project_id)
    session = WebConversationSession(project_dir)
    history_prefix = session.format_history_prefix()
    full_question = history_prefix + question if history_prefix else question

    # Use asyncio.Queue for thread-safe message passing from the query
    # thread to the async WebSocket send loop.
    message_queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_progress(
        step_type: StepType, iteration: int, content: str, token_usage: TokenUsage
    ) -> None:
        step_msg: dict[str, object] = {
            "type": "step",
            "step_type": step_type.value,
            "iteration": iteration,
            "content": content,
        }
        if token_usage.prompt_tokens > 0:
            step_msg["prompt_tokens"] = token_usage.prompt_tokens
            step_msg["completion_tokens"] = token_usage.completion_tokens
        loop.call_soon_threadsafe(message_queue.put_nowait, step_msg)

    await ws.send_json({"type": "status", "phase": "Starting", "iteration": 0})

    # Drain the queue in a background task
    async def drain_queue() -> None:
        while True:
            msg = await message_queue.get()
            if msg is None:
                break
            await ws.send_json(msg)

    drain_task = asyncio.create_task(drain_queue())

    # Run query in thread to avoid blocking the event loop
    result = await loop.run_in_executor(
        None,
        lambda: project.query(
            full_question, on_progress=on_progress, cancel_event=cancel_event
        ),
    )

    # Signal the drain task to stop, then wait for it
    await message_queue.put(None)
    await drain_task

    # Save to session
    trace_id = None
    traces = state.topic_mgr._storage.list_traces(project_id)
    if traces:
        trace_id = traces[-1].stem

    session.add_exchange(
        question=question,
        answer=result.answer,
        trace_id=trace_id,
        tokens={
            "prompt": result.token_usage.prompt_tokens,
            "completion": result.token_usage.completion_tokens,
            "total": result.token_usage.total_tokens,
        },
        execution_time=result.execution_time,
        model=state.model,
    )

    await ws.send_json({
        "type": "complete",
        "answer": result.answer,
        "trace_id": trace_id,
        "tokens": {
            "prompt": result.token_usage.prompt_tokens,
            "completion": result.token_usage.completion_tokens,
            "total": result.token_usage.total_tokens,
        },
        "duration_ms": int(result.execution_time * 1000),
    })

    return cancel_event
