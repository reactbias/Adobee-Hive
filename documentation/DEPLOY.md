# Run and deploy

## Locally

```bash
# backend
cd code/backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q                                   # includes an end-to-end booking over MCP
ANTHROPIC_API_KEY=sk-ant-... uvicorn app.main:app --reload --port 8000

# frontend (another terminal)
cd code/frontend && npm install && npm run dev   # http://localhost:5173
```

Or the whole stack: `cd code && cp .env.example .env` (add the key), then `docker compose up --build`
(frontend on 5173, backend on 8000).

Without `ANTHROPIC_API_KEY` everything still runs: a scripted planner walks the same MCP tools, and owner edits fall
back to simple rules ("add sauna").

### Point any agent at the Hive

The MCP endpoint is `http://localhost:8000/mcp/` (Streamable HTTP), also listed in `/.well-known/hive.json`. Add it
as a custom connector in Claude and ask: *"Find me a dog-friendly hotel near Basel SBB under CHF 200 for next
weekend and book it."*

## AWS: every push to `main` deploys itself

| Part | Service | Trigger | Config |
| --- | --- | --- | --- |
| Frontend | Amplify Hosting, monorepo app root `code/frontend` | Amplify watches `main` | `amplify.yml` |
| Backend | App Runner, image from ECR, auto-deploy on new image | GitHub Action on changes under `code/backend/` | `.github/workflows/deploy-backend.yml`, `code/backend/Dockerfile` |
| Claude key | Secrets Manager, injected into App Runner | Set once | `code/scripts/aws/bootstrap.sh` |
| Data | DuckDB file, snapshot to S3 after each write, restored on boot | Automatic | `code/backend/app/storage.py` |

Region: `eu-central-1` (Frankfurt).

One-time setup, about 15 minutes:

1. `AWS_PROFILE=... ANTHROPIC_API_KEY=... ./code/scripts/aws/bootstrap.sh` (needs Docker and the AWS CLI). It
   creates the ECR repo, S3 bucket, secret, IAM roles and the App Runner service, and prints the backend URL.
2. GitHub repo secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (an IAM user that can push to ECR).
3. Amplify console: *New app*, connect this repo, branch `main`, tick monorepo with root `code/frontend`.
   Environment variable `VITE_API_URL` = the backend URL. Under *Rewrites and redirects* add
   `</^[^.]+$|\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json|webp)$)([^.]+$)/>` → `/index.html` (200)
   so deep links like `/card/rheinblick` work.
4. Push to `main`.

## Cost guard for the demo key

The booking agent uses `claude-opus-5-5` at low effort with prompt caching on the tool definitions; owner edits use
`claude-haiku-5-5`. Change either with `CLAUDE_MODEL` / `CLAUDE_FAST_MODEL`. `AGENT_MAX_TURNS` caps each agent run.
