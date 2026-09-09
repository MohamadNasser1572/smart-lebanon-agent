"""
LEIA — Full system integration test

Usage:
    python test_system.py          → offline mode using mock Claude responses
    python test_system.py --live   → uses real Claude API (needs ANTHROPIC_API_KEY)
"""

import os, sys, json, time, unittest.mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LIVE = "--live" in sys.argv

G="\033[92m"; Y="\033[93m"; R="\033[91m"; B="\033[94m"; BOLD="\033[1m"; END="\033[0m"
def ok(m):   print(f"{G}  \u2713 {m}{END}")
def fail(m): print(f"{R}  \u2717 {m}{END}")
def hdr(m):  print(f"\n{BOLD}{B}{'-'*55}\n  {m}\n{'-'*55}{END}")
def info(m): print(f"    {m}")

passed = failed = 0
def check(label, cond, detail=""):
    global passed, failed
    if cond:
        ok(label + (f"  ({detail})" if detail else "")); passed += 1
    else:
        fail(label + (f"  -- {detail}" if detail else "")); failed += 1

# -----------------------------------------------------------------------------
hdr("Layer 1 -- Knowledge base & local tools")
# -----------------------------------------------------------------------------
if not LIVE:
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-placeholder")

from agent.tools import kb_lookup, classify_threat, get_emergency_contacts

for region in ["beirut", "mount_lebanon", "north_lebanon", "south_lebanon", "bekaa"]:
    r = json.loads(kb_lookup(region, "all"))
    check(f"KB region '{region}'", "hospitals" in r and len(r["hospitals"]) > 0,
          f"{len(r['hospitals'])} hospitals, {len(r['shelters'])} shelters")

r = json.loads(kb_lookup("beirut", "hospitals"))
check("Beirut hospitals sorted trauma-first", r["hospitals"][0].get("trauma") is True)

r = json.loads(kb_lookup("south_lebanon", "evacuation_routes"))
check("South Lebanon evacuation routes", len(r["evacuation_routes"]) > 0)

r = json.loads(kb_lookup("bekaa", "shelters"))
check("Bekaa shelters", len(r["shelters"]) >= 2)

r = json.loads(kb_lookup("mars", "all"))
check("Bad region returns error gracefully", "error" in r)

scenarios = [
    ("Explosions reported near Dahieh Beirut", "beirut", 5),
    ("Clashes between armed groups in Tripoli street", "north_lebanon", 4),
    ("Protest blocking road in Hamra", "beirut", 3),
    ("Security advisory issued for Bekaa", "bekaa", 2),
    ("Clear skies, normal traffic in Jounieh", "mount_lebanon", 1),
]
for news, region, exp_min in scenarios:
    r = json.loads(classify_threat(region, news))
    check(f"Threat: '{news[:40]}'", r["level"] >= exp_min,
          f"level={r['level']} color={r['color']}")

r = json.loads(get_emergency_contacts("all"))
check("Civil Defense = 125", r["emergency_numbers"]["civil_defense"] == "125")
check("Red Cross = 140", r["emergency_numbers"]["red_cross_lebanon"] == "140")
check("NGOs loaded", len(r["ngos"]) >= 8, f"{len(r['ngos'])} orgs")

r = json.loads(get_emergency_contacts("medical"))
check("Medical filter works", len(r["ngos"]) > 0)

# -----------------------------------------------------------------------------
hdr(f"Layer 2 -- Agent loop ({'LIVE API' if LIVE else 'mock'})")
# -----------------------------------------------------------------------------
from agent.agent import create_user_message, create_assistant_message

if LIVE:
    from agent.agent import chat
else:
    from tests.mock_api import mock_chat as chat

TEST_QUERIES = [
    {"label": "Beirut safety + hospital",
     "message": "I'm in Hamra Beirut. What's the current security situation and nearest hospital?",
     "expect_keywords": ["beirut", "hospital"], "expect_tools": ["kb_lookup", "web_search_news"]},
    {"label": "South Lebanon travel",
     "message": "Is it safe to drive from Sidon to Tyre today?",
     "expect_keywords": ["sidon", "tyre"], "expect_tools": ["web_search_news"]},
    {"label": "Arabic -- hospital query",
     "message": "أين أقرب مستشفى في طرابلس؟",
     "expect_keywords": [], "expect_tools": ["kb_lookup"]},
    {"label": "Shelter request",
     "message": "I need to find a shelter in Bekaa Valley urgently",
     "expect_keywords": ["bekaa", "shelter"], "expect_tools": ["kb_lookup"]},
]

for t in TEST_QUERIES:
    print(f"\n  {Y}-> {t['label']}{END}")
    info(f'"{t["message"]}"')
    t0 = time.time()
    result = chat([create_user_message(t["message"])])
    elapsed = time.time() - t0
    resp = result["response"].lower()
    tools = [c["name"] for c in result["tool_calls_made"]]
    check(f"  Response received ({elapsed:.1f}s)", len(result["response"]) > 30,
          f"{len(result['response'])} chars")
    check(f"  Tools used", len(tools) > 0, ", ".join(tools))
    for kw in t["expect_keywords"]:
        check(f"  Contains '{kw}'", kw in resp)
    for etool in t["expect_tools"]:
        check(f"  Called {etool}", etool in tools)
    if result.get("threat_level"):
        check(f"  Threat level returned", True, f"level {result['threat_level']}")
    snippet = result["response"][:160].replace("\n", " ")
    info(f"{G}\u21b3{END} {snippet}...")

