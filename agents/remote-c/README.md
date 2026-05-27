# PilotCode Remote Agent (C)

Pure C implementation, zero external dependencies, single-file source.

## Build

```bash
# Dynamic link (uses system libc)
gcc -O2 -s -o agent agent.c

# Fully static binary (recommended for embedded deployment)
gcc -O2 -s -static -o agent agent.c

# Cross compile for ARM64 (using musl-cross toolchain)
aarch64-linux-musl-gcc -O2 -s -static -o agent-arm64 agent.c

# Cross compile for ARM32
arm-linux-musleabihf-gcc -O2 -s -static -o agent-arm32 agent.c
```

## Size

```bash
# Typical binary size after strip:
# x86_64:  ~20-30 KB
# ARM64:   ~25-35 KB
# ARM32:   ~20-25 KB
```

## Deploy

```bash
scp agent user@board:/usr/local/bin/pilotcode-remote-agent
ssh user@board pilotcode-remote-agent
```

## Protocol

JSON-RPC over stdin/stdout, one line per message.

### Methods

| Method | Params | Description |
|--------|--------|-------------|
| `ping` | - | Health check |
| `read_file` | `path` | Read text file (rejects binary) |
| `write_file` | `path`, `content` | Write/overwrite file |
| `exec` | `command`, `cwd?` | Execute shell command |

### Example

```bash
$ echo '{"id":1,"method":"read_file","params":{"path":"/etc/hostname"}}' | ./agent
{"id":1,"result":{"content":"myboard\n"}}
```

## Limitations

- `read_file` max: 16MB, refuses binary (null bytes in first 4KB)
- `write_file` content max: 64KB per request (use chunked writes for larger files)
- `exec` stdout max: 64KB (suitable for build logs, not large binary output)
- JSON parser is minimal: supports strings, numbers, objects, arrays; no unicode escape handling beyond basic `\uXXXX`
