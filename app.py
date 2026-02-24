import os
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.post("/el-chat/chat")
def chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()
    if not msg:
        return jsonify({"message": "Please type a message."}), 400

    # TEMP: proves wiring works
    return jsonify({"message": f"✅ eL is connected. You said: {msg}"}), 200

@app.get("/health")
def health():
    return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
