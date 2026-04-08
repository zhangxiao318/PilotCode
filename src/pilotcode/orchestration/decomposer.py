"""Task decomposition engine.

Analyzes tasks and determines optimal decomposition strategies.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional


class DecompositionStrategy(Enum):
    """Strategies for task decomposition."""
    NONE = auto()           # Don't decompose, execute as-is
    SEQUENTIAL = auto()     # Decompose into sequential steps
    PARALLEL = auto()       # Decompose into parallel subtasks
    HIERARCHICAL = auto()   # Decompose with supervisor/worker pattern
    ITERATIVE = auto()      # Decompose with feedback loops


@dataclass
class SubTask:
    """A single subtask from decomposition."""
    id: str
    description: str
    prompt: str
    role: str  # coder, debugger, tester, etc.
    dependencies: list[str] = field(default_factory=list)
    estimated_complexity: int = 3  # 1-5 scale
    estimated_duration_seconds: int = 60
    required_tools: list[str] = field(default_factory=list)
    output_key: Optional[str] = None  # For result referencing


@dataclass
class DecompositionResult:
    """Result of task decomposition."""
    original_task: str
    strategy: DecompositionStrategy
    subtasks: list[SubTask]
    reasoning: str
    confidence: float  # 0-1 confidence score
    estimated_total_duration: int = 0


class TaskDecomposer:
    """Decomposes complex tasks into manageable subtasks.
    
    Uses heuristics and LLM-based analysis to determine optimal decomposition.
    """
    
    # Complexity indicators that suggest decomposition
    COMPLEXITY_INDICATORS = [
        r"implement|create|build|develop",  # Building something
        r"refactor|restructure|redesign",   # Large changes
        r"analyze.*codebase|understand.*project",  # Exploration
        r"test.*comprehensive|full.*test",  # Testing
        r"migrate|upgrade|update.*to",      # Migration
        r"multiple|several|various",        # Multiple items
        r"and.*then|followed by|after.*then",  # Sequential steps
    ]
    
    # Indicators of parallelizable work
    PARALLEL_INDICATORS = [
        r"each.*separately|independently",
        r"for every|for each",
        r"multiple files|different modules",
        r"check.*and.*fix|review.*and.*update",
    ]
    
    def __init__(self, model_client: Optional[Any] = None):
        self.model_client = model_client
    
    def analyze(self, task: str, context: str = "") -> DecompositionResult:
        """Analyze a task and determine if/ how to decompose it.
        
        Uses a hybrid approach:
        1. Rule-based heuristics for quick decisions
        2. LLM analysis for complex cases
        """
        # Quick heuristic analysis
        heuristic = self._heuristic_analysis(task)
        
        # If clearly simple or clearly complex, use heuristic
        if heuristic["confidence"] > 0.8:
            return self._create_decomposition(
                task, 
                heuristic["strategy"],
                heuristic.get("subtasks", []),
                heuristic["reasoning"]
            )
        
        # Otherwise, use LLM for detailed analysis
        if self.model_client:
            return self._llm_analysis(task, context)
        
        # Fallback to heuristic
        return self._create_decomposition(
            task,
            heuristic["strategy"],
            heuristic.get("subtasks", []),
            heuristic["reasoning"],
            confidence=heuristic["confidence"]
        )
    
    def _heuristic_analysis(self, task: str) -> dict:
        """Quick rule-based analysis."""
        task_lower = task.lower()
        
        # Check for simple tasks (should not decompose)
        simple_indicators = [
            r"^read\s+",
            r"^show\s+",
            r"^list\s+",
            r"^find\s+",
            r"single\s+file",
            r"quick\s+fix",
        ]
        
        for pattern in simple_indicators:
            if re.search(pattern, task_lower):
                return {
                    "strategy": DecompositionStrategy.NONE,
                    "reasoning": "Simple task that doesn't benefit from decomposition",
                    "confidence": 0.9
                }
        
        # Check complexity
        complexity_score = 0
        for pattern in self.COMPLEXITY_INDICATORS:
            if re.search(pattern, task_lower):
                complexity_score += 1
        
        # Check for parallel indicators
        parallel_score = 0
        for pattern in self.PARALLEL_INDICATORS:
            if re.search(pattern, task_lower):
                parallel_score += 1
        
        # Determine strategy based on scores
        if complexity_score < 2:
            return {
                "strategy": DecompositionStrategy.NONE,
                "reasoning": "Low complexity task",
                "confidence": 0.7
            }
        
        if parallel_score > 0:
            return {
                "strategy": DecompositionStrategy.PARALLEL,
                "reasoning": "Task contains parallelizable components",
                "confidence": 0.6 + (0.1 * parallel_score)
            }
        
        if complexity_score > 3:
            return {
                "strategy": DecompositionStrategy.HIERARCHICAL,
                "reasoning": "High complexity suggests hierarchical decomposition",
                "confidence": 0.6
            }
        
        # Default to sequential for moderate complexity
        return {
            "strategy": DecompositionStrategy.SEQUENTIAL,
            "reasoning": "Moderate complexity suggests sequential steps",
            "confidence": 0.5
        }
    
    def _llm_analysis(self, task: str, context: str) -> DecompositionResult:
        """Use LLM to analyze and decompose task."""
        prompt = f"""Analyze this programming task and determine the optimal decomposition strategy.

