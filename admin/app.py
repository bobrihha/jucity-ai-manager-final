"""Streamlit Admin Panel — управление базой знаний."""

import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from datetime import datetime
import os

from db import init_db, SessionLocal, Document, Lead, Session as DBSession, Message, BotCommand
from core.rag import RAGSystem

# Инициализация
init_db()

st.set_page_config(
    page_title="Джунгли Сити — Админка",
    page_icon="🐒",
    layout="wide"
)

# ============ АВТОРИЗАЦИЯ ============
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "jungle2026")  # Можно менять через .env

def check_password():
    """Проверка пароля для доступа к админке."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if st.session_state.authenticated:
        return True
    
    st.title("🔐 Вход в админ-панель")
    st.write("Введите пароль для доступа:")
    
    password = st.text_input("Пароль", type="password", key="password_input")
    
    if st.button("Войти"):
        if password == ADMIN_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Неверный пароль!")
    
    return False

# Проверяем авторизацию
if not check_password():
    st.stop()

# ============ ОСНОВНОЙ ИНТЕРФЕЙС ============
st.title("🐒 Джунгли Сити — Админ-панель")

# Кнопка выхода
if st.sidebar.button("🚪 Выйти"):
    st.session_state.authenticated = False
    st.rerun()

# Сайдбар для навигации
page = st.sidebar.selectbox(
    "Раздел",
    ["📚 База знаний", "🤖 Команды бота", "💬 Диалоги", "🎯 Заявки", "⚙️ Настройки"]
)


# ============ БАЗА ЗНАНИЙ ============
if page == "📚 База знаний":
    st.header("📚 База знаний")
    
    tab1, tab2, tab3 = st.tabs(["Документы", "Добавить", "Переиндексация"])
    
    with tab1:
        st.subheader("Существующие документы")
        
        db = SessionLocal()
        docs = db.query(Document).order_by(Document.category, Document.title).all()
        db.close()
        
        if docs:
            for doc in docs:
                with st.expander(f"[{doc.category}] {doc.title}"):
                    st.text_area("Содержимое", doc.content, height=200, key=f"doc_{doc.id}", disabled=True)
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✏️ Редактировать", key=f"edit_{doc.id}"):
                            st.session_state[f"editing_{doc.id}"] = True
                    with col2:
                        if st.button("🗑️ Удалить", key=f"del_{doc.id}"):
                            db = SessionLocal()
                            db.query(Document).filter(Document.id == doc.id).delete()
                            db.commit()
                            db.close()
                            st.rerun()
        else:
            st.info("Документы пока не добавлены. Перейдите на вкладку 'Добавить'.")
    
    with tab2:
        st.subheader("Добавить документ")
        
        with st.form("add_document"):
            title = st.text_input("Название документа")
            category = st.selectbox("Категория", ["general", "birthday", "shared"])
            content = st.text_area("Содержимое", height=300)
            
            submitted = st.form_submit_button("💾 Сохранить")
            
            if submitted and title and content:
                db = SessionLocal()
                doc = Document(
                    title=title,
                    category=category,
                    content=content,
                    park_id="nn"
                )
                db.add(doc)
                db.commit()
                db.close()
                
                st.success(f"Документ '{title}' добавлен!")
                st.rerun()
    
    with tab3:
        st.subheader("🎪 Обновить афишу с сайта")
        st.write("Загрузить актуальные события с сайта jucity.ru")
        
        if st.button("🔄 Загрузить афишу"):
            with st.spinner("Загружаю события с сайта..."):
                try:
                    from core.afisha_scraper import save_afisha_to_knowledge, scrape_afisha
                    content = save_afisha_to_knowledge("nn")
                    st.success("✅ Афиша обновлена!")
                    st.text_area("Загруженные события", content, height=300)
                except Exception as e:
                    st.error(f"Ошибка: {e}")
        
        st.divider()
        st.subheader("Переиндексация RAG")
        st.write("Обновить векторный индекс для поиска по базе знаний.")
        
        if st.button("🔄 Переиндексировать"):
            with st.spinner("Индексация..."):
                rag = RAGSystem(park_id="nn")
                rag.clear()
                
                # Индексируем из БД
                db = SessionLocal()
                docs = db.query(Document).all()
                
                for doc in docs:
                    rag.add_document(
                        doc_id=f"db_{doc.id}",
                        content=doc.content,
                        category=doc.category,
                        title=doc.title
                    )
                
                # Плюс файлы из knowledge/
                file_count = rag.index_knowledge_files()
                
                db.close()
                
            st.success(f"Проиндексировано: {len(docs)} документов из БД + {file_count} файлов")


# ============ КОМАНДЫ БОТА ============
elif page == "🤖 Команды бота":
    st.header("🤖 Управление командами бота")
    
    tab1, tab2 = st.tabs(["Список команд", "Добавить команду"])
    
    with tab1:
        st.subheader("Активные команды")
        
        db = SessionLocal()
        commands = db.query(BotCommand).order_by(BotCommand.order, BotCommand.command).all()
        
        if commands:
            for cmd in commands:
                status_icon = "🟢" if cmd.is_active else "🔴"
                logic_icon = "⚙️" if cmd.has_logic else "📄"
                
                with st.expander(f"{status_icon} {cmd.command} — {cmd.title} ({logic_icon})"):
                    with st.form(f"edit_cmd_{cmd.id}"):
                        new_title = st.text_input("Название (в меню)", value=cmd.title)
                        new_response = st.text_area("Ответ (HTML)", value=cmd.response or "", height=150)
                        new_order = st.number_input("Порядок", value=cmd.order, step=1)
                        new_is_active = st.checkbox("Активна", value=cmd.is_active)
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("💾 Сохранить"):
                                cmd.title = new_title
                                cmd.response = new_response
                                cmd.order = new_order
                                cmd.is_active = new_is_active
                                db.commit()
                                st.success("Обновлено!")
                                st.rerun()
                        
                        with col2:
                            if st.form_submit_button("🗑️ Удалить"):
                                db.delete(cmd)
                                db.commit()
                                st.warning("Команда удалена!")
                                st.rerun()
        else:
            st.info("Команд пока нет.")
        
        db.close()

    with tab2:
        st.subheader("Новая команда")
        
        with st.form("new_cmd_form"):
            new_command = st.text_input("Команда (без /)", help="Например: prices")
            new_title = st.text_input("Название (в меню)", help="Например: 💰 Цены")
            new_response = st.text_area("Ответ (HTML)", help="Текст ответа бота. Поддерживает HTML теги.")
            new_order = st.number_input("Порядок", value=0, step=1)
            
            submitted = st.form_submit_button("➕ Добавить команду")
            
            if submitted:
                if not new_command or not new_title:
                    st.error("Заполните команду и название!")
                else:
                    db = SessionLocal()
                    # Проверка уникальности
                    exists = db.query(BotCommand).filter(BotCommand.command == new_command).first()
                    if exists:
                        st.error("Такая команда уже есть!")
                        db.close()
                    else:
                        cmd = BotCommand(
                            command=new_command,
                            title=new_title,
                            response=new_response,
                            order=new_order,
                            is_active=True,
                            has_logic=False # Новые команды по умолчанию без спец. логики
                        )
                        db.add(cmd)
                        db.commit()
                        db.close()
                        st.success(f"Команда /{new_command} добавлена!")
                        st.rerun()
                        
    st.divider()
    st.info("💡 **Примечание:** Текст ответов обновляется мгновенно. Для обновления **меню** (кнопка слева от ввода) может потребоваться перезапуск бота или время.")


# ============ ДИАЛОГИ ============
elif page == "💬 Диалоги":
    st.header("💬 История диалогов")
    
    db = SessionLocal()
    sessions = db.query(DBSession).order_by(DBSession.updated_at.desc()).limit(50).all()
    
    if sessions:
        for session in sessions:
            intent_emoji = "🎉" if session.intent == "birthday" else "🎟" if session.intent == "general" else "❓"
            # Определяем источник по telegram_id
            source = "VK" if str(session.telegram_id).startswith("vk_") else "Telegram"
            user_id = session.telegram_id.replace("vk_", "") if source == "VK" else session.telegram_id
            
            with st.expander(f"{intent_emoji} {source}: {user_id} | {session.updated_at.strftime('%d.%m.%Y %H:%M')}"):
                messages = db.query(Message).filter(Message.session_id == session.id).order_by(Message.id).all()
                
                for msg in messages:
                    if msg.role == "user":
                        st.markdown(f"👤 **Пользователь:** {msg.content}")
                    else:
                        st.markdown(f"🐒 **Джулия:** {msg.content}")
                    st.divider()
                
                if session.lead_data:
                    st.json(session.lead_data)
    else:
        st.info("Диалогов пока нет.")
    
    db.close()


# ============ ЗАЯВКИ ============
elif page == "🎯 Заявки":
    st.header("🎯 Заявки на праздники")
    
    db = SessionLocal()
    leads = db.query(Lead).order_by(Lead.created_at.desc()).all()
    
    if leads:
        for lead in leads:
            status_colors = {
                "new": "🔴",
                "contacted": "🟡", 
                "booked": "🟢",
                "cancelled": "⚫"
            }
            status_emoji = status_colors.get(lead.status, "⚪")
            
            with st.expander(f"{status_emoji} {lead.customer_name or 'Без имени'} | {lead.event_date or 'Дата не указана'}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"👤 **Контакт:** {lead.customer_name or '-'}")
                    st.write(f"📞 **Телефон:** {lead.phone or '-'}")
                    st.write(f"👶 **Именинник:** {lead.child_name or '-'} ({lead.child_age or '?'} лет)")
                
                with col2:
                    st.write(f"📅 **Дата:** {lead.event_date or '-'}")
                    st.write(f"👧 **Детей:** {lead.kids_count or '-'}")
                    st.write(f"👨 **Взрослых:** {lead.adults_count or '-'}")
                    st.write(f"📍 **Формат:** {lead.format or '-'}")
                
                # Изменение статуса
                new_status = st.selectbox(
                    "Статус",
                    ["new", "contacted", "booked", "cancelled"],
                    index=["new", "contacted", "booked", "cancelled"].index(lead.status),
                    key=f"status_{lead.id}"
                )
                
                if new_status != lead.status:
                    lead.status = new_status
                    db.commit()
                    st.success("Статус обновлён!")
                    st.rerun()
    else:
        st.info("Заявок пока нет.")
    
    db.close()


# ============ НАСТРОЙКИ ============
elif page == "⚙️ Настройки":
    st.header("⚙️ Настройки")
    
    st.subheader("Конфигурация парка")
    st.code("""
PARK_ID: nn
NAME: Джунгли Сити Нижний Новгород
PHONE: +7 (831) 213-50-50
WHATSAPP: +7 (962) 509-74-93
    """)
    
    st.subheader("Статус системы")
    
    # Проверяем подключения
    try:
        db = SessionLocal()
        session_count = db.query(DBSession).count()
        message_count = db.query(Message).count()
        doc_count = db.query(Document).count()
        db.close()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Сессий", session_count)
        col2.metric("Сообщений", message_count)
        col3.metric("Документов", doc_count)
        
        st.success("✅ База данных подключена")
    except Exception as e:
        st.error(f"❌ Ошибка БД: {e}")
    
    # Проверяем OpenAI
    import os
    if os.getenv("OPENAI_API_KEY"):
        st.success("✅ OpenAI API настроен")
    else:
        st.error("❌ OpenAI API ключ не найден")
    
    # Проверяем Telegram
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        st.success("✅ Telegram Bot Token настроен")
    else:
        st.error("❌ Telegram Bot Token не найден")


# Футер
st.sidebar.divider()
st.sidebar.caption("Джунгли Сити AI Bot v1.0")
