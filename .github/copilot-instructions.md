# GitHub Copilot Instructions

## Project Overview

This is an OpenClaw Gateway Docker deployment project. OpenClaw is an AI agent gateway that manages conversations, tasks, and integrations.

## Project Structure

- `docker-compose.yml` - Docker Compose configuration for running the OpenClaw gateway
- `data/` - Persistent data directory mounted into the container
  - `openclaw.json` - Main configuration file
  - `devices/` - Device pairing and authentication
  - `identity/` - Device identity information
  - `logs/` - Application logs
  - `tasks/` - Background task state (SQLite)
  - `canvas/` - Custom canvas/web interface files

## Code Style & Conventions

- Use YAML for configuration files
- Follow Docker best practices for container security
- Keep sensitive data (tokens, passwords) out of version control

## Key Configuration

- Gateway binds to `0.0.0.0:18789` inside container (mapped to `127.0.0.1:18789` on host)
- Authentication mode: token-based
- Timezone: Asia/Shanghai

## When Making Changes

1. Always validate YAML syntax before committing
2. Remember YAML requires spaces after colons (`: `) and hyphens (`- `)
3. Test docker-compose changes with `docker compose config` before `docker compose up`
4. Back up `data/openclaw.json` before making configuration changes

## Security Considerations

- The gateway should only be exposed on localhost (`127.0.0.1`)
- Container runs with reduced capabilities (`NET_RAW`, `NET_ADMIN` dropped)
- `no-new-privileges` security option is enabled
