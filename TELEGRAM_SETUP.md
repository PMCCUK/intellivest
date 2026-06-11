# Telegram Notifications Setup — 5 minutes

## What you'll receive

Every time the AI engine runs you get a Telegram message like this:

```
🤖 IntelliVest AI Engine
Mon 09 Jun · 14:35 UTC · 🟢 Market open

📈 NEW BUYS (3)
  • BUY 5× NVDA @ £201.57 — Momentum breakout, volume 2x average
    AI Growth Fund
  • BUY 12× JPM @ £242.10 — Strong earnings beat, financials rotation
    AI Master

💼 Portfolio Summary
  🥇 AI Master: £126,727 (+26.73%) · 8 pos
  📈 AI Growth: £124,865 (+24.87%) · 6 pos
  📈 AI Value: £124,402 (+24.40%) · 5 pos

🧠 AI View: Technology showing strong momentum with semiconductor 
demand driving NVDA and AMD...

⚡ Action required in Trading 212:
  👉 Search NVDA → Buy 5 shares @ £201.57
  👉 Search JPM → Buy 12 shares @ £242.10

📊 Open IntelliVest Dashboard
```

---

## Step 1 — Create your Telegram bot (2 minutes)

1. Open Telegram and search for **@BotFather**
2. Send the message: `/newbot`
3. When asked for a name, type: `IntelliVest AI`
4. When asked for a username, type something unique like: `intellivest_yourname_bot`
5. BotFather will reply with your **bot token** — it looks like:
   ```
   5839201847:AAHdqTcvCHhvQepHUti_OVX3lVs_W2pO6HE
   ```
6. **Copy and save this token**

---

## Step 2 — Get your Chat ID (1 minute)

1. In Telegram, search for your new bot (the username you just created)
2. Press **Start** or send `/start`
3. Now open this URL in your browser (replace YOUR_TOKEN with your actual token):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
4. You'll see JSON. Find the number after `"id":` inside `"chat"` — that's your Chat ID
   ```json
   {"chat": {"id": 123456789, ...}}
   ```
5. **Copy that number** — e.g. `123456789`

---

## Step 3 — Add secrets to GitHub (2 minutes)

Go to: `https://github.com/PMCCUK/intellivest/settings/secrets/actions`

Add two new secrets:

| Name | Value |
|------|-------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from Step 1 |
| `TELEGRAM_CHAT_ID` | Your chat ID from Step 2 |

---

## Step 4 — Test it

Go to GitHub Actions → Run workflow manually with `force_run: true`

You should receive a Telegram message within 2 minutes.

---

## Message types you'll receive

| Message | When |
|---------|------|
| 🌅 Morning Briefing | First run of each trading day |
| 🤖 Engine Run | Every run (7× per trading day) |
| 📈 New Buys | When AI opens new positions |
| 📉 Sells/Closes | When AI closes positions |
| 🛑 Stop Loss | When a position hits stop loss |
| ✅ Take Profit | When a position hits take profit |

---

## Muting after-hours notifications

If you don't want to receive the pre-market (08:00 EST = 13:00 UK) notification,
you can mute it in Telegram:
- Long press the IntelliVest bot chat
- Select "Mute notifications"
- Set to "Mute for 8 hours" each morning if needed

Or simply ignore messages you don't act on — they're informational only.
