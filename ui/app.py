"""
LEIA — Lebanon Emergency Intelligence Agent
Web dashboard (Gradio 6+)

Run from project root:
    python ui/app.py
Then open the printed local URL (default http://127.0.0.1:7860)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gradio as gr
from agent.agent import chat, create_user_message, create_assistant_message

THREAT_INFO = {
    1: ("#22c55e", "🟢 Level 1 — Safe"),
    2: ("#eab308", "🟡 Level 2 — Monitor"),
    3: ("#f97316", "🟠 Level 3 — Caution"),
    4: ("#ef4444", "🔴 Level 4 — Danger"),
    5: ("#dc2626", "🆘 Level 5 — CRITICAL"),
}

CSS = """
#chatbot { height: 480px; }
footer { display: none !important; }
.threat-box { border-radius: 10px; padding: 14px 18px; font-weight: 600; font-size: 16px; text-align: center; transition: all 0.3s ease; }
"""

EXAMPLE_QUERIES = [
    "I'm in Beirut Hamra, what's the current situation?",
    "Heard explosions near Dahieh, what should I do?",
    "I'm in south Lebanon near Tyre, is it safe to travel north?",
    "Where is the nearest shelter in Bekaa Valley?",
    "I need emergency medical help in Tripoli",
    "ما هو الوضع الأمني في بيروت الآن؟",
    "أين أقرب مستشفى في الجنوب؟",
]


def format_threat(level):
    if level is None:
        return "<div class='threat-box' style='background:#f3f4f620;border:2px solid #9ca3af;color:#6b7280'>⬜ No threat assessment yet</div>"
    color, label = THREAT_INFO.get(level, ("#6b7280", f"Level {level}"))
    return f"<div class='threat-box' style='background:{color}20;border:2px solid {color};color:{color}'>{label}</div>"


def respond(message, history, session_state):
    if not message or not message.strip():
        return history, session_state, gr.update()

    msg_history = session_state.get("messages", [])
    msg_history.append(create_user_message(message))
    if len(msg_history) > 20:
        msg_history = msg_history[-20:]

    result = chat(msg_history)
    reply = result["response"]
    threat = result["threat_level"]

    msg_history.append(create_assistant_message(reply))
    session_state["messages"] = msg_history

    history = history + [{"role": "user", "content": message},
                          {"role": "assistant", "content": reply}]

    return history, session_state, format_threat(threat)


def clear_session():
    return [], {"messages": []}, format_threat(None)


with gr.Blocks(title="LEIA — Lebanon Emergency Agent") as demo:
    session_state = gr.State({"messages": []})

    with gr.Row():
        with gr.Column(scale=3):
            gr.Markdown(
                "# 🇱🇧 LEIA — Lebanon Emergency Intelligence Agent\n"
                "**Real-time situational awareness and crisis guidance for Lebanon**\n\n"
                "Ask about current security situation, find shelters, hospitals, or evacuation routes. "
                "Works in English or Arabic."
            )
        with gr.Column(scale=1):
            threat_display = gr.HTML(format_threat(None))

    with gr.Row():
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(elem_id="chatbot", label="")
            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="Type your location and situation... (English or Arabic)",
                    label="", scale=5, container=False,
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)
                clear_btn = gr.Button("Clear", variant="secondary", scale=1)

        with gr.Column(scale=1):
            gr.Markdown("### Quick examples")
            for example in EXAMPLE_QUERIES:
                gr.Button(example, size="sm").click(
                    fn=lambda e=example: e, outputs=[msg_input]
                )

            gr.Markdown(
                "### Emergency numbers\n"
                "| Service | Number |\n"
                "|---------|--------|\n"
                "| Civil Defense | **125** |\n"
                "| Red Cross | **140** |\n"
                "| Ambulance | **140** |\n"
                "| Police | **112** |\n"
                "| Fire | **175** |\n"
                "| ISF | **1717** |"
            )

    send_btn.click(
        fn=respond, inputs=[msg_input, chatbot, session_state],
        outputs=[chatbot, session_state, threat_display],
    ).then(lambda: "", outputs=[msg_input])

    msg_input.submit(
        fn=respond, inputs=[msg_input, chatbot, session_state],
        outputs=[chatbot, session_state, threat_display],
    ).then(lambda: "", outputs=[msg_input])

    clear_btn.click(
        fn=clear_session, outputs=[chatbot, session_state, threat_display],
    )

    gr.Markdown(
        "---\n"
        "*LEIA uses live news search and a curated Lebanon knowledge base. Always verify with official sources. "
        "In life-threatening emergencies call Civil Defense: **125***"
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, css=CSS)
