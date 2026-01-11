"""VK Bot Handler — обработчик сообщений ВКонтакте."""

import asyncio
import logging
from vkbottle.bot import Bot, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text
import re

from core.agent import Agent
from core.rag import RAGSystem
from core.intent_router import detect_intent
from db.database import SessionLocal
from db.models import Session as DBSession, Message as DBMessage

logger = logging.getLogger(__name__)

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


def create_vk_bot(token: str, group_id: int):
    """Создать и настроить VK бота."""
    bot = Bot(token=token)
    
    # Инициализируем агента и RAG
    agent = Agent()
    rag = RAGSystem(park_id="nn")
    
    # Клавиатура для старта
    start_keyboard = (
        Keyboard(one_time=False, inline=False)
        .add(Text("🎟 Узнать о парке"), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(Text("🎉 Организовать праздник"), color=KeyboardButtonColor.POSITIVE)
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
        
        await message.answer(
            "Отлично! 🎢\n\n"
            "Спрашивайте что угодно о парке:\n"
            "• Цены и режим работы\n"
            "• Аттракционы и развлечения\n"
            "• Скидки и акции\n"
            "• Как добраться\n\n"
            "Я с удовольствием помогу! 😊"
        )
    
    @bot.on.message(text="🎉 Организовать праздник")
    async def birthday_handler(message: Message):
        """Переключение на birthday intent."""
        db = SessionLocal()
        try:
            session = get_or_create_session(db, message.from_id, "vk")
            session.intent = "birthday"
            session.lead_data = {}
            db.commit()
        finally:
            db.close()
        
        await message.answer(
            "💜💚 Отлично! День рождения в Джунглях — это радость и вау-эмоции! 💚💜\n\n"
            "У нас есть 2 формата праздника — выбирайте, что подойдёт именно вам\n\n"
            "🏠 ТЕМАТИЧЕСКАЯ КОМНАТА (3 часа)\n"
            "— оплачиваются 6 детских билетов\n"
            "— от 7 детей — ИМЕНИННИК БЕСПЛАТНО\n"
            "— безлимит на аттракционы 💚\n\n"
            "🍰 Столик в ресторане\n"
            "— без ограничения по времени\n"
            "— именинник — скидка 50% на вход\n"
            "— безлимит на аттракционы 💚\n\n"
            "✨ Аниматоры, торт, шары, аквагрим — по желанию.\n"
            "Давайте подберем идеальный вариант для вас!\n\n"
            "📅 На какую дату планируете праздник?"
        )
    
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
        
        await message.answer(
            "🎪 Афиша Джунгли Сити!\n\n"
            "У нас постоянно проходят интересные события:\n"
            "• Шоу-программы\n"
            "• Мастер-классы\n"
            "• Дискотеки\n"
            "• Праздничные мероприятия\n\n"
            "Спрашивайте, что будет на этих выходных! 🌟"
        )
    
    @bot.on.message()
    async def message_handler(message: Message):
        """Обработка всех текстовых сообщений."""
        if not message.text:
            return
        
        message_text = message.text.strip()
        user_id = message.from_id
        
        db = SessionLocal()
        try:
            # Получаем или создаём сессию
            session = get_or_create_session(db, user_id, "vk")
            
            # Сохраняем сообщение пользователя
            user_msg = DBMessage(session_id=session.id, role="user", content=message_text)
            db.add(user_msg)
            db.commit()

            # --- НОВАЯ ЛОГИКА: Проверка на ID приложения ---
            app_id_match = re.search(r'(?:id|ид|код|номер|^)\s*[:.\-]?\s*(\d{4,})', message_text, re.IGNORECASE)
            
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
                
                # Извлекаем данные из сообщения пользователя
                extracted = agent.extract_lead_data(message_text, {})
                
                # Обновляем Lead в БД
                if extracted:
                    current_lead = update_lead_from_data(current_lead.id, extracted)
                    logger.info(f"Lead #{current_lead.id} updated with: {extracted}")
                
                # Формируем lead_data для передачи в agent
                lead_data = lead_to_dict(current_lead)
            
            # Генерируем ответ
            response = agent.generate_response(
                message=message_text,
                intent=session.intent,
                history=history,
                rag_context=rag_context,
                lead_data=lead_data
            )
            
            # Сохраняем ответ
            assistant_msg = DBMessage(session_id=session.id, role="assistant", content=response)
            db.add(assistant_msg)
            db.commit()
            
            # Отправляем ответ (VK лимит 4096 символов)
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await message.answer(response[i:i+4000])
            else:
                await message.answer(response)
            
            # Отправка уведомления менеджеру (после ответа пользователю)
            # Отправляем если: бот говорит "передал заявку" И ещё не отправляли
            if current_lead and not current_lead.sent_to_manager:
                # Проверяем, что бот подтвердил бронь в ответе
                if any(x in response.lower() for x in ["передал", "передаю заявку", "менеджер свяжется", "отдел праздников"]):
                    logger.info(f"Bot confirmed booking for Lead #{current_lead.id}")
                    
                    # Извлекаем данные из ОТВЕТА бота (где он суммаризирует всё)
                    final_data = agent.extract_lead_data(response, lead_data)
                    
                    # Сохраняем финальные данные в Lead
                    current_lead = update_lead_from_data(current_lead.id, final_data)
                    logger.info(f"Lead #{current_lead.id} final data: {lead_to_dict(current_lead)}")
                    
                    # Отправляем уведомление
                    msg_text = format_lead_message("vk", str(user_id), lead_to_dict(current_lead))
                    await send_to_managers(msg_text)
                    
                    # Помечаем как отправленный
                    mark_lead_sent_to_manager(current_lead.id)
                    logger.info(f"Manager notification sent for Lead #{current_lead.id}!")
                
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
    bot = create_vk_bot(token, group_id)
    logger.info(f"VK Bot starting for group {group_id}...")
    await bot.run_polling()


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
