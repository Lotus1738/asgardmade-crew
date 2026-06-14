# AsgardMade — Mario's Manual To-Do List

> Everything below requires your credentials or account access. Claude handles the code; you handle the keys.

---

## 🔑 API Keys to Add in Railway (Environment Variables)

| Variable | Where to Get It |
|---|---|
| `HF_KEY` | cloud.higgsfield.ai → API Keys (format: `api_key:api_secret`) |
| `PINTEREST_TOKEN` | developers.pinterest.com → My Apps → Create App → OAuth token |
| `PINTEREST_BOARD_ID` | Open your Pinterest board → copy the ID from the URL |
| `DISCORD_WEBHOOK_URL` | Discord server → Settings → Integrations → Webhooks → New Webhook |
| `TWILIO_ACCOUNT_SID` | twilio.com → Console Dashboard |
| `TWILIO_AUTH_TOKEN` | twilio.com → Console Dashboard |
| `TWILIO_FROM_NUMBER` | twilio.com → Phone Numbers (your Twilio number) |
| `TWILIO_TO_NUMBER` | Your personal phone number (receives daily SMS briefing) |

**How to add to Railway:** railway.app → Your project → Variables → Add each one above

---

## 📱 Accounts to Create (if not already done)

- **Redbubble seller account** — redbubble.com/sell (no API, but the system formats content for manual upload)
- **Amazon Merch by Amazon** — merch.amazon.com (apply for access — has a waitlist, apply ASAP)
- **Pinterest Business account** — needed for API access (convert at pinterest.com/business/create)

---

## ⚙️ One-Time Setup Steps

1. **Pinterest board** — Create a board called "AsgardMade Designs" and copy its ID for `PINTEREST_BOARD_ID`
2. **Discord** — Create a `#pantheon-alerts` channel in your server, add a webhook to it
3. **Higgsfield** — Sign up at higgsfield.ai, go to cloud.higgsfield.ai, generate API keys
4. **Twilio** — Free trial gives you $15 credit (enough for hundreds of daily SMS). Verify your personal number as the `TO` number.

---

## 🤖 What's Fully Automated (Claude handles this)

- Niche research & idea generation (HEIMDALL)
- Design creation via Higgsfield → DALL-E fallback (VULCAN)
- Etsy listing creation & publishing (LOKI)
- Pinterest auto-pinning after each listing (once `PINTEREST_TOKEN` is set)
- Discord notifications for sales, approvals, daily briefing (once `DISCORD_WEBHOOK_URL` is set)
- Daily SMS briefing (once Twilio keys are set)
- Sales data feeding back into niche selection (automatic)
- Bestseller niche auto-requeue every 6 hours (automatic)
- Printify mockup generation before listing (automatic)
- Content formatted for Redbubble + Amazon manual upload (automatic)

---

*Last updated: June 14, 2026*
