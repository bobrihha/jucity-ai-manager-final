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


def needs_booking_change_request(message: str) -> bool:
    """Проверить, просит ли пользователь изменить/отменить бронирование."""
    message_lower = message.lower()
    
    change_keywords = [
        # Перенос/изменение даты
        "перенести", "перенос", "сменить дату", "изменить дату",
        "другую дату", "другой день", "передвинуть",
        # Изменение времени
        "изменить время", "другое время", "сменить время",
        # Отмена
        "отменить", "отмена", "отказаться", "не приедем", "не придём", "не придем",
        "аннулировать", "возврат",
        # Изменение гостей
        "изменить количество", "больше гостей", "меньше гостей",
        "добавить детей", "убрать детей",
        # Изменение услуг
        "добавить аниматора", "убрать аниматора", "добавить торт",
        "изменить меню", "поменять комнату",
        # Общие
        "хочу изменить", "можно изменить", "нужно изменить",
        "хотел бы изменить", "хотела бы изменить",
        # Контекст бронирования
        "изменить бронь", "изменить бронирование",
        "поменять бронь", "поменять бронирование",
        "отменить бронь", "отменить бронирование",
        # Запросы с "время"/"дату" + "бронирования"
        "время бронирования", "дату бронирования",
    ]
    
    return any(kw in message_lower for kw in change_keywords)


def get_booking_change_type(message: str) -> str:
    """Определить тип изменения бронирования."""
    message_lower = message.lower()
    
    if any(kw in message_lower for kw in ["отменить", "отмена", "отказ", "аннулир", "возврат", "не приедем", "не придём", "не придем"]):
        return "Отмена бронирования"
    elif any(kw in message_lower for kw in ["перенести", "перенос", "дату", "день", "передвинуть"]):
        return "Изменить дату/время"
    elif any(kw in message_lower for kw in ["время"]):
        return "Изменить время"
    elif any(kw in message_lower for kw in ["гост", "детей", "количество"]):
        return "Изменить количество гостей"
    elif any(kw in message_lower for kw in ["аниматор", "торт", "меню", "комнат", "услуг"]):
        return "Изменить услуги"
    else:
        return "Изменение бронирования"


def format_booking_change_message(
    platform: str,
    user_id: str,
    user_name: str,
    change_type: str,
    message_text: str,
    deal_id: str = None,
    phone: str = None,
    username: str = None
) -> str:
    """Форматирование уведомления об изменении бронирования."""
    
    source = "ВКонтакте" if platform == "vk" else "Telegram"
    
    if platform == "vk":
        user_link = f"https://vk.com/id{user_id.replace('vk_', '')}"
        contact_info = f"<a href='{user_link}'>Открыть профиль VK</a>"
    else:
        if username:
            user_link = f"https://t.me/{username}"
            contact_info = f"@{username} (<a href='{user_link}'>открыть чат</a>)"
        else:
            contact_info = f"ID {user_id}"
    
    phone_text = format_phone(phone) or phone or "Не указан"
    deal_text = f"<b>Сделка:</b> #{deal_id}\n" if deal_id else ""
    
    msg = (
        f"⚠️ <b>ЗАПРОС НА ИЗМЕНЕНИЕ БРОНИ ({source})</b>\n\n"
        f"{deal_text}"
        f"📝 <b>Тип:</b> {change_type}\n"
        f"💬 <b>Сообщение:</b> {message_text[:200]}{'...' if len(message_text) > 200 else ''}\n\n"
        f"👤 <b>Клиент:</b> {user_name}\n"
        f"📱 <b>Телефон:</b> {phone_text}\n"
        f"🔗 <b>Профиль:</b> {contact_info}\n\n"
        f"🕒 <i>{datetime.now().strftime('%d.%m.%Y %H:%M')}</i>"
    )
    return msg


