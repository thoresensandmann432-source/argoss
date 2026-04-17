import re

SKILL_NAME = 'evolved_улучшение_форматиров'
SKILL_TRIGGERS = ['список', 'триггеров']

def handle(text: str, core=None):
    try:
        # Проверка триггеров
        if any(trigger in text.lower() for trigger in SKILL_TRIGGERS):
            # Унификация структуры ответа
            formatted_text = re.sub(r'\s+', ' ', text).strip()
            formatted_text = f'### {formatted_text}\n\n'
            return formatted_text
    except Exception as e:
        print(f"Error in {SKILL_NAME}: {e}")
    return None