import requests
import socket
import subprocess
import sys
import time

def check_port_connectivity(host='127.0.0.1', port=5051, timeout=5):
    """Проверка доступности порта"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

def test_http_endpoints(base_url):
    """Тест различных HTTP endpoints"""
    endpoints = [
        "/", "/api", "/api/v1", "/health", "/status", 
        "/openapi.json", "/docs", "/redoc", "/api/status",
        "/api/chat", "/chat", "/message"
    ]
    
    results = {}
    for endpoint in endpoints:
        try:
            url = f"{base_url}{endpoint}"
            response = requests.get(url, timeout=3)
            results[endpoint] = {
                'status_code': response.status_code,
                'content_type': response.headers.get('content-type', 'unknown'),
                'content_length': len(response.content)
            }
        except Exception as e:
            results[endpoint] = {'error': str(e)}
    
    return results

def main():
    print("🔍 Диагностика Argos сервера")
    print("=" * 40)
    
    # Проверка доступности порта
    print("Проверка порта 5051...")
    if check_port_connectivity():
        print("✅ Порт 5051 открыт и доступен")
    else:
        print("❌ Порт 5051 недоступен")
        return
    
    # Тест HTTP endpoints
    print("\nТестирование HTTP endpoints...")
    base_url = "http://localhost:5051"
    results = test_http_endpoints(base_url)
    
    for endpoint, result in results.items():
        if 'error' in result:
            print(f"❌ {endpoint}: {result['error']}")
        else:
            status = "✅" if result['status_code'] == 200 else "⚠️"
            print(f"{status} {endpoint}: {result['status_code']} "
                  f"(тип: {result['content_type'][:30]}, размер: {result['content_length']} байт)")

if __name__ == "__main__":
    main()

