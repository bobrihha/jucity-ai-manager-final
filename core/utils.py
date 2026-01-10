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
