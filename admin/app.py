"""Streamlit Admin Panel — управление базой знаний."""

import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from datetime import datetime
import os

from db import init_db, SessionLocal, Document, Lead, Session as DBSession, Message, BotCommand, Client, ClientPhone, ClientChild
from core.rag import RAGSystem

# Инициализация
init_db()

st.set_page_config(
    page_title="Джунгли Сити — Админка",
    page_icon="🐒",
    layout="wide"
)

# ... (Auth logic remains same, skipping lines) ...

# Сайдбар для навигации
if "page_nav" not in st.session_state:
    st.session_state.page_nav = "🎯 Заявки"

def on_page_change():
    st.session_state.page_nav = st.session_state.page_selector

page = st.sidebar.selectbox(
    "Раздел",
    ["📚 База знаний", "🤖 Команды бота", "👥 Клиенты", "💬 Диалоги", "🎯 Заявки", "⚙️ Настройки"],
    key="page_selector",
    index=["📚 База знаний", "🤖 Команды бота", "👥 Клиенты", "💬 Диалоги", "🎯 Заявки", "⚙️ Настройки"].index(st.session_state.page_nav),
    on_change=on_page_change
)


# ... (Knowledge Base and Commands remain same) ...

# ============ КЛИЕНТЫ ============
if page == "👥 Клиенты":
    st.header("👥 База клиентов (CRM)")
    
    search_query = st.text_input("🔍 Поиск клиента (имя, телефон, username, ID)", "")
    
    db = SessionLocal()
    query = db.query(Client).order_by(Client.total_leads.desc())
    
    if search_query:
        search = f"%{search_query}%"
        query = query.filter(
            (Client.first_name.ilike(search)) |
            (Client.last_name.ilike(search)) |
            (Client.username.ilike(search)) |
            (Client.phone.ilike(search)) |
            (Client.telegram_id.ilike(search))
        )
    
    clients = query.limit(50).all()
    
    if clients:
        st.write(f"Найдено клиентов: {len(clients)}")
        for client in clients:
             # Имя для отображения
            display_name = f"{client.first_name or ''} {client.last_name or ''}".strip()
            if not display_name:
                display_name = f"@{client.username}" if client.username else f"ID {client.telegram_id}"
            
            with st.expander(f"👤 {display_name} | 📞 {client.phone or '-'} | Заявок: {client.total_leads}"):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("### 📋 Данные клиента")
                    st.write(f"**ID:** `{client.telegram_id}`")
                    st.write(f"**Username:** @{client.username}" if client.username else "**Username:** -")
                    st.write(f"**Имя:** {client.first_name or '-'}")
                    st.write(f"**Фамилия:** {client.last_name or '-'}")
                    st.write(f"**Телефон (осн):** {client.phone or '-'}")
                    
                    st.markdown("#### 📜 История телефонов")
                    phones = db.query(ClientPhone).filter(ClientPhone.client_id == client.id).all()
                    if phones:
                        for p in phones:
                            st.write(f"- {p.phone} (был {p.last_used_at.strftime('%d.%m.%Y')})")
                    else:
                        st.write("Нет дополнительных телефонов")
                        
                with c2:
                    st.markdown("### 👶 Дети")
                    children = db.query(ClientChild).filter(ClientChild.client_id == client.id).all()
                    if children:
                        for child in children:
                            st.write(f"- 👶 **{child.name}** {f'({child.age} лет)' if child.age else ''}")
                    else:
                        st.write("Нет данных о детях")
                        
                    st.markdown("### 📊 Статистика")
                    st.metric("Всего заявок", client.total_leads)
                    
                    if st.button("💬 Переписка", key=f"chat_cl_{client.id}"):
                        st.session_state.filter_user_id = client.telegram_id
                        st.session_state.page_nav = "💬 Диалоги"
                        st.rerun()

                st.divider()
                st.markdown("### 📅 История заявок")
                client_leads = db.query(Lead).filter(Lead.client_id == client.id).order_by(Lead.created_at.desc()).all()
                if client_leads:
                    for l in client_leads:
                        status_em = {"new": "🔴", "contacted": "🟡", "booked": "🟢", "cancelled": "⚫"}.get(l.status, "⚪")
                        st.write(f"{status_em} **{l.event_date or '?'}** — {l.format or '-'} ({l.kids_count} дет.)")
                else:
                    st.write("Заявок в истории не найдено (возможно, старые не привязались).")

    else:
        st.info("Клиенты не найдены.")
    
    db.close()


