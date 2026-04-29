# PilotCode E2E Code Generation Tests

End-to-end tests for evaluating PilotCode's code generation capabilities across CLI and WebSocket modes.

## Structure

```
tests/e2e/
├── run_e2e_tests.py          # Main test runner
├── analyze_results.py        # Result analyzer / comparator
├── tasks/
│   ├── c_simple/             # Simple C tasks (linked list, stack, sorting, etc.)
│   │   ├── linked_list.yaml
│   │   ├── stack.yaml
│   │   ├── sorting.yaml
│   │   ├── string_utils.yaml
│   │   └── file_reader.yaml
│   ├── c_complex/            # Complex C tasks (AVL, hash table, pthread, etc.)
│   │   ├── avl_tree.yaml
│   │   ├── hash_table.yaml
│   │   ├── ring_buffer.yaml
│   │   ├── memory_pool.yaml
│   │   └── json_parser.yaml
│   └── python/               # Python tasks (placeholder)
└── README.md
```

## Task YAML Format

Each task is defined by a YAML file:

```yaml
task_id: c_simple_linked_list
category: c_simple
description: Singly linked list in C99
prompt: |
  请帮我实现一个C语言单链表...
expected_files:
  - linked_list.h
  - linked_list.c
  - main.c
  - Makefile
compile_command: ["make"]
run_command: ["./main"]
expected_output_contains:
  - "链表"
  - "List"
timeout_seconds: 600
```

## Usage

### Prerequisites

```bash
pip install pyyaml websockets
```

### Run CLI Mode Tests

```bash
# Run simple C tasks
cd tests/e2e
python run_e2e_tests.py --category c_simple --mode cli

# Run complex C tasks
python run_e2e_tests.py --category c_complex --mode cli

# Run all categories
python run_e2e_tests.py --category all --mode cli

# Custom timeout (default: 360s)
python run_e2e_tests.py --category c_complex --mode cli --timeout 600
```

### Run WebSocket Mode Tests

Start the WebSocket server with `--auto-allow` first:

```bash
python -m pilotcode --web --web-port 8082 --auto-allow
```

Then run tests:

```bash
cd tests/e2e
python run_e2e_tests.py --category c_complex --mode websocket

# Custom WebSocket URL / timeout
python run_e2e_tests.py --category c_complex --mode websocket \
    --ws-url ws://127.0.0.1:8083 \
    --ws-recv-timeout 300 \
    --timeout 600
```

### Analyze Results

```bash
# Single run report
python analyze_results.py ~/test/pilotcode_e2e_results/20250429_123456/summary.json

# Compare CLI vs WebSocket
python analyze_results.py \
    ~/test/pilotcode_e2e_results/20250429_cli/summary.json \
    ~/test/pilotcode_e2e_results/20250429_ws/summary.json
```

## Output

Results are saved to `~/test/pilotcode_e2e_results/<run_id>/`:

```
~/test/pilotcode_e2e_results/20250429_123456/
├── summary.json              # Aggregated results
├── logs/
│   ├── c_simple_linked_list.log
│   ├── c_simple_stack.log
│   └── ...
└── generated/
    ├── c_simple_linked_list/
    │   ├── linked_list.h
    │   ├── linked_list.c
    │   ├── main.c
    │   └── Makefile
    └── ...
```

## Adding New Tasks

1. Create a new YAML file in `tasks/<category>/`
2. Define `task_id`, `prompt`, `expected_files`, `compile_command`, `run_command`
3. Run with `--category <category>`

## Example Results

| Task | CLI Compile | CLI Run | WS Compile | WS Run |
|------|-------------|---------|------------|--------|
| AVL Tree | ✅ | ✅ | ✅ | ✅ |
| Hash Table | ✅ | ✅ | ✅ | ✅ |
| Ring Buffer (pthread) | ✅ | ✅ | ✅ | ✅ |
| Memory Pool | ✅ | ✅ | ✅ | ✅ |
| JSON Parser | ✅ | ✅ | ✅ | ✅ |
