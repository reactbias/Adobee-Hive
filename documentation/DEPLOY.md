# Run and deploy

## Locally

```bash
# backend
cd code/backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q                                   # includes an end-to-end booking over MCP
OPENAI_API_KEY=... uvicorn app.main:app --reload --port 8000   # the key is optional

# frontend (another terminal)
cd code/frontend && npm install && npm run dev   # http://localhost:5173
```

Or the whole stack: `cd code && cp .env.example .env` (add the key), then `docker compose up --build`
(frontend on 5173, backend on 8000).

The agents run on **OpenAI** when `OPENAI_API_KEY` is set (`OPENAI_MODEL`, default `gpt-5-mini`): the booking agent,
owner edits, and the sceptic that reviews each held booking before you approve. Claude is an alternative: set
`ANTHROPIC_API_KEY` without an OpenAI key, or `LLM_PROVIDER=claude`. Without any key everything still runs: a
scripted planner walks the same MCP tools, owner edits fall back to simple rules ("add sauna"), a rule check gives the
second opinion, and the header shows **Offline mode**.

### Point any agent at the Hive

The MCP endpoint is `http://localhost:8000/mcp/` (Streamable HTTP), also listed in `/.well-known/hive.json`. Add it
as a custom connector in Claude and ask: *"Find me a dog-friendly hotel near Basel SBB under CHF 200 for next
weekend and book it."*

## AWS: every push to `main` deploys itself

| Part | Service | Trigger | Config |
| --- | --- | --- | --- |
| Frontend | Amplify Hosting, monorepo app root `code/frontend` | Amplify watches `main` | `amplify.yml` |
| Backend | App Runner, image from ECR, auto-deploy on new image | GitHub Action on changes under `code/backend/` | `.github/workflows/deploy-backend.yml`, `code/backend/Dockerfile` |
| OpenAI (and optional Claude) key | Secrets Manager, injected into App Runner | Set once | `code/scripts/aws/bootstrap.sh` |
| Data | DuckDB file, snapshot to S3 after each write, restored on boot | Automatic | `code/backend/app/storage.py` |

Region: `eu-central-1` (Frankfurt).

One-time setup, about 15 minutes:

1. `AWS_PROFILE=... OPENAI_API_KEY=... ./code/scripts/aws/bootstrap.sh` (needs Docker and the AWS CLI; pass
   `ANTHROPIC_API_KEY` too or instead to use Claude). It creates the ECR repo, S3 bucket, secrets, IAM roles and the
   App Runner service, and prints the backend URL.
2. GitHub repo secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (an IAM user that can push to ECR).
3. Amplify console: *New app*, connect this repo, branch `main`, tick monorepo with root `code/frontend`.
   Environment variable `VITE_API_URL` = the backend URL. Under *Rewrites and redirects* add
   `</^[^.]+$|\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json|webp)$)([^.]+$)/>` → `/index.html` (200)
   so deep links like `/card/rheinblick` work.
4. Push to `main`.

The bootstrap prints two team secrets: the **owner token** (the owner studio asks for it before an edit) and the
**demo token** (`X-Demo-Token` for `POST /api/demo/reset`). Share them in person or through a password manager.

## Cost guard for the demo key

On OpenAI every call uses `OPENAI_MODEL` (default `gpt-5-mini`) at low reasoning effort with `store=false`. On
Claude the booking agent uses `CLAUDE_MODEL` with prompt caching and owner edits use `CLAUDE_FAST_MODEL`.
`AGENT_MAX_TURNS` caps each agent run. Calls that may reach a model are limited to `LLM_CALLS_PER_CLIENT_HOUR` (30)
per client and `LLM_CALLS_TOTAL_HOUR` (300) in total. If the model fails, the agent finishes the run with the offline
planner and says so, owner edits use the rules, and the rule check gives the second opinion.
