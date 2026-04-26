# Task Execution Lifecycle

This document outlines the complete lifecycle of tasks in the PilotCode system, from creation to completion.

## Task States

Tasks can exist in the following states:
1. **Pending** - Task created but not yet executed
2. **Running** - Task is currently executing
3. **Completed** - Task finished successfully
4. **Failed** - Task encountered an error during execution
5. **Cancelled** - Task was cancelled before completion

## Lifecycle Flow

### 1. Creation
- Task is created using `TaskCreate` tool
- Initial state is set to `PENDING`
- If a command is provided, execution begins immediately
- Task is stored in global `_tasks` dictionary with unique ID

### 2. Scheduling
- Tasks without commands remain in `PENDING` state
- Tasks with commands transition to `RUNNING` state
- Background execution is started using `asyncio.create_task()`

### 3. Execution
- For command-based tasks, a subprocess is created using `asyncio.create_subprocess_shell()`
- Execution has a 60-second timeout to prevent hanging
- Task state is updated based on execution result:
  - Success: `COMPLETED` state
  - Timeout: `FAILED` state with timeout error
  - Exception: `FAILED` state with error details
  - Cancelled: `CANCELLED` state

### 4. Completion
- Task status is updated to final state (`COMPLETED`, `FAILED`, or `CANCELLED`)
- Completion timestamp is recorded
- Result or error information is stored
- Task handle is cleaned up from `_task_handles` dictionary

## Task Management Operations

### TaskGet
- Retrieves task status and information
- Returns task details including state, timestamps, and results

### TaskList
- Lists tasks with optional filtering by status
- Returns task summaries sorted by creation time

### TaskStop
- Cancels running tasks
- Terminates subprocesses and cleans up resources

### TaskUpdate
- Updates task description or status
- Validates status transitions

## Error Handling

Tasks implement robust error handling:
- Timeout protection (60 seconds)
- Graceful cancellation handling
- Process termination on cancellation
- Error logging for failed executions