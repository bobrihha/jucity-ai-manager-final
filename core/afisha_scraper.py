"""Парсер афиши с сайта jucity.ru"""

import requests
from bs4 import BeautifulSoup
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

AFISHA_URL = "https://nn.jucity.ru/afisha/"

def scrape_afisha() -> str:
    """Парсит афишу с сайта и возвращает текст событий."""
    try:
        response = requests.get(AFISHA_URL, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        events = soup.select('.events__item')
        
        if not events:
            return "Афиша: на данный момент нет запланированных событий."
        
        result_lines = ["АФИША ДЖУНГЛИ СИТИ (Нижний Новгород)\n"]
        result_lines.append(f"Актуально на момент последнего обновления\n")
        result_lines.append("-" * 40 + "\n")
        
        for event in events:
            # Название события
            title_el = event.select_one('.events__item-title a')
            title = title_el.get_text(strip=True) if title_el else "Без названия"
            
            # Дата и время
            info_rows = event.select('.events__item-info-row')
            date = ""
            time = ""
            
            for row in info_rows:
                text = row.get_text(strip=True)
                # Определяем по формату: дата содержит точки, время - двоеточие
                if '.' in text and len(text) <= 10:
                    date = text
                elif ':' in text and len(text) <= 5:
                    time = text
            
            # Ссылка
            link_el = event.select_one('.events__item-link a')
            link = link_el.get('href', '') if link_el else ""
            
            # Формируем запись
            result_lines.append(f"📅 {date} в {time}")
            result_lines.append(f"🎪 {title}")
            if link:
                result_lines.append(f"Подробнее: {link}")
            result_lines.append("")
        
        result_lines.append("-" * 40)
        result_lines.append(f"Полное расписание: {AFISHA_URL}")
        
        return "\n".join(result_lines)
        
    except requests.RequestException as e:
        logger.error(f"Ошибка при парсинге афиши: {e}")
        return f"Не удалось загрузить афишу. Смотрите на сайте: {AFISHA_URL}"


def save_afisha_to_knowledge(park_id: str = "nn") -> str:
    """Сохраняет афишу в файл базы знаний."""
    content = scrape_afisha()
    
    # Путь к файлу афиши
    knowledge_dir = Path(__file__).parent.parent / "knowledge" / park_id / "events"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    
    afisha_file = knowledge_dir / "afisha.txt"
    afisha_file.write_text(content, encoding="utf-8")
    
    logger.info(f"Афиша сохранена: {afisha_file}")
    return content


if __name__ == "__main__":
    # Тест
    print(scrape_afisha())
