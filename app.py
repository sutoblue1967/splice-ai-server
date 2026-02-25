import os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ✅ version stamp so we can verify deploy instantly
EL_VERSION = "El-v2-personality"

@app.get("/")
def home():
    return f"OK ({EL_VERSION})", 200

@app.get("/health")
def health():
    return jsonify({"ok": True, "version": EL_VERSION}), 200

def handle_chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()

    if not msg:
        return jsonify({"message": "Message is required", "version": EL_VERSION}), 400

    user_msg = msg.lower()

    intro = (
        "Hi, I’m El — your insider for everything happening around the MOV. "
        "Tell me what kind of vibe you're looking for and I’ll point you to what’s going on."
    )

    if any(word in user_msg for word in ["hi", "hello", "hey"]):
        reply = intro
    elif "weekend" in user_msg:
        reply = "Looking for something this weekend? Music, family fun, nightlife, or something chill?"
    elif "music" in user_msg:
        reply = "Live music is always happening around the MOV. Want something laid-back, high-energy, or all-ages?"
    elif "kids" in user_msg or "family" in user_msg:
        reply = "Got it — family vibe. I’ll start pulling together the best kid-friendly and family events around the MOV."
    elif "date" in user_msg:
        reply = "Nice 😏 Looking for classy, casual, outdoors, or something unique for date night?"
    else:
        reply = (
            "Tell me what you're in the mood for — live music, food, family fun, nightlife, "
            "art, or something totally different — and I’ll guide you."
        )

    return jsonify({"message": reply, "version": EL_VERSION}), 200

@app.post("/chat")
def chat():
    return handle_chat()

@app.post("/el-chat/chat")
def el_chat_chat():
    return handle_chat()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
