# LEIA — Lebanon Emergency Intelligence Agent

[![Tests](https://github.com/MohamadNasser1572/smart-lebanon-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/MohamadNasser1572/smart-lebanon-agent/actions/workflows/tests.yml)

AI-powered real-time situational awareness and crisis guidance for Lebanon.
Built for Develeb AI Agents Hackathon 2026.

## What it does

1. **Situational awareness** — searches live Lebanon news and classifies threat level 1-5 per region
2. **Citizen guidance** — clear, step-by-step safety instructions based on location and situation
3. **Local knowledge** — every hospital (trauma flag), shelter, evacuation route across Lebanon's 5 regions
4. **Multi-language** — responds in Arabic or English automatically
5. **Multi-channel** — web dashboard (Gradio) and WhatsApp (Twilio webhook via FastAPI)

---

## Quick start (open this folder in VS Code / Antigravity)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```
Windows PowerShell: `$env:ANTHROPIC_API_KEY="sk-ant-your-key-here"`

(`.env.example` is included -- copy to `.env` and fill in if you prefer)

### 3. Run it

| Command | What it does | URL |
|---|---|---|
| `python run.py` | **Web dashboard** (the demo) | http://127.0.0.1:7860 |
| `python run.py api` | REST API + WhatsApp webhook | http://127.0.0.1:8000/docs |
| `python run.py test` | Offline test suite (no key needed) | terminal |
| `python run.py test-live` | Full test against real Claude API | terminal |

**For the hackathon demo, just run `python run.py`** -- opens a chat dashboard
with a live threat-level badge, example queries, and emergency numbers panel.

---

## Project structure

```
smart-lebanon-agent/
├── run.py              <- SINGLE ENTRY POINT, start here
├── api.py              <- FastAPI backend (REST + Twilio WhatsApp webhook)
├── test_system.py      <- Full test suite (offline by default)
├── requirements.txt
├── .env.example
├── agent/
│   ├── __init__.py
│   ├── agent.py        <- Orchestrator + Claude tool-calling loop
│   └── tools.py         <- Tool implementations
├── data/
│   └── lebanon_kb.json <- Knowledge base: hospitals, shelters, contacts, routes
├── tests/
│   ├── __init__.py
│   └── mock_api.py      <- Mock responses for offline testing
└── ui/
    ├── __init__.py
    └── app.py            <- Gradio dashboard (the demo)
```

## First run checklist

```bash
cd smart-lebanon-agent
pip install -r requirements.txt
python test_system.py          # "All 64 tests passed" -- offline, no key needed
export ANTHROPIC_API_KEY=sk-ant-...
python run.py                  # opens the dashboard
```

## WhatsApp setup (Twilio, optional)

1. Create a Twilio account, get a WhatsApp sandbox number
2. Run `python run.py api`
3. Expose it: `ngrok http 8000`
4. Set the Twilio webhook URL to `https://your-ngrok-url.ngrok.io/whatsapp`
5. Message your sandbox number -- LEIA responds!

## Architecture

```
User (Web dashboard / WhatsApp)
        |
   Gradio UI  /  FastAPI
        |
   Agent orchestrator (agent/agent.py)
        |
   Claude (tool-calling loop)
        |
   web_search_news | kb_lookup | classify_threat | get_emergency_contacts
   (live news)     | (static KB)| (LLM+keywords)  | (NGO/emergency numbers)
```

## Threat levels

| Level | Color | Meaning | Action |
|-------|-------|---------|--------|
| 1 | Green  | Safe | Normal precautions |
| 2 | Yellow | Monitor | Stay alert, watch news |
| 3 | Orange | Caution | Avoid non-essential travel |
| 4 | Red    | Danger | Stay indoors, follow guidance |
| 5 | Dark red | Critical | Evacuate if instructed |

