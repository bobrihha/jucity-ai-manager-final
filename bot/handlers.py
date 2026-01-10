"""Telegram Bot — обработчики сообщений."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from core import detect_intent, agent, rag, lead_collector
from db import SessionLocal, Session as DBSession, Message, Lead
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
        f"Добро пожаловать в Джунгли Сити, {user.first_name}! 🦁\n\n"
        "Здесь каждый день — приключение, а ваш ребёнок — главный герой джунглей!\n\n"
        "Я Джуси — ваш проводник по парку. С радостью помогу:\n"
        "• Узнать всё о парке и ценах\n"
        "• Организовать незабываемый день рождения\n"
        "• Рассказать о ближайших событиях\n\n"
        "Что вас интересует? 👇",
        reply_markup=reply_markup
    )


from core.utils import get_prices_from_knowledge

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
                "• Именинник — БЕСПЛАТНО\n"
                "• Взрослые — БЕСПЛАТНО\n"
                "• Безлимит на все аттракционы весь день\n\n"
                "Цены на билеты:\n"
                f"• Будни (вт-пт): {prices['weekday']} ₽\n"
                f"• Выходные: {prices['weekend']} ₽\n"
                f"• Понедельник: {prices['monday']} ₽\n\n"
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
            session = DBSession(telegram_id=user_id, park_id="nn")
            db.add(session)
            db.commit()
            db.refresh(session)
        
        # Сохраняем сообщение пользователя
        user_message = Message(session_id=session.id, role="user", content=message_text)
        db.add(user_message)
        db.commit()
        
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
            current_lead = get_or_create_lead(user_id, source="telegram", park_id="nn")
            
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
                msg_text = format_lead_message("telegram", user_id, lead_to_dict(current_lead))
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
