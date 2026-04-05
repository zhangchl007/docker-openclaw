# OpenClaw Docker Deployment

Docker-based deployment for OpenClaw AI Gateway.

## Quick Start

```bash
# Clone the repository
git clone <your-repo-url>
cd openclaw-docker

# Enable pre-commit security hook
git config core.hooksPath .githooks

# Start the gateway
docker compose up -d
```

## Access Dashboard

Open in browser: http://localhost:18789/

## Configuration

Edit `data/openclaw.json` or use CLI:

```bash
docker exec openclaw openclaw config set <key> <value>
```

## Logs

```bash
docker compose logs -f
```

## Security

⚠️ **Important Security Notes:**

- Gateway only listens on localhost (127.0.0.1)
- Token-based authentication enabled
- Container runs with reduced privileges
- **NEVER commit the `data/` directory contents** (except `canvas/`)
- The `.gitignore` protects sensitive files, but always verify before pushing
- Use the pre-commit hook: `git config core.hooksPath .githooks`

### Sensitive Files (Protected by .gitignore)

| Path | Contains |
|------|----------|
| `data/openclaw.json` | Auth tokens |
| `data/identity/` | Private keys |
| `data/devices/` | Device tokens |
| `data/logs/` | May contain sensitive info |

### Verify Before Pushing

```bash
# Check what will be committed
git status

# Ensure no secrets are staged
git diff --cached --name-only | grep -E "data/(openclaw|identity|devices)" && echo "WARNING: Secrets detected!"
```
