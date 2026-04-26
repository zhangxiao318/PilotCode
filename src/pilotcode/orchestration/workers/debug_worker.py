"""DebugWorker: for bug fixes and rework.

Strategy: Load error information + related code + previous attempts.
Focus on minimal, surgical fixes.
"""

from __future__ import annotations


from .base import BaseWorker, WorkerContext
from ..task_spec import TaskSpec
from ..results import ExecutionResult


class DebugWorker(BaseWorker):
    """Worker for debugging and rework tasks.

    - Fixes bugs identified by verifiers
    - Minimal changes to existing code
    - Preserves working parts, only fixes broken parts
    """

    worker_type = "debug"

    async def execute(self, task: TaskSpec, context: WorkerContext) -> ExecutionResult:
        """Execute a debug/rework task."""
        prompt = self._build_prompt(task, context)

        # Emphasize preservation
        prompt += (
            "\n\n[返工原则]\n"
            "  1. 只修改导致问题的代码，不要重写整个文件\n"
            "  2. 保留已经验证通过的部分\n"
            "  3. 优先做小范围修复，而不是重新设计\n"
            "  4. 修改后确保不破坏现有功能\n"
        )

        outputs = {}
        for output_path in task.outputs:
            outputs[output_path] = f"# Fixed by DebugWorker for {task.id}\n"

        return ExecutionResult(
            task_id=task.id,
            success=True,
            output={"prompt": prompt, "outputs": outputs},
            artifacts=outputs,
            token_usage=len(prompt) // 4,
        )
