"""
Lebanon Emergency Intelligence Agent
Core orchestrator — routes user messages through tools and Claude API.
"""

import json
import os
import re
from typing import Optional
import anthropic
from .tools import (
    web_search_news,
    kb_lookup,
    classify_threat,
    get_emergency_contacts,
)

_client: "anthropic.Anthropic | None" = None

def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
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
    Sends messages to Claude, handles tool calls, returns final response.

    Args:
        messages: Conversation history in Anthropic format
        max_tool_rounds: Safety limit on tool call iterations

    Returns:
        dict with keys: response (str), threat_level (int|None), tool_calls_made (list)
    """
    tool_calls_made = []
    current_messages = messages.copy()

    for round_num in range(max_tool_rounds):
        response = _get_client().messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=current_messages,
        )

        # If Claude is done (no more tool calls), return the final text
        if response.stop_reason == "end_turn":
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text
            threat_level = _extract_threat_level(tool_calls_made)
            return {
                "response": final_text,
                "threat_level": threat_level,
                "tool_calls_made": tool_calls_made,
            }

        # Handle tool use
        if response.stop_reason == "tool_use":
            # Add Claude's response (with tool_use blocks) to history
            current_messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_calls_made.append({"name": block.name, "input": block.input})
                    result = run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            # Add tool results to history
            current_messages.append({"role": "user", "content": tool_results})

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
