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


from core.utils import get_prices_from_knowledge


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
    
    # Устанавливаем intent = birthday для пользователя
    db = SessionLocal()
    try:
        session = db.query(DBSession).filter(DBSession.telegram_id == str(user.id)).first()
        if not session:
            session = DBSession(telegram_id=str(user.id), park_id="nn")
            db.add(session)
        session.intent = "birthday"
        session.lead_data = {}
        db.commit()
    finally:
        db.close()
    
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
        "ℹ️ Если детей меньше 7 — можно забронировать столик в ресторане (именинник со скидкой 50%)\n\n"
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
        "🔥 <b>СКИДКА 26% НА ПРАЗДНИК В 2026!</b>\n"
        "Период: до 11 января 2026\n\n"
        "Условия:\n"
        "• Бронирование праздника от 6 детей\n"
        "• Праздник может быть в любой день 2026 года\n"
        "• Скидка НЕ распространяется на пакеты\n\n"
        "<b>Пример:</b>\n"
        "8 детей в субботу: 7 × 1590 = 11 130 ₽\n"
        "Со скидкой 26%: <b>8 236 ₽</b> 💰\n\n"
        "Хотите забронировать со скидкой? Напишите /birthday",
        parse_mode="HTML"
    )


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
    
    try:
        if query.data == "intent_birthday":
            if session:
                session.intent = "birthday"
                db.commit()
            
            # Получаем актуальные цены
            prices = get_prices_from_knowledge()
            
            await query.edit_message_text(
                "Отлично, праздники — это моя любимая тема! 🎉\n\n"
                "Вот что у нас входит:\n"
                "• Комната на 3 часа БЕСПЛАТНО (от 6 детей)\n"
                "• Именинник — БЕСПЛАТНО (только при 7+ детях!)\n"
                "• Взрослые — БЕСПЛАТНО\n"
                "• Безлимит на все аттракционы весь день\n\n"
                "Цены на билеты:\n"
                f"• Будни (вт-пт): {prices['weekday']} ₽\n"
                f"• Выходные: {prices['weekend']} ₽\n"
                f"• Понедельник: {prices['monday']} ₽\n\n"
                "ℹ️ Если детей меньше 7 — можно забронировать столик в ресторане (именинник со скидкой 50%)\n\n"
                "Дополнительно можно заказать аниматоров, торт, шары, аквагрим.\n\n"
                "Чтобы рассчитать стоимость и забронировать, ответьте на пару вопросов.\n\n"
                "📅 **1. На какую дату планируете праздник?** (число и месяц)"
            )
            
        elif query.data == "intent_general":
            if session:
                session.intent = "general"
                db.commit()
            
            await query.edit_message_text(
                "Отлично! 🎢\n\n"
                "Спрашивайте что угодно о парке:\n"
                "• Цены и режим работы\n"
                "• Аттракционы и развлечения\n"
                "• Скидки и акции\n"
                "• Как добраться\n\n"
                "Я с удовольствием помогу! 😊"
            )
            
        elif query.data == "intent_events":
            if session:
                session.intent = "events"
                db.commit()
            
            await query.edit_message_text(
                "🎪 Афиша Джунгли Сити!\n\n"
                "У нас постоянно проходят интересные события:\n"
                "• Шоу-программы\n"
                "• Мастер-классы\n"
                "• Дискотеки\n"
                "• Праздничные мероприятия\n\n"
                "Спрашивайте, что будет на этих выходных! 🌟"
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
        # Ищем паттерн ID (числа, возможно с префиксом "id", "ид", "номер")
        # Regex ловит: "12345", "ID 12345", "ид: 12345", "мой номер 12345"
        # Исключаем простые короткие числа, если это не явно ID (чтобы не ловить "мне 2 билета")
        app_id_match = re.search(r'(?:id|ид|код|номер|^)\s*[:.\-]?\s*(\d{4,})', message_text, re.IGNORECASE)
        
        # Разрешаем просто числа от 4 знаков (например "16327") или явные ID с любым кол-вом цифр
        if app_id_match:
            app_id = app_id_match.group(1)
            
            # Отправляем уведомление менеджеру
            if MANAGER_CHAT_ID:
                try:
                    user_link = f"@{user.username}" if user.username else f"ID {user_id}"
                    msg_text = (
                        f"🔔 <b>Новый App ID для начисления баллов!</b>\n\n"
                        f"👤 Пользователь: {user.first_name} ({user_link})\n"
                        f"🔢 ID: <code>{app_id}</code>\n"
                        f"💬 Сообщение: {message_text}"
                    )
                    await context.bot.send_message(
                        chat_id=MANAGER_CHAT_ID,
                        text=msg_text,
                        parse_mode="HTML"
                    )
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
            current_lead = get_or_create_lead(user_id, source="telegram", park_id="nn", username=user.username)
            
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
        
        # Отправляем ответ пользователю
        await context.bot.send_message(chat_id=update.effective_chat.id, text=response)
        
        # Отправка уведомления менеджеру
        # Отправляем если: бот говорит "передал заявку" И ещё не отправляли
        if current_lead and not current_lead.sent_to_manager:
            # Проверяем, говорит ли бот что передал заявку
            if any(x in response.lower() for x in ["передал", "передаю заявку", "менеджер свяжется", "отдел праздников"]):
                logger.info(f"Bot confirmed booking for Lead #{current_lead.id}")
                
                # Извлекаем данные из ОТВЕТА бота (где он суммаризирует всё)
                final_data = agent.extract_lead_data(response, lead_data)
                
                # Сохраняем финальные данные в Lead
                current_lead = update_lead_from_data(current_lead.id, final_data)
                logger.info(f"Lead #{current_lead.id} final data: {lead_to_dict(current_lead)}")
                
                # Отправляем уведомление
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
