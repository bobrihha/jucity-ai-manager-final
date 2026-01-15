"""VK Bot Handler — обработчик сообщений ВКонтакте."""

import asyncio
import json
import logging
from vkbottle.bot import Bot, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text, PhotoMessageUploader
import re
import aiohttp

from core.agent import Agent
from core.rag import RAGSystem
from core.intent_router import detect_intent
from db.database import SessionLocal
from db.models import Session as DBSession, Message as DBMessage, Lead
from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger(__name__)

# Картинки для основных разделов (локальные файлы на сервере)
import os as os_module
VK_BASE_DIR = os_module.path.dirname(os_module.path.dirname(os_module.path.abspath(__file__)))
VK_IMAGES_DIR = os_module.path.join(VK_BASE_DIR, "static", "images")

IMAGES = {
    "general": os_module.path.join(VK_IMAGES_DIR, "park.jpg"),           # О парке
    "birthday": os_module.path.join(VK_IMAGES_DIR, "birthday.jpg"),      # День рождения
    "events": os_module.path.join(VK_IMAGES_DIR, "events.jpg"),          # Афиша
    "confirmation": os_module.path.join(VK_IMAGES_DIR, "confirmation.png"),  # Подтверждение
}

from core.notifications import (
    send_to_managers, 
    format_lead_message, 
    format_escalation_message, 
    needs_human_escalation,
    needs_lost_item_flow,
    format_lost_item_message,
    needs_booking_change_request,
    get_booking_change_type,
    format_booking_change_message,
    needs_photo_request,
    needs_photo_order,
    format_photo_request_message,
    format_photo_order_message,
    needs_partnership_proposal,
    format_partnership_message

)
from core.lead_service import (
    get_or_create_lead,
    update_lead_from_data,
    mark_lead_sent_to_manager,
    lead_to_dict,
    save_amocrm_deal_id,
    mark_status_notified
)
from core.utils import get_afisha_events
from core.amocrm import send_lead_to_amocrm, amocrm_client


