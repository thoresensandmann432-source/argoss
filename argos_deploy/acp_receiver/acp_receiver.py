from flask import Flask, request, jsonify
import os

app = Flask(__name__)

@app.route('/write', methods=['POST'])
def handle_write():
    data = request.json
    path = data.get('path')
    content = data.get('content')
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({"status": "ok", "file": path}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) # Откройте порт 5000 в фаерволе

