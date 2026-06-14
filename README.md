# AsgardMade Pantheon

Fully automated Etsy print-on-demand AI agent system. 10 specialist agents coordinated by ODIN, powered by Claude, running on FastAPI.

## Agents

| Agent | Role | Cycle |
|-------|------|-------|
| ODIN | Master orchestrator, strategic brain | 5 min |
| HERMES | Log scanner, anomaly detection | 60s |
| HEPHAESTUS | Auto-patcher, error fixer | On demand |
| ARGUS | System metrics monitor | 30s |
| ATHENA | Etsy analytics, revenue trends | 5 min |
| LOKI | Listing publisher, SEO optimizer | On demand |
| TYR | Security guardian, IP blocker | 60s |
| HEIMDALL | Niche researcher, idea generator | 2 min |
| VAULT | P&L tracker, financial reporting | 5 min |
| VULCAN | DALL-E design generator, Printify uploader | On demand |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in your API keys in .env
python main.py
```

Open `http://localhost:8000` in your browser.

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | Powers all agent chat intelligence |
| `OPENAI_API_KEY` | Optional | Real DALL-E 3 design generation (demo mode without) |
| `ETSY_API_KEY` | Optional | Live Etsy listing creation (demo mode without) |
| `ETSY_SHOP_ID` | Optional | Your Etsy shop ID |
| `PRINTIFY_API_KEY` | Optional | Live Printify product creation (demo mode without) |
| `PRINTIFY_SHOP_ID` | Optional | Your Printify shop ID |

## Pipeline Flow

1. **Heimdall** researches niches every 2 minutes → adds ideas to queue
2. **Commander** reviews ideas in HUD IDEA QUEUE tab → clicks APPROVE
3. **Vulcan** generates 2 DALL-E design variants → adds to design queue
4. **Commander** reviews designs → clicks APPROVE
5. **Vulcan** uploads approved design to Printify CDN, creates product
6. **Loki** creates optimized Etsy listing with SEO tags
7. **Vault** logs production cost ($8.50 Printify + $0.20 listing fee)
8. **Odin** broadcasts final confirmation to HUD

## API Endpoints

```
POST /api/chat              Chat with any agent
POST /api/chat/{agent}      Chat with named agent
GET  /api/status            All agent statuses
GET  /api/queue             Pending approval queue
POST /api/approve/{id}      Approve idea or design
POST /api/reject/{id}       Reject idea or design
GET  /api/vault             Financial P&L report
POST /api/heimdall/research Trigger niche research (optional: body {niche})
POST /api/vulcan/generate   Trigger design generation
WS   /                      Live event stream (WebSocket)
```

## Railway Deployment

1. Connect your GitHub repo to Railway
2. Set environment variables in Railway dashboard
3. Railway auto-detects the Procfile and deploys

The Procfile runs: `uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1`
