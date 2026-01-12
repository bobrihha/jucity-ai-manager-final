"""Telegram Bot — обработчики сообщений."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import re

from core import detect_intent, agent, rag, lead_collector
from db import SessionLocal, Session as DBSession, Message, Lead, BotCommand
from config.settings import MANAGER_CHAT_ID
from core.notifications import (
    send_to_managers, 
    format_lead_message, 
    format_escalation_message, 
    needs_human_escalation
)
from core.lead_service import (
    get_or_create_lead,
    update_lead_from_data,
    mark_lead_sent_to_manager,
    lead_to_dict
)

logger = logging.getLogger(__name__)

# Картинки для основных разделов (локальные файлы на сервере)
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(BASE_DIR, "static", "images")

IMAGES = {
    "general": os.path.join(IMAGES_DIR, "park.jpg"),           # О парке
    "birthday": os.path.join(IMAGES_DIR, "birthday.jpg"),      # День рождения
    "events": os.path.join(IMAGES_DIR, "events.jpg"),          # Афиша
    "confirmation": os.path.join(IMAGES_DIR, "confirmation.png"),  # Подтверждение заявки
}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    user = update.effective_user
    
    # Создаём или получаем сессию в БД
    db = SessionLocal()
    try:
        session = db.query(DBSession).filter(DBSession.telegram_id == str(user.id)).first()
        if not session:
            session = DBSession(telegram_id=str(user.id), park_id="nn")
            db.add(session)
            db.commit()
        else:
            # Сбрасываем intent для нового диалога
            session.intent = "unknown"
            session.lead_data = {}
            db.commit()
    finally:
        db.close()
    
    # Приветственное сообщение с кнопками
    keyboard = [
        [InlineKeyboardButton("📋 Моё бронирование", callback_data="my_booking")],
        [InlineKeyboardButton("🎫 Узнать о парке", callback_data="intent_general")],
        [InlineKeyboardButton("🎉 Организовать праздник", callback_data="intent_birthday")],
        [InlineKeyboardButton("🎪 Афиша и события", callback_data="intent_events")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Добро пожаловать в Джунгли Сити, {user.first_name}! 💚💜\n\n"
        "Здесь каждый день — приключение, а ваш ребёнок — главный герой джунглей!\n\n"
        "Я Джуси — ваш проводник по парку. С радостью помогу:\n"
        "• Узнать всё о парке и ценах\n"
        "• Организовать незабываемый день рождения\n"
        "• Рассказать о ближайших событиях\n\n"
        "Что вас интересует? 👇",
        reply_markup=reply_markup
    )


from core.utils import get_prices_from_knowledge, get_afisha_events


async def prices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /prices — цены на билеты."""
    prices = get_prices_from_knowledge()
    
    await update.message.reply_text(
        "💰 <b>Цены на безлимитный билет</b>\n\n"
        f"🟢 Понедельник (супер-цена): <b>{prices['monday']} ₽</b>\n"
        f"🔵 Будни (вт-пт): <b>{prices['weekday']} ₽</b>\n"
        f"🔴 Выходные: <b>{prices['weekend']} ₽</b>\n\n"
        "✅ Взрослые — БЕСПЛАТНО\n"
        "✅ Дети до 1 года — БЕСПЛАТНО\n\n"
        "<b>Скидки:</b>\n"
        "• Дети 1-4 года: -20% в будни\n"
        "• Многодетные: -30% (вт-вс)\n"
        "• После 20:00: -50%\n"
        "• Именинник: -50% (±5 дней от ДР)\n\n"
        "Напишите, если нужна помощь с расчётом! 😊",
        parse_mode="HTML"
    )


