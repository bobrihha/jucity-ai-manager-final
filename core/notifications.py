"""Модуль уведомлений менеджеров."""
import os
import aiohttp
import logging
from datetime import datetime

from core.utils import format_phone

logger = logging.getLogger(__name__)

async def send_to_managers(text: str):
    """Отправить сообщение в чат менеджеров."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("MANAGER_CHAT_ID")
    
    if not token or not chat_id:
        logger.warning("Notification failed: TELEGRAM_BOT_TOKEN or MANAGER_CHAT_ID not set")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    resp_text = await response.text()
                    logger.error(f"Failed to send manager notification: {resp_text}")
                else:
                    logger.info("Manager notification sent successfully")
    except Exception as e:
        logger.error(f"Error sending notification: {e}")

def format_lead_message(platform: str, user_id: str, lead_data: dict, username: str = None) -> str:
    """Форматирование заявки для менеджеров."""
    
    source = "ВКонтакте" if platform == "vk" else "Telegram"
    
    # Формируем ссылку на профиль
    if platform == "vk":
        user_link = f"https://vk.com/id{user_id.replace('vk_', '')}"
        contact_info = f"<a href='{user_link}'>Открыть профиль</a>"
    else:
        # Telegram: предпочтительно username; без username нет https-ссылки
        if username:
            user_link = f"https://t.me/{username}"
            contact_info = f"@{username} (<a href='{user_link}'>открыть</a>)"
        else:
            contact_info = f"ID {user_id} (нет ссылки без username)"
    
    # Форматируем именинника
    child_info = lead_data.get('child_name', 'Не указан')
    if lead_data.get('child_age'):
        child_info += f", {lead_data.get('child_age')} лет"
        
    raw_phone = lead_data.get('phone')
    phone_text = format_phone(raw_phone) or (raw_phone if raw_phone else "🔥 НЕ УКАЗАН 🔥")
    
    # Форматируем extras (дополнительные услуги)
    extras = lead_data.get('extras', [])
    if isinstance(extras, str):
        import json
        try:
            extras = json.loads(extras)
        except:
            extras = [extras] if extras else []
    extras_text = ", ".join(extras) if extras else "—"

    msg = (
        f"🔥 <b>НОВАЯ ЗАЯВКА ({source})</b>\n\n"
        f"🎂 <b>Именинник:</b> {child_info}\n"
        f"📅 <b>Дата:</b> {lead_data.get('event_date', 'Не указана')}\n"
        f"⏰ <b>Время:</b> {lead_data.get('time', 'Не указано')}\n"
        f"👥 <b>Гостей:</b> {lead_data.get('kids_count', '?')} дет. + {lead_data.get('adults_count', '?')} взр.\n"
        f"🏠 <b>Формат:</b> {lead_data.get('format', 'Не указан')}\n"
        f"👤 <b>Заказчик:</b> {lead_data.get('customer_name', 'Не указан')}\n"
        f"📱 <b>Телефон:</b> {phone_text}\n"
        f"✨ <b>Доп. услуги:</b> {extras_text}\n\n"
        f"🔗 <b>Профиль:</b> {contact_info}\n"
        f"🕒 <i>Создано: {datetime.now().strftime('%d.%m.%Y %H:%M')}</i>"
    )
    return msg


def format_escalation_message(platform: str, user_id: str, username: str, user_name: str, message: str) -> str:
    """Форматирование уведомления о запросе живого менеджера."""
    
    source = "ВКонтакте" if platform == "vk" else "Telegram"
    
    if platform == "vk":
        user_link = f"https://vk.com/id{user_id.replace('vk_', '')}"
        contact_info = f"<a href='{user_link}'>Открыть профиль VK</a>"
    else:
        if username:
            user_link = f"https://t.me/{username}"
            contact_info = f"@{username} (<a href='{user_link}'>открыть чат</a>)"
        else:
            contact_info = f"ID {user_id} (нет ссылки без username)"
    
    msg = (
        f"🆘 <b>ЗАПРОС ЖИВОГО МЕНЕДЖЕРА ({source})</b>\n\n"
        f"👤 <b>Пользователь:</b> {user_name}\n"
        f"💬 <b>Сообщение:</b> {message[:200]}{'...' if len(message) > 200 else ''}\n\n"
        f"📞 <b>Контакт:</b> {contact_info}\n"
        f"🕒 <i>{datetime.now().strftime('%d.%m.%Y %H:%M')}</i>"
    )
    return msg


def needs_human_escalation(message: str) -> bool:
    """Проверить, просит ли пользователь живого человека."""
    message_lower = message.lower()
    
    escalation_keywords = [
        "живой человек", "живого человека", "живому человеку",
        "живой менеджер", "живого менеджера",
        "оператор", "оператора",
        "позвоните мне", "позвони мне", "перезвоните",
        "свяжитесь со мной", "свяжись со мной",
        "хочу поговорить с человеком",
        "можно менеджера", "дайте менеджера",
        "соедините с менеджером", "соединить с менеджером",
        "не бот", "не робот", "реальный человек",
        "срочно", "жалоба", "претензия", "недоволен",
    ]
    
    return any(kw in message_lower for kw in escalation_keywords)
