"""AI Agent — основной модуль общения с пользователем."""

from openai import OpenAI

from config.settings import OPENAI_API_KEY, OPENAI_MODEL
from config.prompts import get_system_prompt


class Agent:
    """AI агент для общения с пользователями."""
    
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = OPENAI_MODEL
    
    def generate_response(
        self,
        message: str,
        intent: str,
        history: list[dict] = None,
        rag_context: str = None,
        lead_data: dict = None
    ) -> str:
        """
        Сгенерировать ответ на сообщение пользователя.
        
        Args:
            message: Сообщение пользователя
            intent: Намерение (birthday, general, unknown)
            history: История сообщений
            rag_context: Контекст из базы знаний (RAG)
            lead_data: Уже собранные данные лида
        
        Returns:
            Ответ бота
        """
        # Формируем системный промпт
        system_prompt = get_system_prompt(intent)
        
        # Добавляем контекст из базы знаний
        if rag_context:
            system_prompt += f"\n\n--- ИНФОРМАЦИЯ ИЗ БАЗЫ ЗНАНИЙ ---\n{rag_context}\n---"
        
        # Добавляем контекст собранного лида (для birthday ветки)
        if intent == "birthday" and lead_data:
            collected = []
            missing = []
            
            # Проверяем заполненные поля (в порядке сбора)
            if lead_data.get("event_date"):
                collected.append(f"- Дата праздника: {lead_data['event_date']}")
            else:
                missing.append("Дата праздника")
            
            if lead_data.get("kids_count"):
                collected.append(f"- Детей: {lead_data['kids_count']}")
            else:
                missing.append("Количество детей")
            
            if lead_data.get("time"):
                collected.append(f"- Время: {lead_data['time']}")
            else:
                missing.append("Время начала (10:30, 14:30 или 18:30)")
            
            if lead_data.get("room"):
                collected.append(f"- Комната: {lead_data['room']}")
            
            if lead_data.get("customer_name"):
                collected.append(f"- Имя для связи: {lead_data['customer_name']}")
            else:
                missing.append("Имя для связи")
            
            if lead_data.get("phone"):
                collected.append(f"- Телефон: {lead_data['phone']}")
            else:
                missing.append("Номер телефона")
            
            # Опционально
            if lead_data.get("child_name"):
                collected.append(f"- Именинник: {lead_data['child_name']}")
            if lead_data.get("child_age"):
                collected.append(f"- Возраст: {lead_data['child_age']}")
            
            if collected:
                system_prompt += f"\n\n--- УЖЕ СОБРАННЫЕ ДАННЫЕ ---\n" + "\n".join(collected)
            
            if missing:
                # Указываем СЛЕДУЮЩИЙ КОНКРЕТНЫЙ вопрос
                next_question = missing[0]
                system_prompt += f"\n\n🔴 СЛЕДУЮЩИЙ ВОПРОС, КОТОРЫЙ ТЫ ОБЯЗАН ЗАДАТЬ:\n→ {next_question}\n"
                system_prompt += f"\nЕЩЁ НУЖНО УЗНАТЬ: {', '.join(missing[1:]) if len(missing) > 1 else 'ничего'}"
                system_prompt += "\n\nНЕ ОТВЛЕКАЙСЯ на акции и каталоги пока не соберёшь ВСЕ данные!"
            else:
                system_prompt += "\n\n✅ ВСЕ ДАННЫЕ СОБРАНЫ! Теперь сделай Саммари и подтверди передачу заявки."
        
        # Формируем сообщения
        messages = [{"role": "system", "content": system_prompt}]
        
        # Добавляем историю (последние 10 сообщений)
        if history:
            for msg in history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Добавляем текущее сообщение
        messages.append({"role": "user", "content": message})
        
        # Генерируем ответ
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        text = response.choices[0].message.content
        
        # Убираем markdown форматирование для Telegram
        text = self._clean_markdown(text)
        
        return text
    
    def _clean_markdown(self, text: str) -> str:
        """Убираем markdown форматирование, которое не работает в Telegram."""
        import re
        
        # Убираем жирный текст **text** и __text__
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        
        # Убираем курсив *text* и _text_ (осторожно, не ломаем смайлики)
        text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', text)
        
        # Убираем `code`
        text = re.sub(r'`([^`]+)`', r'\1', text)
        
        # Убираем [text](url) -> text: url
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1: \2', text)
        
        return text
    
    def extract_lead_data(self, message: str, current_data: dict = None) -> dict:
        """
        Извлечь данные лида из сообщения пользователя.
        
        Returns:
            Обновлённые данные лида
        """
        if current_data is None:
            current_data = {}
        
        prompt = f"""Извлеки информацию о бронировании праздника из сообщения.

Сообщение: "{message}"

Уже известные данные:
{current_data}

Извлеки ТОЛЬКО то, что ЯВНО указано в сообщении. Верни JSON:
{{
    "customer_name": "имя родителя/заказчика или null",
    "child_name": "имя ребёнка-именинника или null",
    "child_age": число (возраст) или null,
    "event_date": "дата праздника (число месяц) или null",
    "time": "время начала (например 10:30, 14:30, 18:30) или null",
    "kids_count": число детей или null,
    "adults_count": число взрослых или null,
    "phone": "номер телефона или null",
    "room": "название комнаты (Опушка, Поляна Чудес и т.д.) или null",
    "format": "room/restaurant или null",
    "extras": ["аниматор", "торт", "шары"...] или []
}}

ВАЖНО: 
- Не выдумывай данные! Если в сообщении нет информации — ставь null.
- Если написано "10.30" или "10:30" — это время, запиши в time.
- Если написано "11 февраля" или "2 марта" — это дата, запиши в event_date.
- Если написано "7 детей" или "детей 7" — запиши kids_count: 7.
- Если написано "опушка" — запиши room: "Опушка".
Ответь ТОЛЬКО JSON, без пояснений."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0
            )
            
            import json
            result = response.choices[0].message.content.strip()
            # Убираем markdown если есть
            if result.startswith("```"):
                result = result.split("```")[1]
                if result.startswith("json"):
                    result = result[4:]
            
            extracted = json.loads(result)
            
            # Мержим с текущими данными (новые перезаписывают)
            for key, value in extracted.items():
                if value is not None and value != [] and value != "":
                    current_data[key] = value
            
            return current_data
            
        except Exception as e:
            print(f"Lead extraction error: {e}")
            return current_data


# Глобальный экземпляр агента
agent = Agent()
