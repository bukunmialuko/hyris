"""In-process run registry: start graph runs, stream their progress, keep results.

Good for local development and a single API process. For multi-worker production,
swap the registry for Redis or read progress straight from the Postgres checkpointer.
"""

import asyncio
import uuid
from dataclasses import dataclass, field


@dataclass
class Run:
    run_id: str
    status: str = "running"                       # running | done | failed
    steps: list[str] = field(default_factory=list)
    quiz: dict | None = None
    error: str | None = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    async def start(self, graph, inputs: dict) -> Run:
        run = Run(run_id=f"run_{uuid.uuid4().hex[:12]}")
        self._runs[run.run_id] = run
        asyncio.create_task(self._execute(graph, inputs, run))
        return run

    async def _execute(self, graph, inputs: dict, run: Run) -> None:
        config = {"configurable": {"thread_id": run.run_id}}
        final: dict = {}
        try:
            async for update in graph.astream(inputs, config, stream_mode="updates"):
                for node, out in update.items():
                    run.steps.append(node)
                    await run.queue.put({"event": "step", "node": node})
                    final.update(out or {})
            if final.get("quiz", {}).get("questions"):
                run.status, run.quiz = "done", final["quiz"]
                await run.queue.put({"event": "quiz", "quiz": run.quiz})
            else:
                run.status = "failed"
                run.error = final.get("error") or "The run produced no quiz."
                await run.queue.put({"event": "error", "error": run.error})
        except Exception as e:  # noqa: BLE001 — never leave a run hanging
            run.status, run.error = "failed", f"Run crashed: {e}"
            await run.queue.put({"event": "error", "error": run.error})
        finally:
            await run.queue.put({"event": "end"})


registry = RunRegistry()
