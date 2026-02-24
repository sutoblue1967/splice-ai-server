import os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.get("/")
def home():
    return "OK", 200

@app.get("/health")
def health():
    return jsonify({"ok": True}), 200

def handle_chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()

    if not msg:
        return jsonify({"message": "Message is required"}), 400

    # ✅ TEMP reply (swap with real AI later)
    return jsonify({"message": f"✅ eL is connected. You said: {msg}"}), 200

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