def needs_lost_item_flow(message: str) -> bool:
    """Проверить, сообщает ли пользователь о потерянной вещи."""
    message_lower = message.lower()
    
    # ИСКЛЮЧЕНИЯ: если есть контекст покупки/приобретения — это НЕ потеряшки
    buy_context = [
        "купить", "приобрести", "продаёте", "продаете", "продаётся", "продается",
        "можно ли купить", "у вас можно", "у вас есть",
        "где купить", "сколько стоит", "стоимость", "цена",
        "едем в парк", "идём в парк", "идем в парк", "собираемся в парк",
        "взять с собой", "нужно ли брать", "надо брать",
    ]
    if any(kw in message_lower for kw in buy_context):
        return False
    
    # Явные триггеры потери (всегда срабатывают)
    strong_lost_keywords = [
        "потерял", "потеряла", "потеряли",
        "пропало", "пропала", "пропали",
        "утерян", "утеряна", "утеряно",
        "бюро находок", "потерянные вещи",
        "потеряшка", "потеряшки",
        "не могу найти", "не нашёл", "не нашла",
    ]
    if any(kw in message_lower for kw in strong_lost_keywords):
        return True
    
    # Слабые триггеры (забыл/оставил) — требуют контекст потери
    weak_lost_keywords = [
        "забыл", "забыла", "забыли",
        "оставил", "оставила", "оставили",
    ]
    lost_context = [
        "в парке", "у вас", "в комнате", "на аттракционе", "в ресторане",
        "вчера", "сегодня", "неделю назад", "в выходные",
        "найти", "верните", "где мой", "где моя", "где мои",
        "вещь", "сумку", "телефон", "кошелёк", "кошелек", "куртку", "очки",
    ]
    
    if any(kw in message_lower for kw in weak_lost_keywords):
        # Проверяем контекст
        if any(ctx in message_lower for ctx in lost_context):
            return True
    
    return False


def format_lost_item_message(
    platform: str,
    user_id: str,
    user_name: str,
    lost_date: str,
    lost_location: str,
    lost_description: str,
    phone: str,
    username: str = None
) -> str:
    """Форматирование уведомления о потерянной вещи для менеджеров."""
    
    source = "ВКонтакте" if platform == "vk" else "Telegram"
    
    if platform == "vk":
        user_link = f"https://vk.com/id{user_id.replace('vk_', '')}"
        contact_info = f"<a href='{user_link}'>Открыть профиль VK</a>"
    else:
        if username:
            user_link = f"https://t.me/{username}"
            contact_info = f"@{username} (<a href='{user_link}'>открыть чат</a>)"
        else:
            contact_info = f"ID {user_id}"
    
    phone_formatted = format_phone(phone) or phone or "Не указан"
    
    msg = (
        f"🔍 <b>#потеряшки — ПОТЕРЯННАЯ ВЕЩЬ ({source})</b>\n\n"
        f"📅 <b>Дата посещения:</b> {lost_date or 'Не указана'}\n"
        f"📍 <b>Место:</b> {lost_location or 'Не указано'}\n"
        f"🎒 <b>Описание:</b> {lost_description or 'Не указано'}\n\n"
        f"👤 <b>Пользователь:</b> {user_name}\n"
        f"📱 <b>Телефон:</b> {phone_formatted}\n"
        f"🔗 <b>Профиль:</b> {contact_info}\n\n"
        f"🕒 <i>{datetime.now().strftime('%d.%m.%Y %H:%M')}</i>"
    )
    return msg


# ============ ФУНКЦИОНАЛ ФОТОГРАФИЙ ============

def needs_photo_request(message: str) -> bool:
    """Проверить, спрашивает ли клиент о получении фотографий с мероприятия."""
    message_lower = message.lower()
    
    request_keywords = [
        # Получение фото
        "фото отда", "фотографии отда", "когда фото", "где фото",
        "фото не приш", "фотографии не приш", "не прислали фото",
        "обещали фото", "ждём фото", "ждем фото",
        # Фотограф снимал
        "снимал фотограф", "фотограф снимал", "нас снимал",
        "был фотограф", "фотографировал", "фотографировали",
        # Вопросы о готовых фото
        "фото готов", "фотографии готов", "получить фото",
        "забрать фото", "прислать фото",
    ]
    
    return any(kw in message_lower for kw in request_keywords)


def needs_photo_order(message: str) -> bool:
    """Проверить, хочет ли клиент заказать фотографа/фотосессию."""
    message_lower = message.lower()
    
    order_keywords = [
        # Заказ фотографа
        "заказать фотограф", "закажу фотограф", "хочу фотограф",
        "нужен фотограф", "можно фотограф", "есть фотограф",
        # Фотосессия
        "фотосессия", "фотосессию", "фотосъёмка", "фотосъемка",
        # Цена
        "сколько стоит фотограф", "цена фотограф", "стоимость фотограф",
    ]
    
    return any(kw in message_lower for kw in order_keywords)


