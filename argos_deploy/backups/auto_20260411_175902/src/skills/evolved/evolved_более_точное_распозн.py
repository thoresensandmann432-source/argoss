import spacy
from spacy.lang.en import English
from typing import Optional

SKILL_NAME = 'evolved_более_точное_распознавание'
SKILL_TRIGGERS = ['список', 'триггеров']

nlp = English()

def handle(text: str, core=None) -> Optional[str]:
    try:
        doc = nlp(text)
        entities = [(ent.text, ent.label_) for ent in doc.ents]
        
        if any(trigger in text.lower() for trigger in SKILL_TRIGGERS):
            return f"Запрос триггеров: {entities}"
    
    except Exception as e:
        print(f"Ошибка обработки текста: {e}")
    
    return None