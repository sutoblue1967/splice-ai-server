import os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

EL_VERSION = "el-v3-welcome"

@app.get("/")
def home():
    return "OK", 200

@app.get("/health")
def health():
    return jsonify({"ok": True, "version": EL_VERSION}), 200

def build_welcome_message():
    # Placeholder sections (we’ll wire real events next)
    return (
        "Hi, I’m El — your insider for everything happening around the MOV.\n\n"
        "✨ **Today’s Highlights**\n"
        "• (coming next: pulled from your events feed)\n\n"
        "📅 **This Weekend**\n"
        "• (coming next: top weekend picks)\n\n"
        "🔥 **Trending Right Now**\n"
        "• (coming next: what people are clicking + popular categories)\n\n"
        "Tell me what kind of vibe you’re looking for — music, family fun, nightlife, chill, food, sports — and I’ll point you to what’s going on."
    )

def handle_chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()

    if not msg:
        return jsonify({"message": "Message is required"}), 400

    # ✅ Special auto-welcome trigger
    if msg == "__WELCOME__":
        return jsonify({"message": build_welcome_message()}), 200

    user_msg = msg.lower()

    # Simple starter logic (we’ll replace with real event search)
    if any(word in user_msg for word in ["hi", "hello", "hey"]):
        return jsonify({"message": build_welcome_message()}), 200

    return jsonify({"message": f"✅ El is connected. You said: {msg}"}), 200

# ✅ Accept BOTH URLs so WP never 404s
@app.post("/chat")
def chat():
    return handle_chat()

@app.post("/el-chat/chat")
def el_chat_chat():
    return handle_chat()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