# ============ ДИАЛОГИ ============
elif page == "💬 Диалоги":
    st.header("💬 История диалогов")
    
    # Фильтр по ID
    filter_id = st.text_input("🔍 Поиск по ID (VK или Telegram)", value=st.session_state.get("filter_user_id", ""))
    
    if st.button("Сбросить фильтр"):
        st.session_state.filter_user_id = ""
        st.rerun()
    
    db = SessionLocal()
    
    query = db.query(DBSession).order_by(DBSession.updated_at.desc())
    
    if filter_id:
        # Ищем по telegram_id (частичное совпадение)
        query = query.filter(DBSession.telegram_id.contains(filter_id))
    
    sessions = query.limit(50).all()
    
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
        st.info("Диалогов не найдено.")
    
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
            
            # Определяем источник и создаем ссылку
            source_icon = "📱"
            user_link = "#"
            if lead.source == "vk" or str(lead.telegram_id).startswith("vk_"):
                vk_id = str(lead.telegram_id).replace("vk_", "")
                user_link = f"https://vk.com/id{vk_id}"
                source_icon = "🔵 VK"
            else:
                if lead.username:
                    user_link = f"https://t.me/{lead.username}"
                    source_icon = "✈️ TG"
                else:
                    user_link = f"tg://user?id={lead.telegram_id}"
                    source_icon = "✈️ TG (ID)"

            with st.expander(f"{status_emoji} {lead.customer_name or 'Без имени'} | {lead.event_date or 'Дата не указана'}"):
                
                # --- БЛОК 1: Основные действия ---
                col_act1, col_act2, col_act3 = st.columns([1, 1, 2])
                with col_act1:
                    st.markdown(f"**[{source_icon} Профиль]({user_link})**")
                with col_act2:
                    if st.button("📜 Переписка", key=f"hist_{lead.id}"):
                        st.session_state.filter_user_id = lead.telegram_id
                        st.session_state.page_nav = "💬 Диалоги"
                        st.rerun()
                
                st.divider()

                # --- БЛОК 2: Редактирование данных ---
                with st.form(key=f"lead_form_{lead.id}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        new_name = st.text_input("Имя клиента", value=lead.customer_name or "")
                        new_phone = st.text_input("Телефон", value=lead.phone or "")
                        new_child = st.text_input("Имя именинника", value=lead.child_name or "")
                        new_age = st.number_input("Возраст", value=lead.child_age or 0, step=1)
                    
                    with c2:
                        new_date = st.text_input("Дата праздника", value=lead.event_date or "")
                        new_kids = st.number_input("Детей", value=lead.kids_count or 0, step=1)
                        new_adults = st.number_input("Взрослых", value=lead.adults_count or 0, step=1)
                        new_format = st.text_input("Формат", value=lead.format or "")
                    
                    st.markdown("**Дополнительно:**")
                    new_notes = st.text_area("Комментарий / Заметки", value=lead.notes or "", height=100)
                    
                    # Статус внутри формы
                    new_status = st.selectbox(
                        "Статус заявки",
                        ["new", "contacted", "booked", "cancelled"],
                        index=["new", "contacted", "booked", "cancelled"].index(lead.status)
                    )
                    
                    if st.form_submit_button("💾 Сохранить изменения"):
                        lead.customer_name = new_name
                        lead.phone = new_phone
                        lead.child_name = new_child
                        lead.child_age = new_age
                        lead.event_date = new_date
                        lead.kids_count = new_kids
                        lead.adults_count = new_adults
                        lead.format = new_format
                        lead.notes = new_notes
                        lead.status = new_status
                        
                        db.commit()
                        st.success("Данные обновлены!")
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
