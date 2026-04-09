---
name: docker-compose
description: Analyze and fix docker-compose files
aliases: [dc, compose]
allowedTools: [Read, Glob, Bash]
whenToUse: When working with docker-compose.yml files
---

Please analyze the docker-compose file at {path} and help with:

1. Service configuration review
2. Network and volume setup
3. Environment variables
4. Health checks
5. Resource limits

File to analyze: {path}

Provide recommendations for improvements and best practices.