async def birthday_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /birthday — запуск бронирования ДР."""
    user = update.effective_user
    prices = get_prices_from_knowledge()
    
    db = SessionLocal()
    try:
        # 1. Проверяем, есть ли активная (незавершенная) заявка
        active_lead = db.query(Lead).filter(
            Lead.telegram_id == str(user.id),
            Lead.park_id == "nn",
            Lead.status.in_(["new", "contacted"]),
            Lead.sent_to_manager == False
        ).first()

        if active_lead:
            # Если есть черновик — спрашиваем пользователя
            keyboard = [
                [InlineKeyboardButton("✏️ Продoлжить текущую", callback_data="lead_continue")],
                [InlineKeyboardButton("➕ Создать новую", callback_data="lead_new")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🎉 <b>У вас есть незавершенная заявка!</b>\n\n"
                f"Мы уже начали оформлять праздник (ID: {active_lead.id}).\n"
                f"Хотите продолжить её заполнение или начать новую?",
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            return  # Прерываем, ждем нажатия кнопки

        # 2. Если нет активной заявки — начинаем новую (как раньше)
        session = db.query(DBSession).filter(DBSession.telegram_id == str(user.id)).first()
        if not session:
            session = DBSession(telegram_id=str(user.id), park_id="nn")
            db.add(session)
        session.intent = "birthday"
        session.lead_data = {}  # Очищаем контекст, так как это новая заявка
        db.commit()
    finally:
        db.close()
    
    # Стандартное приветствие для НОВОЙ заявки
    await update.message.reply_text(
        "🎉 <b>День рождения в Джунгли Сити!</b>\n\n"
        "Что входит (от 6 детей):\n"
        "✅ Комната на 3 часа — БЕСПЛАТНО\n"
        "✅ Именинник — БЕСПЛАТНО (только при 7+ детях!)\n"
        "✅ Взрослые — БЕСПЛАТНО\n"
        "✅ Безлимит на все аттракционы весь день\n\n"
        f"<b>Цены на билеты:</b>\n"
        f"• Будни (вт-пт): {prices['weekday']} ₽\n"
        f"• Выходные: {prices['weekend']} ₽\n"
        f"• Понедельник: {prices['monday']} ₽\n\n"
        "ℹ️ Если детей меньше 7 — можно забронировать столик в ресторане (именинник со скидкой 50% на вход)\n\n"
        "Чтобы рассчитать и забронировать — ответьте:\n"
        "📅 <b>На какую дату планируете праздник?</b>",
        parse_mode="HTML"
    )


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /schedule — режим работы."""
    await update.message.reply_text(
        "🕐 <b>Режим работы Джунгли Сити</b>\n\n"
        "📍 Нижний Новгород, ТЦ «Лента»\n\n"
        "• Понедельник: 12:00 - 22:00\n"
        "• Вторник - Воскресенье: 10:00 - 22:00\n\n"
        "⚠️ Вход в парк до 21:00\n"
        "🍕 Ресторан принимает заказы до 21:00",
        parse_mode="HTML"
    )


async def afisha_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /afisha — афиша событий."""
    await update.message.reply_text(
        "🎪 <b>Афиша Джунгли Сити</b>\n\n"
        "Актуальные события и мероприятия:\n"
        "👉 <a href='https://nn.jucity.ru/afisha/'>Открыть афишу</a>\n\n"
        "У нас регулярно проходят:\n"
        "• Шоу-программы\n"
        "• Мастер-классы\n"
        "• Дискотеки\n"
        "• Праздничные мероприятия\n\n"
        "Спрашивайте — расскажу подробнее! 🌟",
        parse_mode="HTML"
    )


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /rules — правила парка."""
    await update.message.reply_text(
        "📋 <b>Правила посещения Джунгли Сити</b>\n\n"
        "🧦 <b>Носки обязательны</b> на игровой территории\n\n"
        "👨‍👩‍👧 <b>Дети под присмотром</b> взрослых\n\n"
        "🍕 <b>Своя еда запрещена</b>\n"
        "   (кроме детского питания и воды)\n\n"
        "🚫 <b>Запрещено:</b>\n"
        "• Алкоголь\n"
        "• Домашние животные\n"
        "• Опасные предметы\n\n"
        "♿ Есть пандусы и лифты через ТЦ «Лента»",
        parse_mode="HTML"
    )


