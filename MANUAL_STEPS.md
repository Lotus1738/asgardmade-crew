# Manual Steps Required — AsgardMade Pantheon

## 🔴 REQUIRED RIGHT NOW

### 1. Push all changes to GitHub
Open a terminal in `C:\Users\Mario\asgardmade-crew` and run:
```
del .git\HEAD.lock
git add -A
git commit -m "Hub layout ODIN center, agent display names, gpt-image-1, DDG search, bug fixes"
git push
```
Railway auto-deploys on push. Changes go live ~2 minutes after push.

---

## 🔑 ENVIRONMENT VARIABLES (set in Railway)

Go to Railway → your project → Variables tab:

| Variable | Status | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ Required | Powers all 6 agents (Claude Haiku) |
| `OPENAI_API_KEY` | ⚠️ Required for real designs | gpt-image-1 image generation. Without it, Vulcan uses demo placeholder images. |
| `PRINTIFY_API_KEY` | ⚠️ Required for live products | Without it, Printify steps run in demo mode (no actual product created) |
| `PRINTIFY_SHOP_ID` | ⚠️ Required for live products | Your Printify shop ID (numeric string) |
| `ETSY_API_KEY` | ⚠️ Required for live listings | Without it, Loki uses demo mode (no actual Etsy listing created) |
| `ETSY_SHOP_ID` | ⚠️ Required for live listings | Your Etsy shop ID |
| `SERPER_API_KEY` | 🔵 Optional | Google search for Heimdall research. Without it, DuckDuckGo (free) is used automatically. |

**To check which keys are active:** look at the HUD header — `APIS` dot turns green when all keys work.

---

## 🏪 PRINTIFY SETUP

1. Sign up at printify.com
2. Create a shop
3. Connect Etsy as the sales channel
4. Go to API settings → copy your API key
5. Copy your Shop ID from the URL: `printify.com/app/shop/YOUR_SHOP_ID/...`
6. Set both in Railway env vars

---

## 🛒 ETSY SETUP

1. Create an Etsy seller account at etsy.com/sell
2. Go to etsy.com/developers → create an app
3. Generate an API key + access token
4. Set `ETSY_API_KEY`, `ETSY_SHOP_ID` in Railway

---

## 📁 DATA PERSISTENCE (Railway)

Railway's filesystem resets on redeploy. To persist agent memory and queue:

- **Option A (free):** Mount a Railway volume → set `DATA_DIR` env var to `/data`
- **Option B (recommended):** Use a free Postgres or Redis add-on and migrate `data/` writes there

For now, agent XP, ideas queue, and vault data survive between restarts but reset on full redeploy.

---

## ⏰ SCHEDULED TASKS

The `pantheon-self-improve` scheduled task runs every 45 minutes **only while the Cowork app is open**. If you want continuous improvement:
- Keep the app running, OR
- Deploy to Railway (it runs 24/7 there automatically via the background loops)

---

## 🔍 HOW TO VERIFY EVERYTHING IS WORKING

After pushing + Railway deploys:

1. Open your Railway URL
2. Check HUD header: all 4 dots (NEXUS, AGENTS, APIS, SECURE) should be green
3. Look at LIVE LOG STREAM — should see GUARDIAN scanning, HEIMDALL generating ideas
4. Click any agent room to chat with them
5. If you see "demo" in logs = that integration's API key is missing

---

## 🐛 KNOWN DEMO-MODE INDICATORS

- `Design generation: Demo mode — set OPENAI_API_KEY` → missing OpenAI key
- `Printify image upload: demo` → missing Printify credentials  
- `Etsy listing created (demo)` → missing Etsy credentials
- Shop stats show `$0.00 today` → Etsy API not connected