Task: {task}
Context: {context}

Provide a JSON response with this structure:
{{
    "should_decompose": true/false,
    "strategy": "none|sequential|parallel|hierarchical|iterative",
    "reasoning": "explanation of why this strategy was chosen",
    "confidence": 0.0-1.0,
    "subtasks": [
        {{
            "id": "step1",
            "description": "brief description",
            "role": "coder|debugger|tester|reviewer|planner|explainer",
            "prompt": "full prompt for this subtask",
            "dependencies": [],
            "complexity": 1-5
        }}
    ]
}}

Guidelines:
- Use "none" for tasks that are atomic and don't benefit from decomposition
- Use "sequential" when steps depend on previous results
- Use "parallel" when subtasks are independent
- Use "hierarchical" for complex tasks needing a coordinator
- Use "iterative" for tasks requiring refinement loops"""

        try:
            # This would call the actual model client
            # For now, return a placeholder
            return self._create_decomposition(
                task,
                DecompositionStrategy.SEQUENTIAL,
                [],
                "LLM analysis not available, using fallback"
            )
        except Exception:
            return self._create_decomposition(
                task,
                DecompositionStrategy.NONE,
                [],
                "Error in LLM analysis, falling back to no decomposition"
            )
    
    def _create_decomposition(
        self,
        task: str,
        strategy: DecompositionStrategy,
        subtask_dicts: list[dict],
        reasoning: str,
        confidence: float = 0.5
    ) -> DecompositionResult:
        """Create a decomposition result from analysis."""
        subtasks = []
        total_duration = 0
        
        for i, std in enumerate(subtask_dicts):
            subtask = SubTask(
                id=std.get("id", f"step{i+1}"),
                description=std.get("description", ""),
                prompt=std.get("prompt", ""),
                role=std.get("role", "coder"),
                dependencies=std.get("dependencies", []),
                estimated_complexity=std.get("complexity", 3),
                estimated_duration_seconds=std.get("duration", 60),
                required_tools=std.get("tools", []),
                output_key=std.get("output_key")
            )
            subtasks.append(subtask)
            total_duration += subtask.estimated_duration_seconds
        
        return DecompositionResult(
            original_task=task,
            strategy=strategy,
            subtasks=subtasks,
            reasoning=reasoning,
            confidence=confidence,
            estimated_total_duration=total_duration
        )
    
    def auto_decompose(self, task: str) -> DecompositionResult:
        """Automatically decompose a task using default rules.
        
        Creates standard decomposition patterns for common tasks.
        """
        task_lower = task.lower()
        
        # Pattern: "Implement X with tests"
        if "implement" in task_lower and ("test" in task_lower or "tests" in task_lower):
            return self._decompose_implementation_with_tests(task)
        
        # Pattern: "Refactor X"
        if "refactor" in task_lower:
            return self._decompose_refactoring(task)
        
        # Pattern: "Fix bug in X"
        if any(word in task_lower for word in ["fix", "bug", "error", "issue"]):
            return self._decompose_bug_fix(task)
        
        # Pattern: "Review X"
        if "review" in task_lower or "audit" in task_lower:
            return self._decompose_code_review(task)
        
        # Default analysis
        return self.analyze(task)
    
    def _decompose_implementation_with_tests(self, task: str) -> DecompositionResult:
        """Decompose implementation task."""
        return DecompositionResult(
            original_task=task,
            strategy=DecompositionStrategy.SEQUENTIAL,
            subtasks=[
                SubTask(
                    id="plan",
                    description="Plan the implementation",
                    prompt=f"Analyze this task and create an implementation plan:\n\n{task}\n\nProvide:\n1. Key components needed\n2. Interface design\n3. Implementation approach",
                    role="planner",
                    estimated_complexity=2
                ),
                SubTask(
                    id="implement",
                    description="Implement the code",
                    prompt=f"Implement the solution:\n\n{task}\n\nFollow the plan from the previous step. Write clean, well-documented code.",
                    role="coder",
                    dependencies=["plan"],
                    estimated_complexity=4
                ),
                SubTask(
                    id="test",
                    description="Write tests",
                    prompt=f"Write comprehensive tests for the implementation:\n\n{task}\n\nCover:\n1. Happy path\n2. Edge cases\n3. Error cases",
                    role="tester",
                    dependencies=["implement"],
                    estimated_complexity=3
                )
            ],
            reasoning="Implementation tasks benefit from planning first, then coding, then testing",
            confidence=0.85
        )
    
    def _decompose_refactoring(self, task: str) -> DecompositionResult:
        """Decompose refactoring task."""
        return DecompositionResult(
            original_task=task,
            strategy=DecompositionStrategy.SEQUENTIAL,
            subtasks=[
                SubTask(
                    id="explore",
                    description="Explore current code",
                    prompt=f"Explore the code to understand current structure:\n\n{task}\n\nProvide:\n1. Current architecture\n2. Pain points\n3. Areas needing change",
                    role="explorer",
                    estimated_complexity=2
                ),
                SubTask(
                    id="plan",
                    description="Plan refactoring steps",
                    prompt=f"Create a detailed refactoring plan:\n\n{task}\n\nBased on the exploration, define:\n1. Step-by-step refactoring plan\n2. Safety checks at each step\n3. Rollback strategy",
                    role="planner",
                    dependencies=["explore"],
                    estimated_complexity=3
                ),
                SubTask(
                    id="refactor",
                    description="Execute refactoring",
                    prompt=f"Execute the refactoring:\n\n{task}\n\nFollow the plan carefully. Make incremental changes.",
                    role="coder",
                    dependencies=["plan"],
                    estimated_complexity=4
                ),
                SubTask(
                    id="verify",
                    description="Verify the refactoring",
                    prompt=f"Verify the refactoring is correct:\n\n{task}\n\nCheck:\n1. Functionality preserved\n2. Code quality improved\n3. No regressions",
                    role="reviewer",
                    dependencies=["refactor"],
                    estimated_complexity=2
                )
            ],
            reasoning="Refactoring requires understanding current state, planning, executing, and verifying",
            confidence=0.9
        )
    
    def _decompose_bug_fix(self, task: str) -> DecompositionResult:
        """Decompose bug fix task."""
        return DecompositionResult(
            original_task=task,
            strategy=DecompositionStrategy.SEQUENTIAL,
            subtasks=[
                SubTask(
                    id="diagnose",
                    description="Diagnose the bug",
                    prompt=f"Diagnose this bug:\n\n{task}\n\nFind:\n1. Root cause\n2. Affected code\n3. Reproduction steps",
                    role="debugger",
                    estimated_complexity=3
                ),
                SubTask(
                    id="fix",
                    description="Fix the bug",
                    prompt=f"Fix the identified bug:\n\n{task}\n\nMake minimal, targeted changes.",
                    role="coder",
                    dependencies=["diagnose"],
                    estimated_complexity=2
                ),
                SubTask(
                    id="test",
                    description="Add regression test",
                    prompt=f"Add a regression test for the bug:\n\n{task}\n\nEnsure the bug won't recur.",
                    role="tester",
                    dependencies=["fix"],
                    estimated_complexity=2
                )
            ],
            reasoning="Bug fixing requires diagnosis before fix, then verification",
            confidence=0.9
        )
    
    def _decompose_code_review(self, task: str) -> DecompositionResult:
        """Decompose code review task."""
        return DecompositionResult(
            original_task=task,
            strategy=DecompositionStrategy.PARALLEL,
            subtasks=[
                SubTask(
                    id="review_structure",
                    description="Review code structure",
                    prompt=f"Review code structure:\n\n{task}\n\nFocus on:\n1. Architecture\n2. Design patterns\n3. Code organization",
                    role="reviewer",
                    estimated_complexity=3
                ),
                SubTask(
                    id="review_quality",
                    description="Review code quality",
                    prompt=f"Review code quality:\n\n{task}\n\nFocus on:\n1. Readability\n2. Maintainability\n3. Best practices",
                    role="reviewer",
                    estimated_complexity=3
                ),
                SubTask(
                    id="review_security",
                    description="Review security",
                    prompt=f"Review security:\n\n{task}\n\nFocus on:\n1. Security vulnerabilities\n2. Input validation\n3. Error handling",
                    role="reviewer",
                    estimated_complexity=3
                )
            ],
            reasoning="Code review aspects can be evaluated in parallel",
            confidence=0.8
        )
