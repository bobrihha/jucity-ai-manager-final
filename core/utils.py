import re
from pathlib import Path

def get_prices_from_knowledge(park_id: str = "nn") -> dict:
    """
    Парсит файл prices.txt и возвращает словарь с ценами.
    Если не находит, возвращает дефолтные значения.
    """
    default_prices = {
        "monday": 990,
        "weekday": 1190,
        "weekend": 1590
    }
    
    try:
        # Путь к файлу цен
        root = Path(__file__).parent.parent
        file_path = root / "knowledge" / park_id / "general" / "prices.txt"
        
        if not file_path.exists():
            return default_prices
            
        content = file_path.read_text(encoding="utf-8")
        
        prices = default_prices.copy()
        
        # Понедельник
        monday_match = re.search(r"Понедельник[^:]*:.*?(\d+)\s*руб", content, re.IGNORECASE)
        if monday_match:
            prices["monday"] = int(monday_match.group(1))
            
        # Будни
        weekday_match = re.search(r"Будни[^:]*:.*?(\d+)\s*руб", content, re.IGNORECASE)
        if weekday_match:
            prices["weekday"] = int(weekday_match.group(1))
            
        # Выходные
        weekend_match = re.search(r"Выходные[^:]*:.*?(\d+)\s*руб", content, re.IGNORECASE)
        if weekend_match:
            prices["weekend"] = int(weekend_match.group(1))
            
        return prices
        
    except Exception as e:
        print(f"Error parsing prices: {e}")
        return default_prices

def get_prices_text(park_id: str = "nn") -> str:
    """Возвращает полное содержимое файла цен."""
    try:
        root = Path(__file__).parent.parent
        file_path = root / "knowledge" / park_id / "general" / "prices.txt"
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
    except:
        pass
    return ""


def format_phone(phone: str) -> str:
    """Форматировать телефон для отображения."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"+7 ({digits[0:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:10]}"
    return str(phone)


def get_afisha_events(park_id: str = "nn") -> str:
    """
    Парсит файл afisha.txt и возвращает красивый текст с событиями.
    """
    # Эмодзи для разных типов событий
    event_emoji = {
        "мастер-класс": "✨",
        "бармен": "🍹",
        "кулинар": "👨‍🍳",
        "розыгрыш": "🎁",
        "лото": "🎵",
        "именинник": "🎂",
        "дискотека": "💃",
        "шоу": "🌟",
    }
    
    try:
        root = Path(__file__).parent.parent
        file_path = root / "knowledge" / park_id / "events" / "afisha.txt"
        
        if not file_path.exists():
            return None
        
        content = file_path.read_text(encoding="utf-8")
        
        # Парсим события из файла
        # Формат: 📅 DD.MM.YYYY в HH:MM\n🎪 Название
        events = []
        lines = content.split("\n")
        
        current_date = None
        for line in lines:
            line = line.strip()
            
            # Ищем дату: 📅 13.01.2026 в 18:00
            date_match = re.search(r"📅\s*(\d{1,2})\.(\d{1,2})\.\d{4}\s*в\s*(\d{1,2}:\d{2})", line)
            if date_match:
                day = date_match.group(1)
                month = int(date_match.group(2))
                time = date_match.group(3)
                
                # Месяцы на русском
                months = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
                          "июля", "августа", "сентября", "октября", "ноября", "декабря"]
                month_name = months[month] if month <= 12 else str(month)
                
                current_date = f"{day} {month_name}, {time}"
                continue
            
            # Ищем название события: 🎪 Название
            event_match = re.search(r"🎪\s*(.+)", line)
            if event_match and current_date:
                event_name = event_match.group(1).strip()
                
                # Подбираем подходящий эмодзи
                emoji = "🎪"
                for keyword, em in event_emoji.items():
                    if keyword in event_name.lower():
                        emoji = em
                        break
                
                events.append(f"{emoji} {current_date} — {event_name}")
                current_date = None
        
        if not events:
            return None
        
        # Формируем красивый текст
        events_text = "\n".join(events)
        result = (
            f"🎪 Ближайшие события в Джунгли Сити!\n\n"
            f"{events_text}\n\n"
            f"Приходите — будет весело! 🎉\n\n"
            f"👉 Полная афиша: nn.jucity.ru/afisha/"
        )
        return result
        
    except Exception as e:
        print(f"Error parsing afisha: {e}")
        return None
