"""
Mock Claude responses for offline testing (no API key needed).
Used by test_system.py in default mode.
"""

MOCK_RESPONSES = {
    "beirut_safety": {
        "response": """Current situation in Hamra, Beirut: threat level 2 (monitor).

**Nearest hospitals:**
1. American University of Beirut Medical Center (AUBMC) — +961-1-350000 — Trauma center
2. Hotel Dieu de France — +961-1-615300 — Achrafieh

**Recommended actions:**
1. Stay alert and monitor local news (NNA, LBCI)
2. Keep phone charged
3. Note evacuation route: Beirut Ring Road → Antelias (North)

Emergency: Civil Defense 125 | Red Cross 140""",
        "threat_level": 2,
        "tool_calls_made": [
            {"name": "web_search_news", "input": {"query": "Beirut Hamra security situation today", "region": "beirut"}},
            {"name": "kb_lookup", "input": {"region": "beirut", "info_type": "hospitals"}},
            {"name": "classify_threat", "input": {"region": "beirut", "news_context": "Normal activity reported"}},
        ],
    },
    "south_travel": {
        "response": """Travel advisory Sidon → Tyre: coastal road currently passable.

**Route:** Coastal highway south, ~45 minutes.
**Caution:** Monitor Civil Defense announcements before departure.

Emergency: 125 (Civil Defense)""",
        "threat_level": 2,
        "tool_calls_made": [
            {"name": "web_search_news", "input": {"query": "south Lebanon Sidon Tyre road safe today"}},
            {"name": "kb_lookup", "input": {"region": "south_lebanon", "info_type": "evacuation_routes"}},
        ],
    },
    "arabic_hospital": {
        "response": """أقرب المستشفيات في طرابلس:
1. مستشفى طرابلس الحكومي — +961-6-628000 — مركز صدمات
2. المستشفى الإسلامي في طرابلس — +961-6-442000

للطوارئ: اتصل بـ 140 (الصليب الأحمر) أو 125 (الدفاع المدني)""",
        "threat_level": 1,
        "tool_calls_made": [
            {"name": "kb_lookup", "input": {"region": "north_lebanon", "info_type": "hospitals"}},
        ],
    },
    "bekaa_shelter": {
        "response": """Bekaa Valley shelters:
1. Zahle Municipality Center — capacity 600 — Zahle center
2. Chtaura Community Hall — capacity 250 — Chtaura
3. Baalbek Roman Temple Grounds — capacity 400

Head to Zahle Municipality Center first — largest, officially managed.

Emergency: Civil Defense 125""",
        "threat_level": 3,
        "tool_calls_made": [
            {"name": "kb_lookup", "input": {"region": "bekaa", "info_type": "shelters"}},
            {"name": "web_search_news", "input": {"query": "Bekaa Valley security alert today", "region": "bekaa"}},
        ],
    },
    "default": {
        "response": "Based on current information, stay alert and contact Civil Defense at 125 for real-time guidance.",
        "threat_level": 2,
        "tool_calls_made": [{"name": "web_search_news", "input": {"query": "Lebanon security"}}],
    },
}


def mock_chat(messages: list) -> dict:
    if not messages:
        return MOCK_RESPONSES["default"]
    last = messages[-1].get("content", "")
    if isinstance(last, list):
        last = " ".join(b.get("text", "") for b in last if isinstance(b, dict))
    last = last.lower()

    if "hamra" in last or ("beirut" in last and "situation" in last):
        return MOCK_RESPONSES["beirut_safety"]
    if "sidon" in last or "tyre" in last or ("travel" in last and "lebanon" in last):
        return MOCK_RESPONSES["south_travel"]
    if "طرابلس" in last or "مستشفى" in last:
        return MOCK_RESPONSES["arabic_hospital"]
    if "bekaa" in last or "shelter" in last:
        return MOCK_RESPONSES["bekaa_shelter"]
    if "tripoli" in last:
        return MOCK_RESPONSES["arabic_hospital"]
    return MOCK_RESPONSES["default"]
