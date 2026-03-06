"""
Marvin Worker — Background task processor.

Runs alongside the Transmission API server. Continuously:
  1. Claims the next queued task
  2. Runs constitutional pre-checks (non-optional)
  3. Routes it through the LLM tier waterfall
  4. Runs constitutional post-checks on output
  5. Optionally executes tool actions from the LLM response
  6. Stores the result and caches it

The constitution wraps everything. It cannot be skipped.
"""

import json
import logging
import re
import time
import signal

from src.taskqueue.task_queue import TaskQueue, TaskPriority
from src.lobby.classifier import LobbyClassifier
from src.cache.cache import CacheLayer
from src.router.llm_router import LLMRouter, TIER_MAP
from src.dispatcher.dispatcher import Dispatcher
from src.constitution.constitution import Constitution, Verdict

logger = logging.getLogger(__name__)

# Action instructions appended to the constitutional system prompt
ACTION_INSTRUCTIONS = """
When the user's request requires action (running commands, reading files, checking status),
respond with a JSON block describing the action:

```action
{"type": "shell", "command": "git status"}
```

```action
{"type": "file_read", "path": "src/main.py"}
```

```action
{"type": "container_status"}
```

```action
{"type": "container_logs", "name": "claude-hub"}
```

If no action is needed, just respond with text.
You can include multiple action blocks in one response.
After actions execute, their results will be appended and you can respond again.
"""


def extract_actions(text: str) -> list[dict]:
    """Extract action blocks from LLM response."""
    actions = []
    for match in re.finditer(r"```action\s*\n({.*?})\s*\n```", text, re.DOTALL):
        try:
            actions.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            logger.warning(f"Invalid action JSON: {match.group(1)}")
    return actions


def execute_actions(dispatcher: Dispatcher, actions: list[dict]) -> str:
    """Execute a list of actions and return combined results."""
    results = []
    for action in actions:
        action_type = action.get("type", "")

        if action_type == "shell":
            r = dispatcher.run_shell(action.get("command", ""))
        elif action_type == "file_read":
            r = dispatcher.read_file(action.get("path", ""))
        elif action_type == "file_write":
            r = dispatcher.write_file(action.get("path", ""), action.get("content", ""))
        elif action_type == "container_status":
            r = dispatcher.container_status()
        elif action_type == "container_logs":
            r = dispatcher.container_logs(action.get("name", ""))
        elif action_type == "container_restart":
            r = dispatcher.container_restart(action.get("name", ""))
        else:
            results.append(f"Unknown action type: {action_type}")
            continue

        status = "OK" if r.success else "FAILED"
        results.append(f"[{action_type}] {status}:\n{r.output}")

    return "\n---\n".join(results)


def process_task(task, router: LLMRouter, dispatcher: Dispatcher,
                 cache: CacheLayer, constitution: Constitution) -> tuple[str, str]:
    """
    Process a single task through the full constitutional pipeline.

    Returns (result_text, tier_used).
    """
    # CONSTITUTIONAL PRE-CHECK (non-optional)
    pre = constitution.pre_check(task)
    if pre.verdict == Verdict.BLOCK.value:
        return f"BLOCKED by constitution ({pre.rule}): {pre.reason}", "constitution"
    if pre.verdict == Verdict.ESCALATE.value:
        return f"ESCALATED ({pre.rule}): {pre.reason} — awaiting human approval", "constitution"

    prompt = task.message
    if task.project:
        prompt = f"[Project: {task.project}]\n\n{prompt}"

    # Build system prompt: constitutional rules + action instructions
    system_prompt = constitution.get_system_prompt() + "\n" + ACTION_INSTRUCTIONS

    # Route to LLM
    response = router.route(prompt, intent=task.intent, system=system_prompt)
    tier = response.tier
    result_text = response.content

    # CONSTITUTIONAL POST-CHECK (non-optional)
    post = constitution.post_check(result_text)
    if post.verdict == Verdict.BLOCK.value:
        logger.warning(f"Output blocked by constitution: {post.rule}")
        result_text = f"[Output redacted by constitution: {post.reason}]"
        return result_text, tier

    # Execute actions from LLM response
    actions = extract_actions(result_text)
    if actions:
        action_results = execute_actions(dispatcher, actions)
        # Feed action results back to LLM for summary
        followup = f"{prompt}\n\n--- Action Results ---\n{action_results}\n\nSummarize what happened."
        followup_response = router.route(followup, intent=task.intent,
                                         system=system_prompt, force_tier=tier)
        result_text = followup_response.content

        # Post-check the summary too
        post2 = constitution.post_check(result_text)
        if post2.verdict == Verdict.BLOCK.value:
            result_text = f"[Output redacted by constitution: {post2.reason}]"

        tier = followup_response.tier

    # Cache if intent is cacheable
    classifier = LobbyClassifier()
    classification = classifier.classify(task.message)
    if classification.cacheable:
        cache.put(
            intent=task.intent,
            response={"text": result_text},
            project=task.project,
            tokens_saved=response.tokens_used,
        )

    constitution.increment_task_count()
    return result_text, tier


class Worker:
    """Background worker that processes queued tasks with constitutional guardrails."""

    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self.running = False
        self.queue = TaskQueue()
        self.router = LLMRouter()
        self.dispatcher = Dispatcher()
        self.cache = CacheLayer()
        self.constitution = Constitution(session_id="worker")
        self.tasks_processed = 0

    def start(self):
        """Start the worker loop."""
        self.running = True
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info("Marvin worker started (constitutional framework active)")

        while self.running:
            task = self.queue.claim_next()
            if not task:
                time.sleep(self.poll_interval)
                continue

            logger.info(f"Processing task {task.id}: {task.message[:60]}...")

            try:
                result, tier = process_task(
                    task, self.router, self.dispatcher,
                    self.cache, self.constitution,
                )
                self.queue.complete(task.id, result, tier=tier)
                self.tasks_processed += 1
                logger.info(f"Task {task.id} done via {tier} (total: {self.tasks_processed})")

            except Exception as e:
                logger.error(f"Task {task.id} failed: {e}")
                self.queue.fail(task.id, str(e))

        self._cleanup()

    def _shutdown(self, signum, frame):
        logger.info("Shutdown signal received")
        self.running = False

    def _cleanup(self):
        self.queue.close()
        self.cache.close()
        logger.info(f"Worker stopped. Processed {self.tasks_processed} tasks.")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    worker = Worker()
    worker.start()


if __name__ == "__main__":
    main()