async def human_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /human — вызов живого менеджера."""
    user = update.effective_user
    
    # Отправляем уведомление менеджерам
    escalation_msg = format_escalation_message(
        platform="telegram",
        user_id=str(user.id),
        username=user.username,
        user_name=user.first_name or "Неизвестный",
        message="[Запрос через команду /human]"
    )
    await send_to_managers(escalation_msg)
    
    await update.message.reply_text(
        "👤 <b>Запрос передан менеджеру!</b>\n\n"
        "Наш специалист скоро свяжется с вами.\n\n"
        "📞 Или позвоните: <b>+7 (831) 213-50-50</b>\n"
        "💬 WhatsApp: +7 (962) 509-74-93",
        parse_mode="HTML"
    )


async def contacts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /contacts — контакты и как добраться."""
    await update.message.reply_text(
        "📍 <b>Как нас найти</b>\n\n"
        "<b>Адрес:</b>\n"
        "г. Нижний Новгород, ул. Коминтерна, д. 11\n"
        "ТЦ «Лента», 1 этаж\n\n"
        "<b>Телефоны:</b>\n"
        "📞 +7 (831) 213-50-50\n"
        "💬 WhatsApp: +7 (962) 509-74-93\n\n"
        "<b>Как добраться:</b>\n"
        "🚇 Метро «Буревестник» — 250 м\n"
        "🚌 Автобус 90, 95, 71, 78, 29 → ост. «Варя»\n"
        "🚋 Троллейбус 5, 8 → ост. «Варя»\n"
        "🚗 Бесплатная парковка у ТЦ",
        parse_mode="HTML"
    )


async def cafe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /cafe — меню ресторана."""
    await update.message.reply_text(
        "🍕 <b>Ресторан Джунгли Сити</b>\n\n"
        "У нас вкусно и для детей, и для взрослых!\n\n"
        "📖 <b>Меню:</b>\n"
        "👉 <a href='https://catalog.botcicada.ru/menu.html'>Открыть меню</a>\n\n"
        "🎂 <b>Торты на заказ:</b>\n"
        "👉 <a href='https://catalog.botcicada.ru/cakes.html'>Каталог тортов</a>\n\n"
        "⏰ Ресторан работает до 21:00",
        parse_mode="HTML"
    )


async def promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /promo — текущие акции."""
    await update.message.reply_text(
        "🎁 <b>Акции Джунгли Сити</b>\n\n"
        "На данный момент специальных акций нет.\n\n"
        "Следите за обновлениями на нашем сайте:\n"
        "👉 https://nn.jucity.ru/\n\n"
        "А пока — приглашаем отметить праздник у нас! 🎉\n"
        "Напишите /birthday для расчёта стоимости.",
        parse_mode="HTML"
    )


def format_booking_info(lead) -> str:
    """Форматировать информацию о бронировании для пользователя."""
    status_emoji = {
        "new": "📝 Новая заявка",
        "contacted": "📞 Связываемся",
        "booked": "✅ Подтверждено"
    }
    
    text = f"📋 <b>Ваше бронирование #{lead.id}</b>\n\n"
    text += f"📊 Статус: {status_emoji.get(lead.status, lead.status)}\n"
    
    if lead.event_date:
        text += f"📅 Дата: <b>{lead.event_date}</b>\n"
    if lead.time:
        text += f"⏰ Время: <b>{lead.time}</b>\n"
    if lead.kids_count:
        text += f"👶 Детей: {lead.kids_count}\n"
    if lead.adults_count:
        text += f"👨 Взрослых: {lead.adults_count}\n"
    if lead.child_name:
        text += f"🎂 Именинник: {lead.child_name}"
        if lead.child_age:
            text += f" ({lead.child_age} лет)"
        text += "\n"
    if lead.format:
        text += f"🏠 Формат: {lead.format}\n"
    if lead.room:
        text += f"🚪 Комната: {lead.room}\n"
    if lead.customer_name:
        text += f"👤 Контакт: {lead.customer_name}\n"
    if lead.phone:
        text += f"📞 Телефон: {lead.phone}\n"
    
    return text


