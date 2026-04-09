---
name: docker-build
description: Build Docker images with best practices
argumentHint: "[path]"
allowedTools: [Bash, Read]
---

Build a Docker image with the following steps:

1. Check for Dockerfile at {path}
2. Review the Dockerfile for best practices
3. Suggest optimizations (multi-stage builds, layer caching, etc.)
4. Provide the build command

Path: {path}
