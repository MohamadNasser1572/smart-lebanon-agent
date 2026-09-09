"""
Tool implementations for the Lebanon Emergency Agent.
Each function maps to one tool Groq can call.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from groq import Groq

# ── Load the knowledge base once at import time ──────────────────────────────
_KB_PATH = Path(__file__).parent.parent / "data" / "lebanon_kb.json"
with open(_KB_PATH, "r", encoding="utf-8") as f:
    KB = json.load(f)

# Lazy client - instantiated on first use so import works without the env var
_client: Groq | None = None


def _groq_model() -> str:
    return os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


# ── Tool 1: Live news search ─────────────────────────────────────────────────

def web_search_news(query: str, region: str = "all") -> str:
    """
    Search for live Lebanon news using Google News RSS.
    Returns a JSON string with headlines and summaries.
    """
    region_hint = ""
    if region and region != "all":
        region_map = {
            "beirut": "Beirut Lebanon",
            "mount_lebanon": "Mount Lebanon Metn Kesrouan Chouf",
            "north_lebanon": "Tripoli North Lebanon Akkar",
            "south_lebanon": "South Lebanon Sidon Tyre Nabatieh",
            "bekaa": "Bekaa Valley Zahle Baalbek",
        }
        region_hint = f" {region_map.get(region, '')}"

    full_query = f"{query}{region_hint} Lebanon"

    try:
        rss_url = "https://news.google.com/rss/search?q=" + quote(full_query)
        request = Request(rss_url, headers={"User-Agent": "LEIA/1.0"})
        with urlopen(request, timeout=8) as response:
            root = ET.fromstring(response.read())
        results = []
        for item in root.findall("./channel/item")[:8]:
            title = item.findtext("title", "").strip()
            source = item.findtext("source", "Lebanon news").strip()
            link = item.findtext("link", "").strip()
            published = item.findtext("pubDate", "").strip()
            results.append({
                "headline": title,
                "source": source,
                "summary": title,
                "url": link,
                "published": published,
            })
        return json.dumps({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "query": query,
            "results": results,
            "overall_summary": " ".join(item["headline"] for item in results[:3]) or "No recent results found.",
        })

    except Exception as e:
        return json.dumps({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "query": query,
            "results": [],
            "overall_summary": f"Search unavailable: {str(e)}. Check Civil Defense at 125 for updates.",
            "error": str(e),
        })


# ── Tool 2: Knowledge base lookup ────────────────────────────────────────────

def kb_lookup(region: str, info_type: str) -> str:
    """
    Look up static Lebanon knowledge base.
    Returns shelters, hospitals, evacuation routes, or safe zones for a region.
    """
    region_data = KB.get("regions", {}).get(region)
    if not region_data:
        available = list(KB.get("regions", {}).keys())
        return json.dumps({
            "error": f"Region '{region}' not found.",
            "available_regions": available,
        })

    if info_type == "all":
        return json.dumps({
            "region": region_data["name"],
            "hospitals": region_data.get("hospitals", []),
            "shelters": region_data.get("shelters", []),
            "evacuation_routes": region_data.get("evacuation_routes", []),
            "safe_zones": region_data.get("safe_zones", []),
        })

    if info_type == "hospitals":
        hospitals = region_data.get("hospitals", [])
        # Sort: trauma centers first
        trauma = [h for h in hospitals if h.get("trauma")]
        non_trauma = [h for h in hospitals if not h.get("trauma")]
        return json.dumps({
            "region": region_data["name"],
            "hospitals": trauma + non_trauma,
            "tip": "Trauma centers listed first.",
        })

    if info_type == "shelters":
        return json.dumps({
            "region": region_data["name"],
            "shelters": region_data.get("shelters", []),
        })

    if info_type == "evacuation_routes":
        return json.dumps({
            "region": region_data["name"],
            "evacuation_routes": region_data.get("evacuation_routes", []),
            "general_tips": KB.get("general_safety_tips", {}).get("evacuation", []),
        })

    if info_type == "safe_zones":
        return json.dumps({
            "region": region_data["name"],
            "safe_zones": region_data.get("safe_zones", []),
        })

    return json.dumps({"error": f"Unknown info_type: {info_type}"})


# ── Tool 3: Threat classifier ─────────────────────────────────────────────────

# Keyword-based fast pre-classifier
_CRITICAL_KEYWORDS = [
    "airstrike", "bombing", "explosion", "missile", "shelling", "attack",
    "غارة", "قصف", "انفجار", "هجوم",
]
_DANGER_KEYWORDS = [
    "clashes", "gunfire", "shooting", "riot", "unrest", "fire outbreak",
    "اشتباكات", "إطلاق نار", "شغب",
]
_CAUTION_KEYWORDS = [
    "tension", "protest", "demonstration", "road blocked", "checkpoint",
    "توترات", "احتجاج", "تظاهر", "طريق مقطوع",
]
_MONITOR_KEYWORDS = [
    "security alert", "warning", "advisory", "monitoring",
    "تحذير", "تنبيه",
]


def classify_threat(region: str, news_context: str) -> str:
    """
    Classify threat level 1-5 for a region given news context.
    Uses keyword pre-scan + LLM scoring for accuracy.
    """
    classifications = KB.get("threat_classifications", {})
    text_lower = news_context.lower()

    # Fast keyword pre-scan
    if any(kw in text_lower for kw in _CRITICAL_KEYWORDS):
        fast_level = 5
    elif any(kw in text_lower for kw in _DANGER_KEYWORDS):
        fast_level = 4
    elif any(kw in text_lower for kw in _CAUTION_KEYWORDS):
        fast_level = 3
    elif any(kw in text_lower for kw in _MONITOR_KEYWORDS):
        fast_level = 2
    else:
        fast_level = 1

    # LLM refinement for levels 3+
    if fast_level >= 3:
        try:
            prompt = f"""You are a Lebanon security analyst. Based on this news context, classify the threat level for {region}.