def format_photo_request_message(
    platform: str,
    user_id: str,
    user_name: str,
    phone: str = None,
    description: str = None,
    username: str = None
) -> str:
    """Форматирование уведомления о запросе фотографий."""
    
    source = "ВКонтакте" if platform == "vk" else "Telegram"
    
    if platform == "vk":
        user_link = f"https://vk.com/id{user_id.replace('vk_', '')}"
        contact_info = f"<a href='{user_link}'>Открыть профиль VK</a>"
    else:
        if username:
            user_link = f"https://t.me/{username}"
            contact_info = f"@{username} (<a href='{user_link}'>открыть чат</a>)"
        else:
            contact_info = f"ID {user_id}"
    
    phone_formatted = format_phone(phone) or phone or "Не указан"
    
    msg = (
        f"📷 <b>#ФОТОГРАФИИ — Запрос фото ({source})</b>\n\n"
        f"💬 <b>Описание:</b> {description or 'Клиент спрашивает о фотографиях'}\n\n"
        f"👤 <b>Клиент:</b> {user_name}\n"
        f"📱 <b>Телефон:</b> {phone_formatted}\n"
        f"🔗 <b>Профиль:</b> {contact_info}\n\n"
        f"🕒 <i>{datetime.now().strftime('%d.%m.%Y %H:%M')}</i>"
    )
    return msg


def format_photo_order_message(
    platform: str,
    user_id: str,
    user_name: str,
    phone: str = None,
    username: str = None
) -> str:
    """Форматирование уведомления о заказе фотографа."""
    
    source = "ВКонтакте" if platform == "vk" else "Telegram"
    
    if platform == "vk":
        user_link = f"https://vk.com/id{user_id.replace('vk_', '')}"
        contact_info = f"<a href='{user_link}'>Открыть профиль VK</a>"
    else:
        if username:
            user_link = f"https://t.me/{username}"
            contact_info = f"@{username} (<a href='{user_link}'>открыть чат</a>)"
        else:
            contact_info = f"ID {user_id}"
    
    phone_formatted = format_phone(phone) or phone or "Не указан"
    
    msg = (
        f"📸 <b>#ФОТОГРАФ_ЗАКАЗ — Заказ фотосессии ({source})</b>\n\n"
        f"💰 <b>Услуга:</b> Фотограф (2500₽/час)\n\n"
        f"👤 <b>Клиент:</b> {user_name}\n"
        f"📱 <b>Телефон:</b> {phone_formatted}\n"
        f"🔗 <b>Профиль:</b> {contact_info}\n\n"
        f"🕒 <i>{datetime.now().strftime('%d.%m.%Y %H:%M')}</i>"
    )
    return msg


# ============ ФУНКЦИОНАЛ ПРЕДЛОЖЕНИЙ О СОТРУДНИЧЕСТВЕ ============

def needs_partnership_proposal(message: str) -> bool:
    """Проверить, предлагает ли клиент сотрудничество/партнёрство."""
    message_lower = message.lower()
    
    proposal_keywords = [
        # Сотрудничество
        "сотрудничеств", "партнёр", "партнер",
        "предложение для вас", "предложить вам",
        "с кем связаться", "кому предложить",
        # Реклама
        "рекламн", "продвижени", "маркетинг",
        # B2B
        "коммерческое предложение", "ком предложение",
        "проведение мероприятия", "корпоратив",
        "услуги для парка", "услуги парку",
        # Поставщики
        "поставщик", "поставка", "закупка",
    ]
    
    return any(kw in message_lower for kw in proposal_keywords)


def format_partnership_message(
    platform: str,
    user_id: str,
    user_name: str,
    proposal_text: str,
    phone: str = None,
    username: str = None
) -> str:
    """Форматирование уведомления о предложении сотрудничества."""
    
    source = "ВКонтакте" if platform == "vk" else "Telegram"
    
    if platform == "vk":
        user_link = f"https://vk.com/id{user_id.replace('vk_', '')}"
        contact_info = f"<a href='{user_link}'>Открыть профиль VK</a>"
    else:
        if username:
            user_link = f"https://t.me/{username}"
            contact_info = f"@{username} (<a href='{user_link}'>открыть чат</a>)"
        else:
            contact_info = f"ID {user_id}"
    
    phone_formatted = format_phone(phone) or phone or "Не указан"
    
    msg = (
        f"🤝 <b>#СОТРУДНИЧЕСТВО — Предложение ({source})</b>\n\n"
        f"💬 <b>Суть предложения:</b>\n{proposal_text[:500]}\n\n"
        f"👤 <b>Контакт:</b> {user_name}\n"
        f"📱 <b>Телефон:</b> {phone_formatted}\n"
        f"🔗 <b>Профиль:</b> {contact_info}\n\n"
        f"🕒 <i>{datetime.now().strftime('%d.%m.%Y %H:%M')}</i>"
    )
    return msg