def create_vk_bot(token: str, group_id: int):
    """Создать и настроить VK бота."""
    bot = Bot(token=token)
    
    # Инициализируем агента и RAG
    agent = Agent()
    rag = RAGSystem(park_id="nn")
    
    # Загрузчик фотографий
    photo_uploader = PhotoMessageUploader(bot.api)
    
    async def upload_photo_from_file(file_path: str, peer_id: int) -> str:
        """Загрузить фото из локального файла и вернуть attachment."""
        try:
            if os_module.path.exists(file_path):
                attachment = await photo_uploader.upload(file_path, peer_id=peer_id)
                return attachment
            else:
                logger.error(f"Photo file not found: {file_path}")
        except Exception as e:
            logger.error(f"Failed to upload photo from {file_path}: {e}")
        return None
    
    # Клавиатура для старта
    start_keyboard = (
        Keyboard(one_time=False, inline=False)
        .add(Text("🎟 Узнать о парке"), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(Text("🎉 Организовать праздник"), color=KeyboardButtonColor.POSITIVE)
        .row()
        .add(Text("📅 Моё бронирование"), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(Text("🎪 Афиша и события"), color=KeyboardButtonColor.SECONDARY)
    )

    @bot.on.message(text=["Начать", "начать", "Start", "start", "/start"])
    async def start_handler(message: Message):
        """Приветственное сообщение."""
        user_info = await message.get_user()
        first_name = user_info.first_name if user_info else "Гость"
        
        await message.answer(
            f"Добро пожаловать в Джунгли Сити, {first_name}! 💚💜\n\n"
            "Здесь каждый день — приключение, а ваш ребёнок — главный герой джунглей!\n\n"
            "Я Джуси — ваш проводник по парку. С радостью помогу:\n"
            "• Узнать всё о парке и ценах\n"
            "• Организовать незабываемый день рождения\n"
            "• Рассказать о ближайших событиях\n\n"
            "Что вас интересует? 👇",
            keyboard=start_keyboard
        )

    @bot.on.message(text="📅 Моё бронирование")
    async def my_booking_handler(message: Message):
        """Отображение информации о бронированиях."""
        user_id = message.from_id
        db = SessionLocal()
        
        try:
            # 1. Пробуем найти контакт в AmoCRM (вернёт по VK ID)
            contact = await amocrm_client.find_contact_by_vk_id(user_id)
            
            if contact:
                # Получаем все сделки
                deals = await amocrm_client.get_deals_for_contact(contact["id"])
                
                if deals:
                    for deal in deals[:3]:  # До 3х последних
                        text = format_booking_info_vk(deal)
                        
                        # ID для кнопок (или deal_id, или локальный)
                        lead_id = deal["deal_id"]
                        
                        keyboard = (
                            Keyboard(inline=True)
                            .add(Text("✏️ Изм. дату/время", payload={"cmd": f"change_{lead_id}_datetime"}), color=KeyboardButtonColor.PRIMARY)
                            .row()
                            .add(Text("👥 Изм. гостей", payload={"cmd": f"change_{lead_id}_guests"}), color=KeyboardButtonColor.PRIMARY)
                            .row()
                            .add(Text("🎁 Доб. услуги", payload={"cmd": f"change_{lead_id}_extras"}), color=KeyboardButtonColor.PRIMARY)
                            .row()
                            .add(Text("❌ Отменить", payload={"cmd": f"change_{lead_id}_cancel"}), color=KeyboardButtonColor.NEGATIVE)
                        ).get_json()
                        
                        await message.answer(text, keyboard=keyboard)
                    return
            
            # 2. Fallback: локальная БД (если сделка еще не в AmoCRM)
            leads = db.query(Lead).filter(
                Lead.telegram_id == f"vk_{user_id}",
                Lead.status.in_(["new", "contacted", "booked"]),
                Lead.sent_to_manager == True
            ).order_by(Lead.created_at.desc()).limit(3).all()
            
            if not leads:
                await message.answer(
                    "📋 У вас пока нет активных бронирований.\n\n"
                    "Хотите организовать незабываемый день рождения? 🎂",
                    keyboard=(
                        Keyboard(inline=True)
                        .add(Text("🎉 Забронировать", payload={"cmd": "lead_new"}), color=KeyboardButtonColor.POSITIVE)
                    ).get_json()
                )
            else:
                for lead in leads:
                    deal_dict = lead_to_dict(lead)
                    # Добавляем deal_id если есть
                    deal_dict["deal_id"] = lead.amocrm_deal_id or f"L{lead.id}"
                    
                    text = format_booking_info_vk(deal_dict)
                    lead_id = lead.id
                    
                    keyboard = (
                        Keyboard(inline=True)
                        .add(Text("✏️ Изм. дату/время", payload={"cmd": f"change_{lead_id}_datetime"}), color=KeyboardButtonColor.PRIMARY)
                        .row()
                        .add(Text("👥 Изм. гостей", payload={"cmd": f"change_{lead_id}_guests"}), color=KeyboardButtonColor.PRIMARY)
                        .row()
                        .add(Text("🎁 Доб. услуги", payload={"cmd": f"change_{lead_id}_extras"}), color=KeyboardButtonColor.PRIMARY)
                        .row()
                        .add(Text("❌ Отменить", payload={"cmd": f"change_{lead_id}_cancel"}), color=KeyboardButtonColor.NEGATIVE)
                    ).get_json()
                    
                    await message.answer(text, keyboard=keyboard)

        except Exception as e:
            logger.error(f"Error in my_booking_handler: {e}")
            await message.answer("Произошла ошибка при получении данных. Попробуйте позже.")
        finally:
            db.close()

    def format_booking_info_vk(deal: dict) -> str:
        """Форматирование брони для VK."""
        return (
            f"📋 Бронирование #{deal.get('deal_id')}\n\n"
            f"📅 Дата: {deal.get('event_date', 'Не указана')}\n"
            f"🕐 Время: {deal.get('event_time', 'Не указано')}\n"
            f"👶 Детей: {deal.get('kids_count', 'Не указано')}\n"
            f"👨‍👩‍👧 Взрослых: {deal.get('adults_count', 0)}\n"
            f"🏠 Комната: {deal.get('room', 'Не выбрана')}\n"
            f"🎁 Доп. услуги: {deal.get('extras', 'Нет')}\n"
        )

    @bot.on.message(text="🎟 Узнать о парке")
    async def general_handler(message: Message):
        """Переключение на general intent."""
        db = SessionLocal()
        try:
            session = get_or_create_session(db, message.from_id, "vk")
            session.intent = "general"
            db.commit()
        finally:
            db.close()
        
        # Загружаем и отправляем фото с текстом
        text = (
            "Отлично! 🎢\n\n"
            "Спрашивайте что угодно о парке:\n"
            "• Цены и режим работы\n"
            "• Аттракционы и развлечения\n"
            "• Скидки и акции\n"
            "• Как добраться\n\n"
            "Я с удовольствием помогу! 😊"
        )
        attachment = await upload_photo_from_file(IMAGES["general"], message.peer_id)
        if attachment:
            await message.answer(text, attachment=attachment)
        else:
            await message.answer(text)
    
    @bot.on.message(text="🎉 Организовать праздник")
    async def birthday_handler(message: Message):
        """Переключение на birthday intent."""
        user_id = message.from_id
        db = SessionLocal()
        
        try:
            # 1. Проверяем активную заявку (незавершенную)
            active_lead = db.query(Lead).filter(
                Lead.telegram_id == f"vk_{user_id}",
                Lead.park_id == "nn",
                Lead.status.in_(["new", "contacted"]),
                Lead.sent_to_manager == False
            ).first()

            if active_lead:
                # Если есть черновик — спрашиваем пользователя
                keyboard = (
                    Keyboard(inline=True)
                    .add(Text("✏️ Продолжить текущую", payload={"cmd": "lead_continue"}), color=KeyboardButtonColor.POSITIVE)
                    .row()
                    .add(Text("➕ Создать новую", payload={"cmd": "lead_new"}), color=KeyboardButtonColor.SECONDARY)
                ).get_json()
                
                await message.answer(
                    f"🎉 У вас есть незавершенная заявка! (ID: {active_lead.id})\n\n"
                    "Хотите продолжить её заполнение или начать новую?",
                    keyboard=keyboard
                )
                
                # Обновляем интент сессии, чтобы бот знал контекст
                session = get_or_create_session(db, user_id, "vk")
                session.intent = "birthday" 
                db.commit()
                return

            # 2. Проверяем возвратного клиента (CRM)
            contact = await amocrm_client.find_contact_by_vk_id(user_id)
            if contact:
                contact_info = amocrm_client.get_contact_info(contact)
                found_phone = contact_info.get("phone")
                found_name = contact_info.get("name")
                
                # Если есть телефон — спрашиваем подтверждение
                if found_phone:
                    phone_display = f"+7 {found_phone[-10:-7]} {found_phone[-7:-4]}-{found_phone[-4:-2]}-{found_phone[-2:]}" if len(found_phone) >= 10 else found_phone
                    
                    keyboard = (
                        Keyboard(inline=True)
                        .add(Text(f"✅ Да, {phone_display}", payload={"cmd": "confirm_phone_yes", "phone": found_phone, "name": found_name or ""}), color=KeyboardButtonColor.POSITIVE)
                        .row()
                        .add(Text("📱 Указать другой", payload={"cmd": "confirm_phone_no"}), color=KeyboardButtonColor.SECONDARY)
                    ).get_json()
                    
                    greeting = f"Рады снова видеть вас, {found_name}! 💚" if found_name else "Рады снова вас видеть! 💚"
                    await message.answer(
                        f"{greeting}\n\n📱 Актуален ли этот номер телефона для связи?\n{phone_display}",
                        keyboard=keyboard
                    )
                    
                    # Обновляем интент
                    session = get_or_create_session(db, user_id, "vk")
                    session.intent = "birthday"
                    db.commit()
                    return

            # 3. Если нет активной заявки и не нашли контакт — стандартный старт
            session = get_or_create_session(db, user_id, "vk")
            session.intent = "birthday"
            session.lead_data = {}
            db.commit()
            
        finally:
            db.close()
        
        # Стандартное приветствие
        await send_birthday_intro(message)


    async def send_birthday_intro(message: Message):
        """Отправить стандартное приветствие для ДР."""
        text = (
            "💜💚 Отлично! День рождения в Джунглях — это радость и вау-эмоции! 💚💜\n\n"
            "У нас есть 2 формата праздника — выбирайте, что подойдёт именно вам 💚\n\n"
            "🏠 ТЕМАТИЧЕСКАЯ КОМНАТА (3 часа)\n"
            "—предоставляется при оплате 6 полных детских билетов\n"
            "— от 7 детей — ИМЕНИННИК БЕСПЛАТНО\n"
            "— безлимит на аттракционы 💚\n\n"
            "🍰 Столик в ресторане\n"
            "— без ограничения по времени\n"
            "— именинник — скидка 50% на вход\n"
            "— безлимит на аттракционы 💚\n\n"
            "✨ Аниматоры, торт, шары, аквагрим — по желанию.\n"
            "Давайте подберём идеальный вариант для вас 💜\n\n"
            "📅 На какую дату планируете праздник?"
        )
        attachment = await upload_photo_from_file(IMAGES["birthday"], message.peer_id)
        if attachment:
            await message.answer(text, attachment=attachment)
        else:
            await message.answer(text)


    @bot.on.message(func=lambda message: message.payload is not None)
    async def payload_handler(message: Message):
        """Обработка нажатий на инлайн-кнопки (payload)."""
        payload = json.loads(message.payload)
        cmd = payload.get("cmd")
        user_id = message.from_id
        
        db = SessionLocal()
        try:
            if cmd == "lead_continue":
                # Пользователь хочет продолжить
                session = get_or_create_session(db, user_id, "vk")
                session.intent = "birthday"
                db.commit()
                
                await message.answer("Отлично! Продолжаем оформление. 📝\nНа каком вопросе мы остановились? (я сейчас проверю историю...)")
                # Тут в идеале бот должен посмотреть историю, но пока просто подтверждаем.
                # RAG/Agent сам подхватит контекст из истории сообщений.
                
            elif cmd == "lead_new":
                # Пользователь хочет новую заявку — закрываем старые
                old_leads = db.query(Lead).filter(
                    Lead.telegram_id == f"vk_{user_id}",
                    Lead.park_id == "nn",
                    Lead.status.in_(["new", "contacted"])
                ).all()
                for l in old_leads:
                    l.status = "cancelled"
                
                session = get_or_create_session(db, user_id, "vk")
                session.intent = "birthday"
                session.lead_data = {}
                db.commit()
                
                await message.answer("Хорошо, начнём сначала! 🔄")
                await send_birthday_intro(message)
                
            elif cmd == "confirm_phone_yes":
                # Подтвердил телефон -> Создаём лид с этим телефоном
                phone = payload.get("phone")
                name = payload.get("name")
                
                # Создаем лид
                lead = get_or_create_lead(f"vk_{user_id}", source="vk", park_id="nn")
                
                # Обновляем данные
                update_data = {"phone": phone}
                if name:
                    update_data["customer_name"] = name
                
                update_lead_from_data(lead.id, update_data)
                
                # Инициализируем сессию birthday
                session = get_or_create_session(db, user_id, "vk")
                session.intent = "birthday"
                db.commit()
                
                await message.answer("✅ Телефон подтвержден!\n\n📅 На какую дату планируете праздник?")
                
            elif cmd == "confirm_phone_no":
                # Не подтвердил -> Стандартный флоу (спросим телефон позже)
                session = get_or_create_session(db, user_id, "vk")
                session.intent = "birthday"
                session.lead_data = {}
                db.commit()
                
                await message.answer("Понял, укажем другой номер в процессе. 👌")
                await send_birthday_intro(message)

            elif cmd.startswith("change_"):
                # cmd формат: change_{lead_id}_{action}
                parts = cmd.split("_")
                
                # action - последняя часть
                action = parts[-1]
                # deal_id/lead_id - все что между change и action
                deal_id = "_".join(parts[1:-1])
                
                # Формируем текст запроса
                action_map = {
                    "datetime": "Изменить дату/время",
                    "guests": "Изменить количество гостей",
                    "extras": "Добавить услуги",
                    "cancel": "❌ ОТМЕНИТЬ БРОНЬ"
                }
                action_text = action_map.get(action, "Изменение бронирования")
                
                # Определяем телефон и создаем задачу в AmoCRM
                phone_info = ""
                is_amo_deal = not str(deal_id).startswith("L")
                
                if is_amo_deal:
                    try:
                        # 1. Ищем контакт для получения телефона
                        contact = await amocrm_client.find_contact_by_vk_id(user_id)
                        if contact:
                            contact_info = amocrm_client.get_contact_info(contact)
                            phone = contact_info.get("phone")
                            if phone:
                                phone_info = f"📱 Телефон: {phone}\n"
                        
                        # 2. Создаем задачу в AmoCRM
                        task_text = f"Клиент просит: {action_text} (из VK Бот)"
                        await amocrm_client.create_task(int(deal_id), task_text)
                    except Exception as e:
                        logger.error(f"Error processing AmoCRM task/contact: {e}")

                # Уведомляем менеджера
                msg_text = (
                    f"⚠️ <b>ЗАПРОС ИЗ VK</b>\n\n"
                    f"🆔 Сделка/Лид: {deal_id}\n"
                    f"👤 Пользователь: id{user_id}\n"
                    f"{phone_info}"
                    f"❓ Запрос: {action_text}"
                )
                await send_to_managers(msg_text)
                
                await message.answer(f"✅ Запрос на «{action_text}» передан менеджеру! Мы свяжемся с вами в ближайшее время.")

            elif cmd == "lost_phone_yes":
                # Подтвердил телефон — отправляем уведомление
                session = get_or_create_session(db, user_id, "vk")
                lost_data = session.lead_data or {}
                user_info = await message.get_user()
                user_name = f"{user_info.first_name} {user_info.last_name}".strip() if user_info else "Гость"
                
                msg = format_lost_item_message(
                    platform="vk",
                    user_id=str(user_id),
                    user_name=user_name,
                    lost_date=lost_data.get("lost_date"),
                    lost_location=lost_data.get("lost_location"),
                    lost_description=lost_data.get("lost_description"),
                    phone=lost_data.get("phone")
                )
                await send_to_managers(msg)
                
                # Сбрасываем режим
                session.intent = "unknown"
                session.lead_data = {}
                db.commit()
                
                await message.answer(
                    "✅ Спасибо! Мы передали информацию в бюро находок.\n\n"
                    "Менеджер свяжется с вами, если вещь найдётся. 💚"
                )

            elif cmd == "lost_phone_no":
                # Не подтвердил — запрашиваем новый номер
                session = get_or_create_session(db, user_id, "vk")
                lost_data = session.lead_data or {}
                lost_data["lost_step"] = "phone"
                lost_data.pop("phone", None)
                session.lead_data = lost_data
                flag_modified(session, "lead_data")
                db.commit()
                
                await message.answer("📱 Укажите номер телефона для связи:")
                
        except Exception as e:
            logger.error(f"Error handling payload: {e}")
            await message.answer("Произошла ошибка при обработке кнопки. Попробуйте написать текстом.")
        finally:
            db.close()
    
    @bot.on.message(text="🎪 Афиша и события")
    async def events_handler(message: Message):
        """Переключение на events intent."""
        db = SessionLocal()
        try:
            session = get_or_create_session(db, message.from_id, "vk")
            session.intent = "events"
            db.commit()
        finally:
            db.close()
        
        # Загружаем и отправляем фото с текстом (динамически из afisha.txt)
        text = get_afisha_events() or (
            "🎪 Афиша Джунгли Сити!\n\n"
            "Следите за нашими событиями:\n"
            "👉 nn.jucity.ru/afisha/"
        )
        attachment = await upload_photo_from_file(IMAGES["events"], message.peer_id)
        if attachment:
            await message.answer(text, attachment=attachment)
        else:
            await message.answer(text)
    
    # Тексты кнопок, которые обрабатываются отдельными хендлерами
    BUTTON_TEXTS = [
        "🎟 Узнать о парке",
        "🎉 Организовать праздник",
        "🎪 Афиша и события",
        "Начать", "начать", "Start", "start", "/start"
    ]
    
    @bot.on.message()
    async def message_handler(message: Message):
        """Обработка всех текстовых сообщений."""
        if not message.text:
            return
        
        message_text = message.text.strip()
        
        # Игнорируем тексты кнопок — они обрабатываются отдельными хендлерами
        if message_text in BUTTON_TEXTS:
            return
        
        user_id = message.from_id
        
        db = SessionLocal()
        try:
            # Получаем или создаём сессию
            session = get_or_create_session(db, user_id, "vk")
            
            # Сохраняем сообщение пользователя
            user_msg = DBMessage(session_id=session.id, role="user", content=message_text)
            db.add(user_msg)
            # -----------------------------------------------

            # --- НОВАЯ ЛОГИКА: Проверка на ID приложения ---
            # Ищем только если есть явное упоминание "id", "код" и НЕТ признаков телефона
            app_id_match = None
            
            # Исключаем телефонные паттерны (содержат +, скобки, много дефисов)
            if not re.search(r'[\+\(\)]{1,}|\d{1,3}\-\d{1,3}\-\d{1,3}', message_text):
                # Теперь ищем ID только с явным ключевым словом перед цифрами
                app_id_match = re.search(r'(?:app\s*id|мой\s*id|ид|код)\s*[:.=\-]?\s*(\d{4,6})\b', message_text, re.IGNORECASE)
            
            if app_id_match:
                app_id = app_id_match.group(1)
                
                # Получаем имя пользователя
                user_info = await message.get_user()
                user_name = f"{user_info.first_name} {user_info.last_name}" if user_info else "Неизвестный"
                
                # Отправляем уведомление менеджерам (через Telegram bridge)
                try:
                    msg_text = (
                        f"🔔 <b>Новый App ID (из ВК)!</b>\n\n"
                        f"👤 Пользователь: {user_name} (id{user_id})\n"
                        f"🔢 ID: <code>{app_id}</code>\n"
                        f"💬 Сообщение: {message_text}"
                    )
                    await send_to_managers(msg_text)
                    logger.info(f"VK App ID {app_id} notification sent to manager")
                except Exception as e:
                    logger.error(f"Failed to notify manager about VK App ID: {e}")
                
                # Отвечаем пользователю
                await message.answer(
                    "Принято! Передал менеджеру для начисления баллов. "
                    "Баллы будут начислены в течение 7 дней. "
                    "Спасибо, что вы с нами! 💚💜"
                )
                return
            # -----------------------------------------------
            
            # ============ ПОТЕРЯШКИ — обработка потерянных вещей ============
            # Проверяем, находимся ли мы уже в режиме опроса
            lost_data = session.lead_data or {}
            lost_step = lost_data.get("lost_step")
            
            if lost_step:
                # Проверяем, не хочет ли пользователь выйти из опроса
                exit_keywords = [
                    "ничего не потерял", "ничего не потеряла", "ничего не теряла", "ничего не терял",
                    "не потерял", "не потеряла", "не теряла", "не терял",
                    "я не про это", "я о другом", "хотел спросить", "хотела спросить",
                    "я спрашиваю", "речь не об этом", "не об этом",
                    "отмена", "стоп", "хватит", "выход", "exit", "cancel",
                    "можно купить", "где купить", "продаёте", "продаете",
                ]
                message_lower = message_text.lower()
                if any(kw in message_lower for kw in exit_keywords):
                    # Сбрасываем режим потеряшек
                    session.intent = "unknown"
                    session.lead_data = {}
                    db.commit()
                    
                    await message.answer(
                        "Ой, простите за недопонимание! 😊\n\n"
                        "Чем могу помочь? Спрашивайте — я отвечу на любые вопросы о парке, ценах или празднике! 💚"
                    )
                    return
                
                # Мы в процессе опроса о потерянной вещи
                user_info = await message.get_user()
                vk_fname = user_info.first_name if user_info else "Гость"
                vk_lname = user_info.last_name if user_info else ""
                user_name = f"{vk_fname} {vk_lname}".strip()
                
                if lost_step == "date":
                    lost_data["lost_date"] = message_text
                    lost_data["lost_step"] = "location"
                    session.lead_data = lost_data
                    flag_modified(session, "lead_data")
                    db.commit()
                    await message.answer("📍 В каком примерно месте вы могли оставить вещь?\n(аттракцион, комната, ресторан и т.д.)")
                    return
                    
                elif lost_step == "location":
                    lost_data["lost_location"] = message_text
                    lost_data["lost_step"] = "description"
                    session.lead_data = lost_data
                    flag_modified(session, "lead_data")
                    db.commit()
                    await message.answer("🔍 Опишите, что именно потеряли?\n(цвет, размер, особенности)")
                    return
                    
                elif lost_step == "description":
                    lost_data["lost_description"] = message_text
                    lost_data["lost_step"] = "phone"
                    session.lead_data = lost_data
                    flag_modified(session, "lead_data")
                    db.commit()
                    
                    # Проверяем телефон в CRM
                    try:
                        contact = await amocrm_client.find_contact_by_vk_id(user_id)
                        if contact:
                            contact_info = amocrm_client.get_contact_info(contact)
                            phone = contact_info.get("phone")
                            if phone:
                                lost_data["phone"] = phone
                                lost_data["lost_step"] = "confirm_phone"
                                session.lead_data = lost_data
                                flag_modified(session, "lead_data")
                                db.commit()
                                
                                keyboard = (
                                    Keyboard(inline=True)
                                    .add(Text("✅ Да", payload={"cmd": "lost_phone_yes"}), color=KeyboardButtonColor.POSITIVE)
                                    .add(Text("❌ Другой", payload={"cmd": "lost_phone_no"}), color=KeyboardButtonColor.NEGATIVE)
                                ).get_json()
                                
                                await message.answer(f"📱 Для связи использовать номер {phone}?", keyboard=keyboard)
                                return
                    except Exception as e:
                        logger.error(f"Failed to check CRM for lost item: {e}")
                    
                    # Нет телефона — запрашиваем
                    await message.answer("📱 Укажите номер телефона для связи:")
                    return
                    
                elif lost_step == "phone":
                    lost_data["phone"] = message_text
                    
                    # Отправляем уведомление
                    msg = format_lost_item_message(
                        platform="vk",
                        user_id=str(user_id),
                        user_name=user_name,
                        lost_date=lost_data.get("lost_date"),
                        lost_location=lost_data.get("lost_location"),
                        lost_description=lost_data.get("lost_description"),
                        phone=lost_data.get("phone")
                    )
                    await send_to_managers(msg)
                    
                    # Сбрасываем режим
                    session.intent = "unknown"
                    session.lead_data = {}
                    db.commit()
                    
                    await message.answer(
                        "✅ Спасибо! Мы передали информацию в бюро находок.\n\n"
                        "Менеджер свяжется с вами, если вещь найдётся. 💚"
                    )
                    return
            
            # Проверяем триггер потеряшек (начало опроса)
            # Если уже был в режиме lost_item но lost_step нет — сбросим и начнём заново
            if session.intent == "lost_item" and not lost_step:
                session.intent = "unknown"
                db.commit()
            
            if needs_lost_item_flow(message_text):
                session.intent = "lost_item"
                session.lead_data = {"lost_step": "date"}
                flag_modified(session, "lead_data")
                db.commit()
                
                await message.answer(
                    "Ой, как жаль! 😔 Давайте попробуем найти вашу вещь.\n\n"
                    "📅 Когда вы были в парке? (напишите дату)"
                )
                return
            # ============ КОНЕЦ ПОТЕРЯШКИ ============
            
            # Проверяем запрос живого менеджера
            if needs_human_escalation(message_text):
                # Получаем имя пользователя
                user_info = await message.get_user()
                user_name = f"{user_info.first_name} {user_info.last_name}" if user_info else "Неизвестный"
                
                # Отправляем уведомление менеджерам
                escalation_msg = format_escalation_message(
                    platform="vk",
                    user_id=str(user_id),
                    username=None,  # VK не имеет username как Telegram
                    user_name=user_name,
                    message=message_text
                )
                await send_to_managers(escalation_msg)
                
                # Отвечаем пользователю
                await message.answer(
                    "Понимаю, что вам нужна помощь живого менеджера! 🙋\n\n"
                    "Я уже передал ваш запрос нашей команде. "
                    "Менеджер свяжется с вами в ближайшее время!\n\n"
                    "А пока я могу ответить на ваши вопросы о парке или празднике. 😊"
                )
                return
            
            # ============ ЗАПРОСЫ НА ИЗМЕНЕНИЕ БРОНИРОВАНИЯ ============
            # Проверяем, просит ли клиент изменить/отменить бронь текстом
            if needs_booking_change_request(message_text):
                user_info = await message.get_user()
                user_name = f"{user_info.first_name} {user_info.last_name}" if user_info else "Гость"
                change_type = get_booking_change_type(message_text)
                
                # Ищем сделку пользователя в AmoCRM
                deal_id = None
                phone = None
                try:
                    contact = await amocrm_client.find_contact_by_vk_id(user_id)
                    if contact:
                        contact_info = amocrm_client.get_contact_info(contact)
                        phone = contact_info.get("phone")
                        
                        # Получаем последнюю сделку
                        deals = await amocrm_client.get_contact_deals(contact["id"])
                        if deals:
                            deal_id = str(deals[0].get("id", ""))
                            
                            # Создаём задачу в AmoCRM
                            task_text = f"Клиент просит: {change_type} (из VK Бот)"
                            await amocrm_client.create_task(int(deal_id), task_text)
                except Exception as e:
                    logger.error(f"Error checking AmoCRM for booking change: {e}")
                
                # Отправляем уведомление менеджерам
                msg = format_booking_change_message(
                    platform="vk",
                    user_id=str(user_id),
                    user_name=user_name,
                    change_type=change_type,
                    message_text=message_text,
                    deal_id=deal_id,
                    phone=phone
                )
                await send_to_managers(msg)
                
                # Отвечаем пользователю
                await message.answer(
                    f"✅ Ваш запрос на «{change_type}» передан менеджеру!\n\n"
                    "Мы свяжемся с вами в ближайшее время для уточнения деталей. 📞"
                )
                return
            # ============ КОНЕЦ ЗАПРОСОВ НА ИЗМЕНЕНИЕ ============
            
            # ============ ОБРАБОТКА ЗАПРОСОВ ФОТОГРАФИЙ ============
            # Проверяем, уже в режиме опроса про фото?
            photo_data = session.lead_data or {}
            photo_step = photo_data.get("photo_step")
            
            if photo_step:
                user_info = await message.get_user()
                user_name = f"{user_info.first_name} {user_info.last_name}".strip() if user_info else "Гость"
                
                if photo_step == "phone":
                    # Валидируем телефон
                    phone_pattern = r'[\d\+\(\)\-\s]{7,}'
                    if re.search(phone_pattern, message_text):
                        photo_data["phone"] = message_text
                        photo_type = photo_data.get("type", "request")
                        
                        if photo_type == "order":
                            # Заказ фотографа — создаём заявку в AmoCRM
                            msg = format_photo_order_message(
                                platform="vk",
                                user_id=str(user_id),
                                user_name=user_name,
                                phone=message_text
                            )
                            await send_to_managers(msg)
                            
                            # Создаём лид и отправляем в AmoCRM
                            try:
                                lead = get_or_create_lead(f"vk_{user_id}", source="vk", park_id="nn")
                                lead.phone = message_text
                                lead.name = user_name
                                lead.extras = "Фотограф (2500₽/час)"
                                db.commit()
                                
                                # Отправляем в AmoCRM
                                await send_lead_to_amocrm(
                                    lead_data={
                                        "customer_name": user_name,
                                        "phone": message_text,
                                        "extras": "📸 Заказ фотографа (2500₽/час)",
                                        "source": "vk"
                                    },
                                    vk_id=user_id
                                )
                            except Exception as e:
                                logger.error(f"Error creating photo order lead: {e}")

                            
                            await message.answer(
                                "📸 Отлично! Мы передали вашу заявку в отдел праздников.\n\n"
                                "Менеджер свяжется с вами, чтобы подобрать удобное время для фотосессии! 💚"
                            )
                        else:
                            # Запрос фото — уведомление менеджерам
                            msg = format_photo_request_message(
                                platform="vk",
                                user_id=str(user_id),
                                user_name=user_name,
                                phone=message_text,
                                description=photo_data.get("description")
                            )
                            await send_to_managers(msg)
                            
                            await message.answer(
                                "📷 Спасибо! Мы передали ваш запрос.\n\n"
                                "Менеджер свяжется с вами по поводу фотографий! 💚"
                            )
                        
                        # Сбрасываем режим
                        session.intent = "unknown"
                        session.lead_data = {}
                        db.commit()
                        return
                    else:
                        await message.answer("📱 Пожалуйста, укажите корректный номер телефона:")
                        return
            
            # Проверяем триггер заказа фотографа (сначала — более специфичный)
            if needs_photo_order(message_text):
                user_info = await message.get_user()
                user_name = f"{user_info.first_name} {user_info.last_name}".strip() if user_info else "Гость"
                
                # Проверяем телефон в CRM
                phone = None
                try:
                    contact = await amocrm_client.find_contact_by_vk_id(user_id)
                    if contact:
                        contact_info_crm = amocrm_client.get_contact_info(contact)
                        phone = contact_info_crm.get("phone")
                except Exception as e:
                    logger.error(f"Error finding contact for photo order: {e}")
                
                if phone:
                    # Телефон есть — сразу отправляем
                    session.lead_data = {"type": "order", "phone": phone}
                    flag_modified(session, "lead_data")
                    
                    msg = format_photo_order_message(
                        platform="vk",
                        user_id=str(user_id),
                        user_name=user_name,
                        phone=phone
                    )
                    await send_to_managers(msg)
                    
                    # Создаём лид
                    try:
                        lead = get_or_create_lead(f"vk_{user_id}", source="vk", park_id="nn")
                        lead.phone = phone
                        lead.name = user_name
                        lead.extras = "Фотограф (2500₽/час)"
                        db.commit()
                        
                        # Отправляем в AmoCRM
                        await send_lead_to_amocrm(
                            lead_data={
                                "customer_name": user_name,
                                "phone": phone,
                                "extras": "📸 Заказ фотографа (2500₽/час)",
                                "source": "vk"
                            },
                            vk_id=user_id
                        )

                    except Exception as e:
                        logger.error(f"Error creating photo order lead: {e}")

                    
                    session.intent = "unknown"
                    session.lead_data = {}
                    db.commit()
                    
                    await message.answer(
                        "📸 Отличная идея! Фотографии получаются яркие и эмоциональные — отличная память!\n\n"
                        "💰 Стоимость фотографа: **2500₽/час**\n\n"
                        "Мы передали вашу заявку в отдел праздников, вам перезвонят и подберут удобное время! 💚"
                    )
                else:
                    # Телефона нет — запрашиваем
                    session.intent = "photo_order"
                    session.lead_data = {"photo_step": "phone", "type": "order"}
                    flag_modified(session, "lead_data")
                    db.commit()
                    
                    await message.answer(
                        "📸 Отличная идея! Фотографии получаются яркие и эмоциональные — отличная память!\n\n"
                        "💰 Стоимость фотографа: **2500₽/час**\n\n"
                        "📱 Оставьте ваш номер телефона, мы передадим его в отдел праздников — вам перезвонят и подберут удобное время."
                    )
                return
            
            # Проверяем триггер запроса фотографий (получение готовых фото)
            if needs_photo_request(message_text):
                user_info = await message.get_user()
                user_name = f"{user_info.first_name} {user_info.last_name}".strip() if user_info else "Гость"
                
                # Проверяем телефон в CRM
                phone = None
                try:
                    contact = await amocrm_client.find_contact_by_vk_id(user_id)
                    if contact:
                        contact_info_crm = amocrm_client.get_contact_info(contact)
                        phone = contact_info_crm.get("phone")
                except Exception as e:
                    logger.error(f"Error finding contact for photo request: {e}")
                
                if phone:
                    # Телефон есть — сразу отправляем уведомление
                    msg = format_photo_request_message(
                        platform="vk",
                        user_id=str(user_id),
                        user_name=user_name,
                        phone=phone,
                        description=message_text[:200]
                    )
                    await send_to_managers(msg)
                    
                    await message.answer(
                        "📷 Понимаю, что вы ждёте свои фотографии!\n\n"
                        "Мы передали ваш запрос, с вами свяжутся в ближайшее время. 💚"
                    )
                else:
                    # Телефона нет — запрашиваем
                    session.intent = "photo_request"
                    session.lead_data = {"photo_step": "phone", "type": "request", "description": message_text[:200]}
                    flag_modified(session, "lead_data")
                    db.commit()
                    
                    await message.answer(
                        "📷 Понимаю, что вы ждёте свои фотографии!\n\n"
                        "📱 Оставьте ваш номер телефона, чтобы мы могли связаться с вами:"
                    )
                return
            # ============ КОНЕЦ ОБРАБОТКИ ФОТОГРАФИЙ ============
            
            # ============ ОБРАБОТКА ПРЕДЛОЖЕНИЙ О СОТРУДНИЧЕСТВЕ ============
            partnership_data = session.lead_data if session.lead_data else {}
            partnership_step = partnership_data.get("partnership_step")
            
            # Если уже в процессе опроса по предложению
            if partnership_step == "details":
                # Получили суть предложения, запрашиваем телефон
                session.lead_data = {
                    "partnership_step": "phone",
                    "proposal_text": message_text[:500]
                }
                flag_modified(session, "lead_data")
                db.commit()
                
                await message.answer(
                    "📝 Отлично, записал!\n\n"
                    "📱 Оставьте, пожалуйста, ваш номер телефона для связи:"
                )
                return
            
            if partnership_step == "phone":
                # Проверяем телефон
                phone_pattern = r'[\d\+\(\)\-\s]{7,}'
                if re.search(phone_pattern, message_text):
                    user_info = await message.get_user()
                    user_name = f"{user_info.first_name} {user_info.last_name}".strip() if user_info else "Гость"
                    
                    # Отправляем уведомление менеджерам
                    msg = format_partnership_message(
                        platform="vk",
                        user_id=str(user_id),
                        user_name=user_name,
                        proposal_text=partnership_data.get("proposal_text", ""),
                        phone=message_text
                    )
                    await send_to_managers(msg)
                    
                    # Сбрасываем состояние
                    session.intent = "unknown"
                    session.lead_data = {}
                    db.commit()
                    
                    await message.answer(
                        "🤝 Спасибо за ваше предложение!\n\n"
                        "Мы передали его руководству. С вами свяжутся в ближайшее время! 💚"
                    )
                    return
                else:
                    await message.answer("📱 Пожалуйста, укажите корректный номер телефона:")
                    return
            
            # Проверяем триггер предложения о сотрудничестве
            if needs_partnership_proposal(message_text):
                session.intent = "partnership"
                session.lead_data = {"partnership_step": "details"}
                flag_modified(session, "lead_data")
                db.commit()
                
                await message.answer(
                    "🤝 Здорово, что вы хотите сотрудничать с нами!\n\n"
                    "📝 Расскажите, пожалуйста, подробнее о вашем предложении — в чём его суть?"
                )
                return
            # ============ КОНЕЦ ОБРАБОТКИ ПРЕДЛОЖЕНИЙ ============
            
            # Определяем intent

            current_intent = session.intent
            intent_result = detect_intent(message_text)
            
            # Логика переключения
            if current_intent == "unknown":
                session.intent = intent_result.intent
                db.commit()
            elif current_intent == "general" and intent_result.intent in ["birthday", "events"] and intent_result.confidence >= 0.7:
                session.intent = intent_result.intent
                if intent_result.intent == "birthday":
                    session.lead_data = {}
                db.commit()
            
            # Получаем историю
            history = []
            for msg in db.query(DBMessage).filter(DBMessage.session_id == session.id).order_by(DBMessage.id.desc()).limit(10).all():
                history.insert(0, {"role": msg.role, "content": msg.content})
            
            # Получаем контекст из RAG
            rag_context = rag.get_context(message_text, session.intent)
            
            # Для birthday — сохраняем данные в Lead (надёжно в БД)
            current_lead = None
            lead_data = {}
            
            if session.intent == "birthday":
                # Получаем инфо о пользователе
                user_info = await message.get_user()
                vk_fname = user_info.first_name if user_info else None
                vk_lname = user_info.last_name if user_info else None
                
                # Получаем или создаём Lead в БД
                current_lead = get_or_create_lead(f"vk_{user_id}", source="vk", park_id="nn", first_name=vk_fname, last_name=vk_lname)
                
                # Извлекаем данные из ВСЕЙ истории переписки (не только последнего сообщения)
                # Это критически важно т.к. имя, телефон, дата могут быть в разных сообщениях
                current_lead_data = lead_to_dict(current_lead)
                
                # Собираем все сообщения пользователя из истории
                user_messages = [msg["content"] for msg in history if msg["role"] == "user"][-10:]
                full_conversation = "\n".join(user_messages)
                
                extracted = agent.extract_lead_data(full_conversation, current_lead_data)
                
                # Обновляем Lead в БД
                if extracted:
                    # Если имя не указано — берём из профиля VK
                    if not extracted.get("customer_name") and vk_fname:
                        extracted["customer_name"] = vk_fname
                    
                    current_lead = update_lead_from_data(current_lead.id, extracted)
                    logger.info(f"Lead #{current_lead.id} updated with: {extracted}")
                
                # РАННЯЯ ОТПРАВКА В CRM: Как только есть телефон — создаём сделку
                lead_data = lead_to_dict(current_lead)
                
                # Проверяем валидность телефона (минимум 10 цифр)
                phone = lead_data.get("phone", "")
                phone_digits = ''.join(filter(str.isdigit, str(phone))) if phone else ""
                has_valid_phone = len(phone_digits) >= 10
                
                if has_valid_phone and not current_lead.amocrm_deal_id:
                    # Телефон есть, сделки ещё нет — СОЗДАЁМ!
                    logger.info(f"Phone received! Creating AmoCRM deal for Lead #{current_lead.id}")
                    try:
                        lead_dict = lead_data.copy()
                        lead_dict["source"] = "vk"
                        lead_dict["first_name"] = vk_fname
                        
                        # Передаём vk_id для объединения контактов
                        result = await send_lead_to_amocrm(
                            lead_dict, 
                            telegram_id=None,
                            username=None,
                            vk_id=user_id  # VK user ID
                        )
                        
                        if result and result[0]:
                            amocrm_deal_id, amocrm_contact_id = result
                            # Сохраняем ID сделки через lead_service (правильная сессия БД)
                            save_amocrm_deal_id(current_lead.id, str(amocrm_deal_id))
                            current_lead.amocrm_deal_id = str(amocrm_deal_id)  # Обновляем локальный объект
                            logger.info(f"Lead #{current_lead.id} created in AmoCRM, deal_id={amocrm_deal_id}")
                            
                            # Добавляем историю переписки в AmoCRM
                            try:
                                conversation_lines = []
                                for msg in history[-20:]:
                                    role_emoji = "👤" if msg["role"] == "user" else "🤖"
                                    conversation_lines.append(f"{role_emoji} {msg['content'][:300]}")
                                conversation = "\n\n".join(conversation_lines)
                                await amocrm_client.add_note(
                                    amocrm_deal_id, 
                                    f"📱 Переписка из ВКонтакте:\n\n{conversation}"
                                )
                                logger.info(f"VK conversation history added to AmoCRM deal {amocrm_deal_id}")
                            except Exception as e:
                                logger.error(f"Failed to add VK conversation to AmoCRM: {e}")
                            
                            # Отправляем уведомление менеджерам
                            msg_text = format_lead_message("vk", str(user_id), lead_data)
                            await send_to_managers(msg_text)
                            mark_lead_sent_to_manager(current_lead.id)
                            logger.info(f"Manager notification sent for Lead #{current_lead.id}!")
                    except Exception as e:
                        logger.error(f"Failed to send to AmoCRM: {e}")
                
                elif has_valid_phone and current_lead.amocrm_deal_id:
                    # Телефон есть, сделка уже есть — ОБНОВЛЯЕМ!
                    try:
                        await amocrm_client.update_deal_fields(
                            int(current_lead.amocrm_deal_id), 
                            lead_data
                        )
                    except Exception as e:
                        logger.error(f"Failed to update AmoCRM deal: {e}")
                
                # Формируем lead_data для передачи в agent (добавляем first_name для имени из профиля)
                lead_data["first_name"] = vk_fname
            
            # Проверяем статус сделки в AmoCRM
            deal_in_work = False
            status_just_changed = False
            
            if current_lead and current_lead.amocrm_deal_id:
                try:
                    deal_in_work = await amocrm_client.is_deal_in_work(int(current_lead.amocrm_deal_id))
                    
                    # Если статус изменился и клиент ещё не уведомлён
                    if deal_in_work and not current_lead.status_notified:
                        status_just_changed = True
                        mark_status_notified(current_lead.id)
                        logger.info(f"Lead #{current_lead.id} status changed to 'in work', notifying client")
                except Exception as e:
                    logger.error(f"Failed to check deal status: {e}")
            
            # Если статус только что изменился — сначала уведомляем
            if status_just_changed:
                await message.answer("🎉 Отличные новости! Феи праздников уже начали работу над вашим мероприятием! 🧚‍♀️✨")
            
            # Генерируем ответ (передаём флаг deal_in_work)
            response = agent.generate_response(
                message=message_text,
                intent=session.intent,
                history=history,
                rag_context=rag_context,
                lead_data=lead_data,
                deal_in_work=deal_in_work
            )
            
            # Сохраняем ответ
            assistant_msg = DBMessage(session_id=session.id, role="assistant", content=response)
            db.add(assistant_msg)
            db.commit()
            
            # КРИТИЧНО: Извлекаем данные из ОТВЕТА бота и сохраняем сразу
            # Бот часто суммаризирует данные в своем ответе (например: "Формат: Тематическая комната")
            if current_lead and session.intent == "birthday":
                response_data = agent.extract_lead_data(response, lead_data)
                if response_data:
                    current_lead = update_lead_from_data(current_lead.id, response_data)
                    logger.info(f"Lead #{current_lead.id} updated from bot response: {response_data}")
                    # Обновляем lead_data для следующих итераций
                    lead_data = lead_to_dict(current_lead)
                    
                    # Синхронизируем с AmoCRM если сделка уже создана
                    if current_lead.amocrm_deal_id:
                        try:
                            await amocrm_client.update_deal_fields(
                                int(current_lead.amocrm_deal_id), 
                                lead_data
                            )
                            
                            # Обновляем переписку в AmoCRM (добавляем новую заметку)
                            conversation_lines = []
                            for msg in history[-20:]:
                                role_emoji = "👤" if msg["role"] == "user" else "🤖"
                                conversation_lines.append(f"{role_emoji} {msg['content'][:300]}")
                            conversation = "\n\n".join(conversation_lines)
                            await amocrm_client.add_note(
                                int(current_lead.amocrm_deal_id), 
                                f"📱 Обновление переписки (ВК):\n\n{conversation}"
                            )
                            
                            logger.info(f"AmoCRM deal {current_lead.amocrm_deal_id} synced with new VK data")
                        except Exception as e:
                            logger.error(f"Failed to sync AmoCRM deal: {e}")
            
            # Отправляем ответ (VK лимит 4096 символов)
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await message.answer(response[i:i+4000])
            else:
                await message.answer(response)
            
            # Проверяем, бот сообщил что заявка принята (для отправки фото)
            if current_lead and any(x in response.lower() for x in ["передана феям", "заявка принята", "передал заявку"]):
                logger.info(f"Bot announced confirmation for Lead #{current_lead.id} — sending photo!")
                
                # Извлекаем данные из ОТВЕТА бота и обновляем
                final_data = agent.extract_lead_data(response, lead_data)
                current_lead = update_lead_from_data(current_lead.id, final_data)
                
                # Обновляем сделку в AmoCRM (если есть)
                if current_lead.amocrm_deal_id:
                    try:
                        await amocrm_client.update_deal_fields(
                            int(current_lead.amocrm_deal_id), 
                            lead_to_dict(current_lead)
                        )
                    except Exception as e:
                        logger.error(f"Failed to update AmoCRM deal: {e}")
                
                
        except Exception as e:
            logger.error(f"VK Error: {e}")
            await message.answer(
                "Ой, что-то пошло не так 😅\n"
                "Попробуйте ещё раз или позвоните нам: +7 (831) 213-50-50"
            )
        finally:
            db.close()
    
    return bot


def get_or_create_session(db, user_id: int, platform: str = "vk") -> DBSession:
    """Получить или создать сессию пользователя."""
    # Используем telegram_id с префиксом для VK
    vk_id = f"vk_{user_id}"
    
    session = db.query(DBSession).filter(DBSession.telegram_id == vk_id).first()
    
    if not session:
        session = DBSession(
            telegram_id=vk_id,
            intent="unknown",
            lead_data={}
        )
        db.add(session)
        db.commit()
    
    return session


async def run_vk_bot(token: str, group_id: int):
    """Запустить VK бота."""
    import threading
    
    bot = create_vk_bot(token, group_id)
    logger.info(f"VK Bot starting for group {group_id}...")
    
    # Запускаем VK бота в отдельном потоке чтобы избежать конфликта event loop
    # VKBottle's run_polling создает свой event loop
    def run_in_thread():
        try:
            # Создаем новый event loop для этого потока
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            bot.run_forever()
        except Exception as e:
            logger.error(f"VK Bot error in thread: {e}")
    
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    logger.info(f"VK Bot started in separate thread for group {group_id}")
    
    # Ждем бесконечно (пока не отменят)
    while True:
        await asyncio.sleep(60)  # Heartbeat every minute


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    VK_TOKEN = os.getenv("VK_TOKEN")
    VK_GROUP_ID = int(os.getenv("VK_GROUP_ID", "0"))
    
    if VK_TOKEN and VK_GROUP_ID:
        asyncio.run(run_vk_bot(VK_TOKEN, VK_GROUP_ID))
    else:
        print("VK_TOKEN and VK_GROUP_ID required!")
