import requests
from bs4 import BeautifulSoup
import json

def explore_swagger_docs():
    """Исследование Swagger документации"""
    base_url = "http://localhost:5051"
    
    try:
        # Получаем OpenAPI spec
        response = requests.get(f"{base_url}/openapi.json")
        if response.status_code == 200:
            spec = response.json()
            print("🎯 Найдены API endpoints из OpenAPI:")
            
            # Извлекаем paths
            if 'paths' in spec:
                for path, methods in spec['paths'].items():
                    print(f"  🔗 {path}: {list(methods.keys())}")
                    for method, details in methods.items():
                        if 'summary' in details:
                            print(f"     📝 {details['summary']}")
            return spec
        else:
            print(f"❌ OpenAPI spec недоступен: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Ошибка получения OpenAPI: {e}")
        return None

def test_api_endpoint(path, method="GET"):
    """Тестирование конкретного endpoint'а"""
    base_url = "http://localhost:5051"
    url = f"{base_url}{path}"
    
    try:
        if method.upper() == "POST":
            response = requests.post(url, json={"test": "message"})
        else:
            response = requests.get(url)
        
        print(f"📊 {method} {path}: {response.status_code}")
        if response.status_code == 200:
            try:
                print(f"   📦 {response.json()}")
            except:
                print(f"   📄 {response.text[:100]}")
        return response
    except Exception as e:
        print(f"❌ Ошибка {method} {path}: {e}")
        return None

def main():
    print("🔍 Исследование Argos API")
    print("=" * 30)
    
    # Исследуем Swagger документацию
    spec = explore_swagger_docs()
    
    if spec and 'paths' in spec:
        print("\n🧪 Тестирование найденных endpoints:")
        for path in list(spec['paths'].keys())[:5]:  # Тестируем первые 5
            test_api_endpoint(path)

if __name__ == "__main__":
    main()
