# Task Orchestration System Architecture

## Core Components

### 1. Task Manager
The task manager is implemented through the `TaskCreateTool`, `TaskGetTool`, `TaskListTool`, `TaskStopTool`, and `TaskUpdateTool` classes in `src/pilotcode/tools/task_tools.py`.

Key responsibilities:
- Creating new background tasks with `TaskCreateTool`
- Retrieving task status with `TaskGetTool`
- Listing tasks with `TaskListTool`
- Stopping running tasks with `TaskStopTool`
- Updating task properties with `TaskUpdateTool`

### 2. Task Storage
The task storage system maintains in-memory state for all tasks:
- `_tasks: dict[str, Task]` - Stores all task metadata and state
- `_task_handles: dict[str, asyncio.Task]` - Tracks running asyncio tasks for background execution

### 3. Task Execution Engine
The system uses Python's `asyncio` library for background task execution:
- `_run_task()` function executes shell commands in subprocesses
- Tasks are executed asynchronously using `asyncio.create_task()`
- Process management with timeouts and graceful cancellation
- Automatic cleanup of completed tasks

### 4. Task State Management
Tasks have a defined lifecycle with status transitions:
- PENDING → RUNNING → COMPLETED/FAILED/CANCELLED

### 5. Tool Registry System
The tool registry (`src/pilotcode/tools/registry.py`) manages all tools including task management tools:
- `register_tool()` for registering new tools
- `get_all_tools()` for retrieving all registered tools
- `get_tool_by_name()` for looking up specific tools

### 6. Task Status Enum
Defined in `task_tools.py`:
- PENDING: Task created but not yet started
- RUNNING: Task currently executing
- COMPLETED: Task finished successfully
- FAILED: Task execution failed
- CANCELLED: Task was cancelled

## Component Relationships

1. **Task Manager** interacts with the **Task Storage** to maintain task state
2. **Task Manager** uses the **Task Execution Engine** to run commands in the background
3. **Task Execution Engine** communicates with the **Task Storage** to update task status
4. **Tool Registry** provides access to all tools including the task management tools
5. **Task Status** is maintained through the **Task Storage** and updated by the **Task Execution Engine**

## Implementation Details

The system uses Python's async/await paradigm for handling concurrent background tasks. Each task runs in a separate asyncio task that executes shell commands through subprocess. The system implements proper error handling, timeouts, and cleanup mechanisms.

The architecture is lightweight and designed for simple task orchestration with a focus on integrating with larger systems through tools and commands.