async def booking_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /booking — показать информацию о бронировании."""
    user = update.effective_user
    
    db = SessionLocal()
    try:
        # Ищем активные лиды пользователя (только отправленные менеджеру)
        leads = db.query(Lead).filter(
            Lead.telegram_id == str(user.id),
            Lead.status.in_(["new", "contacted", "booked"]),
            Lead.sent_to_manager == True
        ).order_by(Lead.created_at.desc()).limit(3).all()
        
        if not leads:
            # Проверяем черновики
            drafts = db.query(Lead).filter(
                Lead.telegram_id == str(user.id),
                Lead.sent_to_manager == False,
                Lead.status.in_(["new", "contacted"])
            ).first()
            
            if drafts:
                await update.message.reply_text(
                    "📝 У вас есть незавершённая заявка на праздник.\n\n"
                    "Чтобы продолжить оформление, напишите /birthday\n"
                    "или задайте мне любой вопрос! 😊"
                )
            else:
                keyboard = [
                    [InlineKeyboardButton("🎉 Забронировать праздник", callback_data="intent_birthday")]
                ]
                await update.message.reply_text(
                    "📋 У вас пока нет активных бронирований.\n\n"
                    "Хотите организовать незабываемый день рождения? 🎂",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            return
        
        # Показываем бронирования
        for lead in leads:
            text = format_booking_info(lead)
            
            keyboard = [
                [InlineKeyboardButton("✏️ Изменить дату/время", callback_data=f"change_{lead.id}_datetime")],
                [InlineKeyboardButton("👥 Изменить кол-во гостей", callback_data=f"change_{lead.id}_guests")],
                [InlineKeyboardButton("🎁 Добавить услуги", callback_data=f"change_{lead.id}_extras")],
                [InlineKeyboardButton("❌ Отменить бронь", callback_data=f"change_{lead.id}_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
    finally:
        db.close()


async def dynamic_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Универсальный обработчик динамических команд из БД."""
    command_name = update.message.text.replace("/", "").split("@")[0]  # удаляем @botname если есть
    
    db = SessionLocal()
    try:
        command = db.query(BotCommand).filter(
            BotCommand.command == command_name, 
            BotCommand.is_active == True
        ).first()
        
        if command and command.response:
            await update.message.reply_text(
                command.response,
                parse_mode="HTML"
            )
        else:
            # Если команда не найдена в БД или неактивна
            # Можно отправить заглушку или просто игнорировать
            logger.warning(f"Command /{command_name} not found or inactive.")
    except Exception as e:
        logger.error(f"Error executing dynamic command /{command_name}: {e}")
    finally:
        db.close()


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на инлайн-кнопки."""
    query = update.callback_query
    await query.answer()
    
    # Получаем сессию
    db = SessionLocal()
    session = db.query(DBSession).filter(DBSession.telegram_id == str(query.from_user.id)).first()
    chat_id = query.message.chat_id
    
    try:
        if query.data == "lead_continue":
            # Пользователь решил продолжить текущую заявку
            if session:
                session.intent = "birthday"
                # lead_data НЕ сбрасываем, чтобы бот знал контекст
                
                # Загружаем данные из существующего лида
                active_lead = db.query(Lead).filter(
                    Lead.telegram_id == str(query.from_user.id),
                    Lead.park_id == "nn",
                    Lead.status.in_(["new", "contacted"]),
                    Lead.sent_to_manager == False
                ).first()
                if active_lead:
                    session.lead_data = lead_to_dict(active_lead)
                
                db.commit()

            try:
                await query.message.delete()
            except Exception:
                pass
            
            await update.callback_query.message.reply_text(
                "Отлично! Продолжаем оформление. На чем мы остановились? 😊"
            )

        elif query.data == "lead_new":
            # Пользователь хочет новую заявку. Старую помечаем как "deferred" (отложенную)
            active_lead = db.query(Lead).filter(
                Lead.telegram_id == str(query.from_user.id),
                Lead.park_id == "nn",
                Lead.status.in_(["new", "contacted"]),
                Lead.sent_to_manager == False
            ).first()
            
            if active_lead:
                active_lead.status = "deferred"
                db.commit()
            
            if session:
                session.intent = "birthday"
                session.lead_data = {}  # Сбрасываем для новой
                db.commit()

            try:
                await query.message.delete()
            except Exception:
                pass
            
            # Запускаем стандартный флоу новой заявки (картинка + текст)
            prices = get_prices_from_knowledge()
            caption = (
                "🎉 <b>День рождения в Джунгли Сити!</b>\n\n"
                "Что входит (от 6 детей):\n"
                "✅ Комната на 3 часа — БЕСПЛАТНО\n"
                "✅ Именинник — БЕСПЛАТНО (только при 7+ детях!)\n"
                "✅ Взрослые — БЕСПЛАТНО\n"
                "✅ Безлимит на все аттракционы весь день\n\n"
                f"<b>Цены на билеты:</b>\n"
                f"• Будни (вт-пт): {prices['weekday']} ₽\n"
                f"• Выходные: {prices['weekend']} ₽\n"
                f"• Понедельник: {prices['monday']} ₽\n\n"
                "ℹ️ Если детей меньше 7 — можно забронировать столик в ресторане (именинник со скидкой 50% на вход)\n\n"
                "Чтобы рассчитать и забронировать — ответьте:\n"
                "📅 <b>На какую дату планируете праздник?</b>"
            )
            with open(IMAGES["birthday"], 'rb') as photo_file:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file,
                    caption=caption,
                    parse_mode="HTML"
                )

        elif query.data == "intent_birthday":
            if session:
                session.intent = "birthday"
                db.commit()
            
            # Удаляем старое сообщение с кнопками
            try:
                await query.message.delete()
            except Exception:
                pass
            
            # Отправляем фото с текстом
            caption = (
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
            with open(IMAGES["birthday"], 'rb') as photo_file:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file,
                    caption=caption
                )
            
        elif query.data == "intent_general":
            if session:
                session.intent = "general"
                db.commit()
            
            # Удаляем старое сообщение с кнопками
            try:
                await query.message.delete()
            except Exception:
                pass
            
            # Отправляем фото с текстом
            caption = (
                "Отлично! 🎢\n\n"
                "Спрашивайте что угодно о парке:\n"
                "• Цены и режим работы\n"
                "• Аттракционы и развлечения\n"
                "• Скидки и акции\n"
                "• Как добраться\n\n"
                "Я с удовольствием помогу! 😊"
            )
            with open(IMAGES["general"], 'rb') as photo_file:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file,
                    caption=caption
                )
            
        elif query.data == "intent_events":
            if session:
                session.intent = "events"
                db.commit()
            
            # Удаляем старое сообщение с кнопками
            try:
                await query.message.delete()
            except Exception:
                pass
            
            # Отправляем фото с текстом (динамически из afisha.txt)
            caption = get_afisha_events() or (
                "🎪 Афиша Джунгли Сити!\n\n"
                "Следите за нашими событиями:\n"
                "👉 nn.jucity.ru/afisha/"
            )
            with open(IMAGES["events"], 'rb') as photo_file:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file,
                    caption=caption
                )
        
        elif query.data == "my_booking":
            # Кнопка "Моё бронирование" из стартового меню
            try:
                await query.message.delete()
            except Exception:
                pass
            
            # Ищем активные лиды
            leads = db.query(Lead).filter(
                Lead.telegram_id == str(query.from_user.id),
                Lead.status.in_(["new", "contacted", "booked"]),
                Lead.sent_to_manager == True
            ).order_by(Lead.created_at.desc()).limit(3).all()
            
            if not leads:
                keyboard = [
                    [InlineKeyboardButton("🎉 Забронировать праздник", callback_data="intent_birthday")]
                ]
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="📋 У вас пока нет активных бронирований.\n\n"
                         "Хотите организовать незабываемый день рождения? 🎂",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                for lead in leads:
                    text = format_booking_info(lead)
                    keyboard = [
                        [InlineKeyboardButton("✏️ Изменить дату/время", callback_data=f"change_{lead.id}_datetime")],
                        [InlineKeyboardButton("👥 Изменить кол-во гостей", callback_data=f"change_{lead.id}_guests")],
                        [InlineKeyboardButton("🎁 Добавить услуги", callback_data=f"change_{lead.id}_extras")],
                        [InlineKeyboardButton("❌ Отменить бронь", callback_data=f"change_{lead.id}_cancel")]
                    ]
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode="HTML"
                    )
        
        elif query.data.startswith("change_"):
            # Обработка запросов на изменение бронирования
            parts = query.data.split("_")
            lead_id = int(parts[1])
            change_type = parts[2]
            
            change_type_text = {
                "datetime": "📅 Изменить дату/время",
                "guests": "👥 Изменить количество гостей",
                "extras": "🎁 Добавить услуги",
                "cancel": "❌ Отменить бронирование"
            }
            
            # Получаем информацию о лиде
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            
            if lead:
                # Формируем уведомление менеджеру
                msg_text = (
                    f"⚠️ <b>Запрос на изменение бронирования</b>\n\n"
                    f"📋 Заявка: #{lead.id}\n"
                    f"🔄 Тип: {change_type_text.get(change_type, change_type)}\n\n"
                    f"👤 Клиент: {lead.customer_name or 'Не указано'}\n"
                    f"📞 Телефон: {lead.phone or 'Не указан'}\n"
                    f"💬 Telegram: @{query.from_user.username or 'нет username'}\n\n"
                    f"📅 Текущая дата: {lead.event_date or 'Не указана'}\n"
                    f"⏰ Время: {lead.time or 'Не указано'}\n"
                    f"👶 Детей: {lead.kids_count or 0}"
                )
                await send_to_managers(msg_text)
                
                # Отвечаем пользователю
                if change_type == "cancel":
                    response_text = (
                        "❌ Запрос на отмену бронирования передан менеджеру.\n\n"
                        "Наши феи праздников свяжутся с вами в ближайшее время для подтверждения."
                    )
                else:
                    response_text = (
                        f"✅ Запрос на изменение передан менеджеру!\n\n"
                        f"Тип изменения: {change_type_text.get(change_type, change_type)}\n\n"
                        f"Наши феи праздников свяжутся с вами в ближайшее время. 💚"
                    )
                
                await query.message.reply_text(response_text)
            else:
                await query.message.reply_text(
                    "К сожалению, бронирование не найдено. Попробуйте /booking ещё раз."
                )
    finally:
        db.close()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений."""
    user = update.effective_user
    message_text = update.message.text
    user_id = str(user.id)
    
    logger.info(f"Message from {user.first_name} ({user_id}): {message_text}")
    
    db = SessionLocal()
    try:
        # Получаем или создаём сессию
        session = db.query(DBSession).filter(DBSession.telegram_id == user_id).first()
        if not session:
            session = DBSession(telegram_id=user_id, park_id="nn", username=user.username)
            db.add(session)
            db.commit()
            db.refresh(session)
        else:
            # Обновляем username если изменился
            if user.username and session.username != user.username:
                session.username = user.username
                db.commit()
        
        # Сохраняем сообщение пользователя
        user_message = Message(session_id=session.id, role="user", content=message_text)
        db.add(user_message)
        db.commit()

        # --- НОВАЯ ЛОГИКА: Проверка на ID приложения ---
        # Ищем только если есть явное упоминание "id", "код" и НЕТ признаков телефона
        app_id_match = None
        
        # Исключаем телефонные паттерны (содержат +, скобки, много дефисов)
        if not re.search(r'[\+\(\)]{1,}|\d{1,3}\-\d{1,3}\-\d{1,3}', message_text):
            # Ищем ID с ключевым словом перед цифрами
            app_id_match = re.search(r'(?:app\s*id|мой\s*id|ид|код)\s*[:.=\-]?\s*(\d{4,6})\b', message_text, re.IGNORECASE)
            
            # Если не нашли с ключевым словом — ищем "голое" 5-6 значное число
            if not app_id_match:
                # Только если сообщение короткое (до 10 символов) — скорее всего это App ID
                clean_text = message_text.strip()
                if len(clean_text) <= 10 and re.match(r'^\d{5,6}$', clean_text):
                    app_id_match = re.search(r'(\d{5,6})', clean_text)
        
        if app_id_match:
            app_id = app_id_match.group(1)
            
            # Отправляем уведомление менеджерам
            try:
                msg_text = (
                    f"🔔 <b>Новый App ID!</b>\n\n"
                    f"👤 Пользователь: {user.first_name or 'Неизвестный'} (@{user.username or 'нет username'})\n"
                    f"🔢 ID: <code>{app_id}</code>\n"
                    f"💬 Сообщение: {message_text}"
                )
                await send_to_managers(msg_text)
                logger.info(f"App ID {app_id} notification sent to manager")
            except Exception as e:
                logger.error(f"Failed to notify manager about App ID: {e}")
            
            # Отвечаем пользователю
            await update.message.reply_text(
                "Принято! Передал менеджеру для начисления баллов. "
                "Баллы будут начислены в течение 7 дней. "
                "Спасибо, что вы с нами! 💚💜"
            )
            return
        # -----------------------------------------------
        
        # Проверяем запрос живого менеджера
        if needs_human_escalation(message_text):
            # Отправляем уведомление менеджерам
            escalation_msg = format_escalation_message(
                platform="telegram",
                user_id=user_id,
                username=user.username,
                user_name=user.first_name or "Неизвестный",
                message=message_text
            )
            await send_to_managers(escalation_msg)
            
            # Отвечаем пользователю
            await update.message.reply_text(
                "Понимаю, что вам нужна помощь живого менеджера! 🙋\n\n"
                "Я уже передал ваш запрос нашей команде. "
                "Менеджер свяжется с вами в ближайшее время!\n\n"
                "А пока я могу ответить на ваши вопросы о парке или празднике. 😊"
            )
            return
        
        # Определяем intent
        current_intent = session.intent
        intent_result = detect_intent(message_text)
        
        # Логика переключения intent
        if current_intent == "unknown":
            # Первое определение
            session.intent = intent_result.intent
            db.commit()
            logger.info(f"Intent detected: {intent_result.intent} ({intent_result.confidence})")
        elif current_intent == "general" and intent_result.intent == "birthday" and intent_result.confidence >= 0.7:
            # Переключаемся с general на birthday при явных триггерах
            session.intent = "birthday"
            session.lead_data = {}  # Сбрасываем данные лида
            db.commit()
            logger.info(f"Intent switched: general -> birthday")
        elif current_intent == "general" and intent_result.intent == "events" and intent_result.confidence >= 0.7:
            # Переключаемся с general на events при вопросах об афише
            session.intent = "events"
            db.commit()
            logger.info(f"Intent switched: general -> events")
        elif current_intent == "birthday" and intent_result.intent == "events" and intent_result.confidence >= 0.8:
            # С birthday на events только при очень явных триггерах
            session.intent = "events"
            db.commit()
            logger.info(f"Intent switched: birthday -> events")
        
        # Получаем историю сообщений
        history = []
        for msg in db.query(Message).filter(Message.session_id == session.id).order_by(Message.id.desc()).limit(10).all():
            history.insert(0, {"role": msg.role, "content": msg.content})
        
        # Получаем контекст из RAG
        rag_context = rag.get_context(message_text, session.intent)
        
        # Для birthday ветки — сохраняем данные в Lead (надёжно в БД)
        current_lead = None
        lead_data = {}
        
        if session.intent == "birthday":
            # Получаем или создаём Lead в БД
            current_lead = get_or_create_lead(
                user_id, 
                source="telegram", 
                park_id="nn", 
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            
            # Извлекаем данные из сообщения пользователя
            extracted = agent.extract_lead_data(message_text, {})
            
            # Обновляем Lead в БД
            if extracted:
                current_lead = update_lead_from_data(current_lead.id, extracted)
                logger.info(f"Lead #{current_lead.id} updated with: {extracted}")
            
            # Формируем lead_data для передачи в agent
            lead_data = lead_to_dict(current_lead)
        
        # Показываем индикатор "печатает..."
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # Генерируем ответ
        response = agent.generate_response(
            message=message_text,
            intent=session.intent,
            history=history,
            rag_context=rag_context,
            lead_data=lead_data
        )
        
        # Сохраняем ответ
        assistant_message = Message(session_id=session.id, role="assistant", content=response)
        db.add(assistant_message)
        db.commit()
        
        # КРИТИЧНО: Извлекаем данные из ОТВЕТА бота и сохраняем сразу
        # Бот часто суммаризирует данные в своем ответе (например: "Спасибо, Наталья!")
        if current_lead and session.intent == "birthday":
            response_data = agent.extract_lead_data(response, lead_data)
            if response_data:
                current_lead = update_lead_from_data(current_lead.id, response_data)
                logger.info(f"Lead #{current_lead.id} updated from bot response: {response_data}")
                # Обновляем lead_data для следующих итераций
                lead_data = lead_to_dict(current_lead)
        
        # Отправляем ответ пользователю (ВСЕГДА)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=response)
        
        # Проверяем, это подтверждение заявки?
        is_confirmation = current_lead and not current_lead.sent_to_manager and \
            any(x in response.lower() for x in ["передал", "передаю заявку", "менеджер свяжется", "отдел праздников"])
        
        if is_confirmation:
            # Заявка подтверждена — дополнительно отправляем картинку!
            logger.info(f"Bot confirmed booking for Lead #{current_lead.id} — sending photo!")
            
            # Извлекаем данные из ОТВЕТА бота
            final_data = agent.extract_lead_data(response, lead_data)
            current_lead = update_lead_from_data(current_lead.id, final_data)
            logger.info(f"Lead #{current_lead.id} final data: {lead_to_dict(current_lead)}")
            
            # Отправляем картинку ДОПОЛНИТЕЛЬНО
            try:
                with open(IMAGES["confirmation"], 'rb') as photo_file:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=photo_file
                    )
            except Exception as e:
                logger.error(f"Failed to send confirmation photo: {e}")
            
            # Отправляем уведомление менеджеру
            msg_text = format_lead_message("telegram", user_id, lead_to_dict(current_lead), username=user.username)
            await send_to_managers(msg_text)
            
            # Помечаем как отправленный
            mark_lead_sent_to_manager(current_lead.id)
            logger.info(f"Manager notification sent for Lead #{current_lead.id}!")
        

        
        # Если intent всё ещё unknown — показываем кнопки
        if session.intent == "unknown":
            keyboard = [
                [InlineKeyboardButton("🎟 Узнать о парке", callback_data="intent_general")],
                [InlineKeyboardButton("🎉 Организовать праздник", callback_data="intent_birthday")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Или выберите, что вас интересует:",
                reply_markup=reply_markup
            )
            
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text(
            "Ой, что-то пошло не так 😅\n"
            "Попробуйте ещё раз или позвоните нам: +7 (831) 213-50-50"
        )
    finally:
        db.close()


async def notify_manager(update: Update, lead, context: ContextTypes.DEFAULT_TYPE):
    """Отправить уведомление менеджеру о новом лиде."""
    if not MANAGER_CHAT_ID:
        logger.warning("MANAGER_CHAT_ID not configured, skipping notification")
        return
    
    user = update.effective_user
    summary = lead.get_summary()
    summary += f"\n\n📱 Telegram: @{user.username}" if user.username else f"\n\n📱 Telegram ID: {user.id}"
    
    try:
        await context.bot.send_message(
            chat_id=MANAGER_CHAT_ID,
            text=summary,
            parse_mode="Markdown"
        )
        logger.info(f"Manager notified about lead from {user.id}")
    except Exception as e:
        logger.error(f"Failed to notify manager: {e}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок."""
    logger.error(f"Update {update} caused error {context.error}")
