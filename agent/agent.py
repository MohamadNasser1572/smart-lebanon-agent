"""
Lebanon Emergency Intelligence Agent
Core orchestrator - routes user messages through tools and Groq.
"""

import json
import os
import re
from typing import Optional
from groq import Groq
from .tools import (
    web_search_news,
    kb_lookup,
    classify_threat,
    get_emergency_contacts,
)

_client: Groq | None = None

def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client

SYSTEM_PROMPT = """You are LEIA — Lebanon Emergency Intelligence Agent.
You help people in Lebanon stay safe during crises: conflicts, natural disasters, civil unrest, accidents.

Your job:
1. Understand what situation the user is facing and where they are in Lebanon
2. Search for live news/alerts relevant to their location
3. Classify the current threat level (1=safe to 5=critical)
4. Give them clear, actionable guidance: what to do RIGHT NOW
5. Provide nearest shelters, hospitals, emergency contacts

Tone rules:
- Be calm, clear, and direct. No panic, no fluff.
- Lead with the most important action first.
- Use numbered steps when giving instructions.
- Keep responses under 200 words unless the situation demands more detail.
- Always end with a relevant emergency number.
- If you don't have confirmed info about a specific incident, say so honestly.

Language: Respond in the same language the user writes in (Arabic or English).

You have access to these tools:
- web_search_news: search for live Lebanon news and alerts
- kb_lookup: get shelters, hospitals, evacuation routes for a region
- classify_threat: score current threat level based on retrieved news
- get_emergency_contacts: get NGO and emergency numbers

Always use kb_lookup + web_search_news together before responding to any location-based query."""

TOOLS = [
    {
        "name": "web_search_news",
        "description": "Search for real-time Lebanon news, security alerts, incidents, and civil defense announcements. Use this to get current situational awareness for any region.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. 'Lebanon Beirut security incident today' or 'south Lebanon alert tonight'"
                },
                "region": {
                    "type": "string",
                    "description": "Optional region filter: beirut, mount_lebanon, north_lebanon, south_lebanon, bekaa",
                    "enum": ["beirut", "mount_lebanon", "north_lebanon", "south_lebanon", "bekaa", "all"]
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "kb_lookup",
        "description": "Look up the Lebanon knowledge base for shelters, hospitals, evacuation routes, and safe zones in a specific region.",
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "Region to look up",
                    "enum": ["beirut", "mount_lebanon", "north_lebanon", "south_lebanon", "bekaa"]
                },
                "info_type": {
                    "type": "string",
                    "description": "What information to retrieve",
                    "enum": ["shelters", "hospitals", "evacuation_routes", "safe_zones", "all"]
                }
            },
            "required": ["region", "info_type"]
        }
    },
    {
        "name": "classify_threat",
        "description": "Classify the current threat level for a region based on retrieved news headlines. Returns level 1-5 with color and recommended action.",
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "Region being assessed"
                },
                "news_context": {
                    "type": "string",
                    "description": "The news text / headlines retrieved from web_search_news to analyze"
                }
            },
            "required": ["region", "news_context"]
        }
    },
    {
        "name": "get_emergency_contacts",
        "description": "Get relevant emergency contacts and NGOs. Can filter by service type needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service_type": {
                    "type": "string",
                    "description": "Type of service needed",
                    "enum": ["medical", "shelter", "food", "legal", "refugee", "all"]
                }
            },
            "required": ["service_type"]
        }
    }
]

GROQ_TOOLS = [{"type": "function", "function": {
    "name": tool["name"],
    "description": tool["description"],
    "parameters": tool["input_schema"],
}} for tool in TOOLS]


def run_tool(tool_name: str, tool_input: dict) -> str:
    """Dispatch tool calls to their implementations."""
    if tool_name == "web_search_news":
        return web_search_news(tool_input["query"], tool_input.get("region", "all"))
    elif tool_name == "kb_lookup":
        return kb_lookup(tool_input["region"], tool_input["info_type"])
    elif tool_name == "classify_threat":
        return classify_threat(tool_input["region"], tool_input["news_context"])
    elif tool_name == "get_emergency_contacts":
        return get_emergency_contacts(tool_input["service_type"])
    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})


def chat(messages: list[dict], max_tool_rounds: int = 5) -> dict:
    """
    Main agentic loop.
    Sends messages to Groq, handles tool calls, returns final response.

    Args:
        messages: Conversation history in OpenAI-compatible format
        max_tool_rounds: Safety limit on tool call iterations

    Returns:
        dict with keys: response (str), threat_level (int|None), tool_calls_made (list)
    """
    tool_calls_made = []
    current_messages = messages.copy()

    for round_num in range(max_tool_rounds):
        response = _get_client().chat.completions.create(
            model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            max_tokens=1024,
            tools=GROQ_TOOLS,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + current_messages,
        )

        message = response.choices[0].message

        # If Groq is done (no more tool calls), return the final text.
        if not message.tool_calls:
            threat_level = _extract_threat_level(tool_calls_made)
            return {
                "response": message.content or "",
                "threat_level": threat_level,
                "tool_calls_made": tool_calls_made,
            }

        # Add the assistant tool-call message in OpenAI-compatible format.
        current_messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in message.tool_calls
            ],
        })

        for call in message.tool_calls:
            tool_input = json.loads(call.function.arguments)
            result = run_tool(call.function.name, tool_input)
            tool_calls_made.append({
                "name": call.function.name,
                "input": tool_input,
                "result": result,
            })
            current_messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })

    # Fallback if we hit max rounds
    return {
        "response": "I'm having trouble retrieving complete information right now. Please call the Civil Defense directly at 125 or Red Cross at 140.",
        "threat_level": None,
        "tool_calls_made": tool_calls_made,
    }


def _extract_threat_level(tool_calls: list) -> Optional[int]:
    """Pull the last threat classification level from tool call results."""
    for call in reversed(tool_calls):
        if call["name"] == "classify_threat":
            try:
                result = json.loads(call.get("result", "{}"))
                return result.get("level")
            except Exception:
                pass
    return None


def create_user_message(text: str) -> dict:
    return {"role": "user", "content": text}


def create_assistant_message(text: str) -> dict:
    return {"role": "assistant", "content": text}
