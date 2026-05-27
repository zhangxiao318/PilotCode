# PilotCode Remote Agent

Minimal static-binary agent for remote embedded development.

## Build

```bash
# Native binary
cargo build --release

# Static binary for Linux (no libc dependency)
cargo build --target x86_64-unknown-linux-musl --release

# ARM64 (Raspberry Pi, embedded Linux)
cargo build --target aarch64-unknown-linux-musl --release

# ARM32 (older boards)
cargo build --target armv7-unknown-linux-musleabihf --release
```

## Deploy

```bash
scp target/release/pilotcode-remote-agent user@board:/usr/local/bin/
ssh user@board pilotcode-remote-agent
```

## Protocol

JSON-RPC over stdin/stdout, one line per message.

### Request

```json
{"id":1,"method":"read_file","params":{"path":"/home/user/main.c"}}
```

### Response

```json
{"id":1,"result":{"content":"#include <stdio.h>\n..."}}
```

### Methods

| Method | Params | Description |
|--------|--------|-------------|
| `ping` | - | Health check |
| `read_file` | `path` | Read file as UTF-8 |
| `write_file` | `path`, `content` | Write/overwrite file |
| `exec` | `command`, `cwd?` | Execute shell command |
