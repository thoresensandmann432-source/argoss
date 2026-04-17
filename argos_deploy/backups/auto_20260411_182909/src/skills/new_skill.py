import requests
from bs4 import BeautifulSoup

SKILL_DESCRIPTION = "Шаблон для создания новых навыков ARGOS v2.1"


class ArgosSkillV210:
    """Навык для ИИ‑системы Аргос версии 2.1.0."""

    # Стандартный ARGOS-интерфейс: первый аргумент — core (ArgosCore объект),
    # второй (опциональный) — base_url строка
    def __init__(self, core_or_url=None, base_url: str = "https://example.com"):
        # Если передан ArgosCore — сохраняем его, берём base_url из env или дефолт
        if isinstance(core_or_url, str):
            base_url = core_or_url
            self.core = None
        else:
            self.core = core_or_url
        self.base_url = (base_url or "https://example.com").rstrip('/')
        self.session = requests.Session()

    def fetch_page(self, path):
        """
        Получить HTML‑страницу по относительному пути.

        :param path: Относительный путь к ресурсу
        :return: Текст HTML‑страницы
        :raises requests.HTTPError: При неуспешном запросе
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = self.session.get(url, timeout=10)
        response.raise_for_status()
        return response.text

    def parse_title(self, html):
        """
        Извлечь заголовок <title> из HTML‑кода.

        :param html: Строка HTML‑кода
        :return: Текст заголовка или None, если тег не найден
        """
        soup = BeautifulSoup(html, 'html.parser')
        title_tag = soup.find('title')
        return title_tag.get_text(strip=True) if title_tag else None

    def get_page_title(self, path):
        """
        Получить заголовок страницы по относительному пути.

        :param path: Относительный путь к странице
        :return: Текст заголовка или None
        """
        html = self.fetch_page(path)
        return self.parse_title(html)

    def search(self, query, params=None):
        """
        Выполнить поиск по запросу, используя параметр `q` в GET‑запросе.

        :param query: Строка поискового запроса
        :param params: Дополнительные параметры GET‑запроса (dict)
        :return: Список найденных заголовков страниц
        """
        if params is None:
            params = {}
        params.update({'q': query})
        response = self.session.get(self.base_url, params=params, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        for tag in soup.find_all('title'):
            title = tag.get_text(strip=True)
            if title:
                results.append(title)
        return results

    def close(self):
        """
        Закрыть HTTP‑сеанс, освобождая ресурсы.
        """
        self.session.close()