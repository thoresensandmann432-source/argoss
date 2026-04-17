import re
from typing import Optional

SKILL_NAME = "evolved_улучшение_качества_о"
SKILL_TRIGGERS = ["список", "триггеров"]

def handle(text: str, core=None) -> Optional[str]:
    if not any(trigger in text for trigger in SKILL_TRIGGERS):
        return None
    
    # Удаление лишних пробелов и табуляций
    cleaned_text = re.sub(r'\s+', ' ', text).strip()
    
    # Преобразование заглавных букв в нижний регистр
    formatted_text = cleaned_text.lower()
    
    # Форматирование чисел и дат
    formatted_text = re.sub(r'(\d{4})(-|/)(\d{2})\2(\d{2})', r'\1-\2\3', formatted_text)
    
    # Улучшение структуры предложений
    sentences = re.split(r'[.!?]', formatted_text)
    improved_sentences = []
    for sentence in sentences:
        words = sentence.strip().split()
        if len(words) > 5 and words[-1].lower() != 'и':
            words.append('и')
        improved_sentences.append(' '.join(words))
    
    return '.'.join(improved_sentences) + '.'