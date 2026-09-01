"""Run registry: start graph runs, stream their progress, keep results.

The registry itself is per-process: it holds the asyncio task and the live SSE queue, neither of
which can cross a worker boundary. What CAN cross is the checkpointer -- the graph writes its state
to Postgres on every node transition -- so `from_checkpoint` reconstructs a finished run's result
for a worker that never ran it. That is what makes polling safe under `--workers N`; live SSE
streaming still needs the worker that owns the run, and would need pub/sub to do otherwise.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from app.schemas.quiz import RunState

logger = logging.getLogger(__name__)

# Long enough for a generation already past its LLM calls to land, short enough that a wedged run
# cannot hold shutdown open indefinitely.
DRAIN_TIMEOUT = 30.0


@dataclass
class Run:
    run_id: str
    status: RunState = "running"
    steps: list[str] = field(default_factory=list)
    quiz: dict | None = None
    error: str | None = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        # Strong references to the in-flight tasks. asyncio only holds a weak one, so an untracked
        # create_task can be garbage-collected mid-run; and without the set there is nothing for
        # shutdown to wait on, so Ctrl-C used to discard a whole generation silently.
        self._tasks: set[asyncio.Task] = set()

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    async def start(self, graph, inputs: dict) -> Run:
        run = Run(run_id=f"run_{uuid.uuid4().hex[:12]}")
        self._runs[run.run_id] = run
        task = asyncio.create_task(self._execute(graph, inputs, run))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    async def drain(self, timeout: float = DRAIN_TIMEOUT) -> None:
        """Let in-flight runs finish before the process tears its backends down.

        Called by the app lifespan on shutdown. uvicorn drains HTTP requests but knows nothing about
        these background tasks, so without this a Ctrl-C mid-generation loses the run -- including
        the memory and quiz rows it was about to write -- with no log line.
        """
        if not self._tasks:
            return
        logger.info("waiting for %d in-flight run(s) to finish", len(self._tasks))
        done, pending = await asyncio.wait(set(self._tasks), timeout=timeout)
        for task in pending:
            # Past the deadline the backends are about to close under them anyway; cancelling is
            # tidier than letting them fail on a shut connection.
            logger.warning("run did not finish within %ss, cancelling", timeout)
            task.cancel()

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


async def from_checkpoint(saver, run_id: str) -> Run | None:
    """Rebuild a run's outcome from its checkpoint, for a worker that did not run it.

    thread_id is the run id (see _execute), so the checkpointer is already keyed the way we need.
    `steps` comes back empty: it is accumulated by the process that streamed the run and is not part
    of graph state, so a different worker genuinely does not know it.
    """
    if saver is None:
        return None
    try:
        tup = await saver.aget_tuple({"configurable": {"thread_id": run_id}})
    except Exception as e:  # noqa: BLE001 -- a polling endpoint must not 500 on a checkpoint read
        logger.warning("could not read checkpoint for %s (%s): %s", run_id, type(e).__name__, e)
        return None
    if tup is None:
        return None

    state = tup.checkpoint.get("channel_values", {})
    run = Run(run_id=run_id)
    quiz = state.get("quiz") or {}
    if quiz.get("questions"):
        run.status, run.quiz = "done", quiz
    elif state.get("error"):
        run.status, run.error = "failed", state["error"]
    else:
        # A checkpoint exists but the run reached neither outcome: it was still going when its
        # worker died. Reporting "running" would strand the caller polling forever.
        run.status, run.error = "failed", "The run did not finish."
    return run