News context:
{news_context[:1000]}

Respond with ONLY a JSON object:
{{
  "level": <1-5 integer>,
  "reasoning": "<one sentence>",
  "immediate_actions": ["<action1>", "<action2>", "<action3>"]
}}

Levels:
1=safe, 2=monitor (stay alert), 3=caution (avoid travel), 4=danger (incident active), 5=critical (evacuate)"""

            response = _get_client().chat.completions.create(
                model=_groq_model(),
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.choices[0].message.content or ""

            json_match = re.search(r'\{.*\}', text.strip(), re.DOTALL)
            if json_match:
                llm_result = json.loads(json_match.group(0))
                level = int(llm_result.get("level", fast_level))
                level_key = {1: "safe", 2: "monitor", 3: "caution", 4: "danger", 5: "critical"}.get(level, "caution")
                classification = classifications.get(level_key, {})
                return json.dumps({
                    "region": region,
                    "level": level,
                    "color": classification.get("color", "orange"),
                    "description": classification.get("description", ""),
                    "reasoning": llm_result.get("reasoning", ""),
                    "immediate_actions": llm_result.get("immediate_actions", []),
                    "source": "llm_classified",
                })
        except Exception:
            pass  # Fall through to keyword result

    # Return keyword-based result
    level_key = {1: "safe", 2: "monitor", 3: "caution", 4: "danger", 5: "critical"}.get(fast_level, "safe")
    classification = classifications.get(level_key, {})
    return json.dumps({
        "region": region,
        "level": fast_level,
        "color": classification.get("color", "green"),
        "description": classification.get("description", ""),
        "reasoning": "Keyword-based classification.",
        "immediate_actions": [],
        "source": "keyword_classified",
    })


# ── Tool 4: Emergency contacts ───────────────────────────────────────────────

def get_emergency_contacts(service_type: str = "all") -> str:
    """Return emergency contacts and NGOs filtered by service type."""
    emergency = KB.get("emergency_contacts", {})
    ngos = KB.get("ngos_and_aid", [])

    service_map = {
        "medical": ["ambulance", "health"],
        "shelter": ["shelter"],
        "food": ["food"],
        "legal": ["legal_aid"],
        "refugee": ["refugee_support"],
    }

    if service_type == "all":
        filtered_ngos = ngos
    else:
        keywords = service_map.get(service_type, [])
        filtered_ngos = [
            ngo for ngo in ngos
            if any(kw in ngo.get("services", []) for kw in keywords)
        ]

    return json.dumps({
        "emergency_numbers": emergency,
        "ngos": filtered_ngos,
        "tip": "Call 125 (Civil Defense) or 140 (Red Cross) first in any emergency.",
    })
