from flask import Flask, request, jsonify
from datetime import datetime
import os

app = Flask(__name__)

# Храним состояние сервера
server_state = {
    "started": datetime.now().isoformat(),
    "requests_count": 0
}

@app.route('/')
def home():
    return jsonify({
        "message": "Argos Core Server",
        "status": "running",
        "version": "1.0.0"
    })

@app.route('/api/status')
def status():
    global server_state
    server_state["requests_count"] += 1
    return jsonify({
        "status": "ok",
        "service": "argos",
        "uptime": server_state["started"],
        "requests_processed": server_state["requests_count"]
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    global server_state
    server_state["requests_count"] += 1
    
    data = request.get_json()
    message = data.get('message', '')
    
    # Простая эмуляция ответа
    response_text = f"Argos получил сообщение: '{message}'. Время: {datetime.now().strftime('%H:%M:%S')}"
    
    return jsonify({
        "response": response_text,
        "status": "success"
    })

@app.route('/api/kimi/chat', methods=['POST'])
def kimi_chat():
    global server_state
    server_state["requests_count"] += 1
    
    data = request.get_json()
    message = data.get('message', '')
    
    response_text = f"Kimi AI обработал запрос: '{message}'"
    
    return jsonify({
        "response": response_text,
        "model": "kimi-ai-large",
        "status": "success"
    })

if __name__ == '__main__':
    print("🚀 Запуск Argos Complete Server на http://localhost:5000")
    print("🔧 Endpoints:")
    print("   GET  /api/status")
    print("   POST /api/chat")
    print("   POST /api/kimi/chat")
    app.run(host='0.0.0.0', port=5000, debug=True)
