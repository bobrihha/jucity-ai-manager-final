"""
API для веб-чата на сайте.
Использует FastAPI для обработки сообщений.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging
import uuid
from datetime import datetime

from core.agent import Agent
from core.rag import RAGSystem
from core.intent_router import detect_intent
from db.database import SessionLocal
from db.models import Session as DBSession, Message
from core.lead_service import (
    get_or_create_lead,
    update_lead_from_data,
    mark_lead_sent_to_manager,
    lead_to_dict
)
from core.notifications import send_to_managers, format_lead_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Jungle City Chat API",
    description="API для чат-виджета на сайте nn.jucity.ru",
    version="1.0.0"
)

# CORS - разрешаем доступ с сайта
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://nn.jucity.ru",
        "https://www.nn.jucity.ru",
        "http://localhost:3000",  # для тестирования
        "http://localhost:8080",
        "*"  # временно для тестирования
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация компонентов
agent = Agent()
rag = RAGSystem()


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@app.get("/")
async def root():
    return {"status": "ok", "service": "Jungle City Chat API"}


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Основной endpoint для чата.
    Принимает сообщение и session_id, возвращает ответ бота.
    """
    try:
        db = SessionLocal()
        
        # Генерируем или используем существующий session_id
        session_id = request.session_id or f"web_{uuid.uuid4().hex[:12]}"
        
        # Ищем или создаём сессию
        session = db.query(DBSession).filter(
            DBSession.telegram_id == session_id
        ).first()
        
        if not session:
            session = DBSession(
                telegram_id=session_id,
                park_id="nn",
                intent="unknown"
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            logger.info(f"Created new web session: {session_id}")
        
        # Сохраняем сообщение пользователя
        user_message = Message(
            session_id=session.id,
            role="user",
            content=request.message
        )
        db.add(user_message)
        db.commit()
        
        # Определяем intent если ещё не определён
        if session.intent == "unknown":
            detected_result = detect_intent(request.message)
            # detect_intent возвращает IntentResult, извлекаем строку
            detected = detected_result.intent if hasattr(detected_result, 'intent') else str(detected_result)
            if detected != "unknown":
                session.intent = detected
                db.commit()
                logger.info(f"Detected intent: {detected}")
        
        # Получаем историю сообщений
        history = db.query(Message).filter(
            Message.session_id == session.id
        ).order_by(Message.id).all()
        
        history_list = [{"role": m.role, "content": m.content} for m in history]
        
        # Получаем RAG контекст
        rag_context = rag.get_context(request.message, session.intent)
        
        # Для birthday — работаем с Lead
        lead_data = {}
        current_lead = None
        
        if session.intent == "birthday":
            current_lead = get_or_create_lead(session_id, source="web", park_id="nn")
            extracted = agent.extract_lead_data(request.message, {})
            if extracted:
                current_lead = update_lead_from_data(current_lead.id, extracted)
            lead_data = lead_to_dict(current_lead)
        
        # Генерируем ответ
        response = agent.generate_response(
            message=request.message,
            intent=session.intent,
            rag_context=rag_context,
            history=history_list,
            lead_data=lead_data
        )
        
        # Сохраняем ответ бота
        bot_message = Message(
            session_id=session.id,
            role="assistant",
            content=response
        )
        db.add(bot_message)
        db.commit()
        
        # Отправляем уведомление менеджеру если нужно
        if current_lead and not current_lead.sent_to_manager:
            if any(x in response.lower() for x in ["передал", "передаю заявку", "менеджер свяжется", "отдел праздников"]):
                final_data = agent.extract_lead_data(response, lead_data)
                current_lead = update_lead_from_data(current_lead.id, final_data)
                msg_text = format_lead_message("web", session_id, lead_to_dict(current_lead))
                await send_to_managers(msg_text)
                mark_lead_sent_to_manager(current_lead.id)
                logger.info(f"Manager notification sent for Lead #{current_lead.id}")
        
        db.close()
        
        return ChatResponse(
            reply=response,
            session_id=session_id
        )
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