# -----------------------------------------------------------------------------
hdr("Layer 3 -- Multi-turn conversation memory")
# -----------------------------------------------------------------------------
history = []
turns = [
    "I'm in Tripoli north Lebanon",
    "Any trauma hospitals nearby?",
    "What's the evacuation route to Beirut from here?",
]
for turn in turns:
    history.append(create_user_message(turn))
    result = chat(history)
    history.append(create_assistant_message(result["response"]))
    check(f"Turn: '{turn}'", len(result["response"]) > 10,
          f"{len(result['tool_calls_made'])} tool calls")

check("History has 6 entries (3 turns x 2)", len(history) == 6)

# -----------------------------------------------------------------------------
hdr("Layer 4 -- FastAPI endpoints")
# -----------------------------------------------------------------------------
from tests.mock_api import mock_chat as _mc
patch_target = "api.chat" if not LIVE else None

ctx = unittest.mock.patch("api.chat", side_effect=lambda msgs: _mc(msgs)) if not LIVE else _NullCtx()

class _NullCtx:
    def __enter__(self): return None
    def __exit__(self, *a): return False

ctx = unittest.mock.patch("api.chat", side_effect=lambda msgs: _mc(msgs)) if not LIVE else _NullCtx()

with ctx:
    from fastapi.testclient import TestClient
    from api import app as fastapi_app

    client = TestClient(fastapi_app)

    r = client.get("/health")
    check("GET /health -> 200", r.status_code == 200)

    payload = {"message": "Shelter in Bekaa Valley?", "user_id": "test_1"}
    r = client.post("/chat", json=payload)
    check("POST /chat -> 200", r.status_code == 200)
    data = r.json()
    check("response field present", "response" in data and len(data["response"]) > 10)
    check("session_length tracked", data.get("session_length", 0) >= 1)
    check("tool_calls_made tracked", "tool_calls_made" in data)

    payload2 = {"message": "And the nearest hospital?", "user_id": "test_1"}
    r2 = client.post("/chat", json=payload2)
    check("Follow-up in same session", r2.status_code == 200)
    check("Session grew", r2.json().get("session_length", 0) > data.get("session_length", 0))

    r3 = client.delete("/chat/test_1")
    check("DELETE /chat/{id} clears session", r3.status_code == 200 and r3.json()["cleared"])

    form = {"Body": "I'm in Sidon, is it safe?", "From": "whatsapp:+9613000001",
            "To": "whatsapp:+14155238886", "ProfileName": "Ahmad"}
    r4 = client.post("/whatsapp", data=form)
    check("POST /whatsapp -> 200", r4.status_code == 200)
    check("WhatsApp returns TwiML", "<Response>" in r4.text and "<Message>" in r4.text)
    info(f"TwiML preview: {r4.text[:120].replace(chr(10), ' ')}...")

# -----------------------------------------------------------------------------
hdr("Layer 5 -- Gradio dashboard wiring")
# -----------------------------------------------------------------------------
ctx2 = unittest.mock.patch("ui.app.chat", side_effect=lambda msgs: _mc(msgs)) if not LIVE else _NullCtx()
with ctx2:
    from ui.app import respond, format_threat, clear_session

for level, hex_frag in [(1, "22c55e"), (3, "f97316"), (5, "dc2626")]:
    html = format_threat(level)
    check(f"Threat badge level {level}", hex_frag in html)
check("Threat badge None", "No threat" in format_threat(None))

h, s, t_html = clear_session()
check("clear_session resets history", h == [])
check("clear_session resets state", s["messages"] == [])

with ctx2:
    h_out, s_out, t_html2 = respond("Shelter in Bekaa?", [], {"messages": []})
check("respond() returns 1 chat turn (2 messages)", len(h_out) == 2)
check("respond() state has 2 messages", len(s_out["messages"]) == 2)
check("respond() returns threat HTML", "<div" in t_html2)

# -----------------------------------------------------------------------------
hdr(f"Results: {passed}/{passed+failed} passed")
# -----------------------------------------------------------------------------
if failed == 0:
    print(f"{G}{BOLD}  All {passed} tests passed.{END}")
    if not LIVE:
        print(f"\n  This was an OFFLINE run using mock responses.")
        print(f"  To test against the real Claude API:")
        print(f"    export ANTHROPIC_API_KEY=sk-ant-...")
        print(f"    python test_system.py --live\n")
    print(f"  To launch the dashboard:  python run.py")
    print(f"  To launch the API server: python run.py api\n")
else:
    print(f"{R}{BOLD}  {failed} test(s) failed.{END}\n")

sys.exit(0 if failed == 0 else 1)
