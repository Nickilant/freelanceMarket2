#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Freelance Bot с CryptoBot интеграцией
Функционал:
- Регистрация заказчиков и исполнителей
- Размещение заказов с оплатой в криптовалюте (TON/USDT)
- Эскроу система через CryptoBot
- Комиссия сервиса 5%
- Система тикетов для разрешения споров
- Админ-панель для управления
"""

import logging
import sqlite3
import json
import asyncio
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass
import hashlib
import os
from dotenv import load_dotenv
import hmac


from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)


load_dotenv()
# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.getenv('BOT_TOKEN')
CRYPTOBOT_TOKEN = os.getenv('CRYPTOBOT_TOKEN')
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x]
SERVICE_FEE = int(os.getenv('SERVICE_FEE', '5'))

# Поддерживаемые криптовалюты
SUPPORTED_CURRENCIES = ["TON", "USDT"]

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================
class UserRole(Enum):
    """Роли пользователей"""
    CUSTOMER = "customer"
    FREELANCER = "freelancer"
    BOTH = "both"

class OrderStatus(Enum):
    """Статусы заказов"""
    OPEN = "open"                           # Открыт для откликов
    IN_PROGRESS = "in_progress"             # Исполнитель выбран, работает
    WORK_COMPLETED = "work_completed"       # Исполнитель заявил о выполнении
    AWAITING_PAYMENT = "awaiting_payment"   # Ожидает оплаты от заказчика
    PAYMENT_RECEIVED = "payment_received"   # Оплата получена, работа передается
    WORK_DELIVERED = "work_delivered"       # Работа передана заказчику
    NEEDS_REVISION = "needs_revision"       # Нужны доработки
    PENDING_PAYOUT = "pending_payout"       # Ожидает выплаты исполнителю
    COMPLETED = "completed"                 # Завершен, деньги получены
    CANCELLED = "cancelled"                 # Отменен
    DISPUTED = "disputed"                   # Спор

class ResponseStatus(Enum):
    """Статусы откликов"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

class PaymentStatus(Enum):
    """Статусы платежей"""
    PENDING = "pending"
    PAID = "paid"
    COMPLETED = "completed"
    REFUNDED = "refunded"

class TicketStatus(Enum):
    """Статусы тикетов"""
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    CLOSED = "closed"

# Состояния для ConversationHandler
(CHOOSING_ROLE, CUSTOMER_NAME, CUSTOMER_COMPANY, CUSTOMER_DESCRIPTION,
 FREELANCER_NAME, FREELANCER_SKILLS, FREELANCER_PORTFOLIO, FREELANCER_RATE,
 ORDER_TITLE, ORDER_DESCRIPTION, ORDER_BUDGET, ORDER_CATEGORY, ORDER_SUBCATEGORY,
 ORDER_CURRENCY, ORDER_DEADLINE, RESPONSE_DESCRIPTION, RESPONSE_PRICE, RESPONSE_TIMELINE,
 TICKET_DESCRIPTION, WORK_DELIVERY, REVIEW_COMMENT) = range(21)

# Ограничения
MAX_ACTIVE_RESPONSES = 5
MAX_RESPONSES_PER_ORDER = 10

CATEGORIES = {
    "dev": {
        "name": "💻 Разработка",
        "subcategories": {
            "websites": "🌐 Сайты",
            "bots": "🤖 Боты и автоматизация",
            "mobile": "📱 Мобильные приложения",
            "desktop": "🖥 Десктопные приложения",
            "backend": "⚙️ Backend разработка",
            "frontend": "🎨 Frontend разработка",
            "blockchain": "⛓ Blockchain",
            "game": "🎮 Игры"
        }
    },
    "design": {
        "name": "🎨 Дизайн",
        "subcategories": {
            "logo": "🎯 Логотип и брендинг",
            "ui_ux": "📐 UI/UX дизайн",
            "web_design": "🌈 Веб-дизайн",
            "graphic": "🖼 Графический дизайн",
            "illustration": "✏️ Иллюстрации",
            "3d": "🎭 3D моделирование",
            "animation": "🎬 Анимация",
            "print": "📄 Печатный дизайн"
        }
    },
    "marketing": {
        "name": "📢 Маркетинг",
        "subcategories": {
            "smm": "📱 SMM",
            "context": "🎯 Контекстная реклама",
            "target": "🎪 Таргетированная реклама",
            "email": "📧 Email-маркетинг",
            "strategy": "📊 Маркетинговая стратегия",
            "analytics": "📈 Аналитика",
            "pr": "📰 PR",
            "influence": "⭐ Инфлюенс-маркетинг"
        }
    },
    "copywriting": {
        "name": "✍️ Копирайтинг",
        "subcategories": {
            "articles": "📝 Статьи",
            "seo_texts": "🔍 SEO-тексты",
            "commercial": "💼 Коммерческие тексты",
            "technical": "⚙️ Технические тексты",
            "translate": "🌍 Переводы",
            "scripts": "🎬 Сценарии",
            "naming": "🏷 Нейминг",
            "reviews": "⭐ Отзывы"
        }
    },
    "seo": {
        "name": "🔍 SEO и трафик",
        "subcategories": {
            "seo_audit": "🔎 SEO-аудит",
            "seo_promo": "📈 SEO-продвижение",
            "link_building": "🔗 Линкбилдинг",
            "content_seo": "📝 Контент для SEO",
            "local_seo": "📍 Локальное SEO",
            "ecommerce_seo": "🛒 SEO для e-commerce"
        }
    },
    "video": {
        "name": "🎥 Видео и аудио",
        "subcategories": {
            "video_editing": "✂️ Монтаж видео",
            "video_creating": "🎬 Создание видео",
            "animation_video": "🎞 Анимация",
            "voice": "🎙 Озвучка",
            "audio_editing": "🎵 Обработка аудио",
            "music": "🎼 Музыка",
            "sound_design": "🔊 Звуковой дизайн",
            "podcast": "📻 Подкасты"
        }
    },
    "business": {
        "name": "💼 Бизнес",
        "subcategories": {
            "consulting": "💡 Консалтинг",
            "business_plan": "📋 Бизнес-планы",
            "accounting": "💰 Бухгалтерия",
            "legal": "⚖️ Юридические услуги",
            "hr": "👥 HR",
            "management": "📊 Менеджмент",
            "sales": "🤝 Продажи",
            "crm": "📞 CRM"
        }
    },
    "other": {
        "name": "📦 Другое",
        "subcategories": {
            "data_entry": "⌨️ Ввод данных",
            "research": "🔬 Исследования",
            "teaching": "👨‍🏫 Обучение",
            "virtual_assistant": "🤵 Виртуальный ассистент",
            "customer_support": "💬 Поддержка клиентов",
            "other_tasks": "📌 Прочее"
        }
    }
}

# Заказов на страницу при навигации
ORDERS_PER_PAGE = 2

# ==================== CRYPTOBOT API ====================
import aiohttp

class CryptoBot:
    """Класс для работы с CryptoBot API"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://testnet-pay.crypt.bot/api"
        self.headers = {
            "Crypto-Pay-API-Token": token
        }
    
    async def create_invoice(self, amount: float, currency: str, 
                           description: str, payload: str) -> Optional[Dict]:
        """Создать инвойс для оплаты"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/createInvoice"
                data = {
                    "amount": str(amount),
                    "currency_type": "crypto",
                    "asset": currency,
                    "description": description,
                    "payload": payload,
                    "paid_btn_name": "callback",
                    "paid_btn_url": "https://t.me/your_bot"
                }
                
                async with session.post(url, headers=self.headers, json=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('ok'):
                            return result.get('result')
                    logger.error(f"CryptoBot API error: {await resp.text()}")
                    return None
        except Exception as e:
            logger.error(f"CryptoBot create_invoice error: {e}")
            return None
    
    async def get_invoice(self, invoice_id: int) -> Optional[Dict]:
        """Получить информацию об инвойсе"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/getInvoices"
                params = {"invoice_ids": str(invoice_id)}
                
                async with session.get(url, headers=self.headers, params=params) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('ok') and result.get('result', {}).get('items'):
                            return result['result']['items'][0]
                    return None
        except Exception as e:
            logger.error(f"CryptoBot get_invoice error: {e}")
            return None

    async def transfer(self, user_id: int, amount: float,
                       currency: str, spend_id: str) -> Optional[Dict]:
        """Перевести средства пользователю"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/transfer"
                data = {
                    "user_id": user_id,
                    "amount": str(amount),
                    "asset": currency,
                    "spend_id": spend_id
                }

                async with session.post(url, headers=self.headers, json=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('ok'):
                            return result.get('result')
                    logger.error(f"CryptoBot transfer error: {await resp.text()}")
                    return None
        except Exception as e:
            logger.error(f"CryptoBot transfer error: {e}")
            return None
    
    async def get_balance(self) -> Optional[Dict]:
        """Получить баланс бота"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/getBalance"
                
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('ok'):
                            return result.get('result')
                    return None
        except Exception as e:
            logger.error(f"CryptoBot get_balance error: {e}")
            return None

crypto_bot = CryptoBot(CRYPTOBOT_TOKEN)

# ==================== DATABASE ====================
class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_file: str = "freelance_bot.db"):
        self.db_file = db_file
        self.init_db()
    
    def get_connection(self):
        """Получить соединение с БД"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Инициализация базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                role TEXT NOT NULL,
                name TEXT NOT NULL,
                company TEXT,
                description TEXT,
                skills TEXT,
                portfolio TEXT,
                hourly_rate INTEGER,
                rating REAL DEFAULT 0,
                completed_orders INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Таблица заказов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                budget REAL NOT NULL,
                currency TEXT NOT NULL,
                deadline TEXT,
                category TEXT,
                subcategory TEXT,
                status TEXT NOT NULL,
                freelancer_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                payment_id INTEGER,
                FOREIGN KEY (customer_id) REFERENCES users (user_id),
                FOREIGN KEY (freelancer_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица откликов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS responses (
                response_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                freelancer_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                proposed_price REAL NOT NULL,
                proposed_timeline TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (order_id),
                FOREIGN KEY (freelancer_id) REFERENCES users (user_id),
                UNIQUE(order_id, freelancer_id)
            )
        ''')
        
        # Таблица платежей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                invoice_id INTEGER,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL,
                customer_id INTEGER NOT NULL,
                freelancer_id INTEGER NOT NULL,
                transfer_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (order_id)
            )
        ''')
        
        # Таблица тикетов поддержки
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                admin_id INTEGER,
                resolution TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (order_id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица отзывов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                rating INTEGER NOT NULL,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (order_id),
                FOREIGN KEY (from_user_id) REFERENCES users (user_id),
                FOREIGN KEY (to_user_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")
    
    # ===== ПОЛЬЗОВАТЕЛИ =====
    def create_user(self, user_id: int, username: str, role: str, **kwargs):
        """Создать пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        fields = ['user_id', 'username', 'role']
        values = [user_id, username, role]
        
        for key, value in kwargs.items():
            fields.append(key)
            values.append(value)
        
        placeholders = ', '.join(['?' for _ in values])
        query = f"INSERT INTO users ({', '.join(fields)}) VALUES ({placeholders})"
        
        cursor.execute(query, values)
        conn.commit()
        conn.close()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Получить пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def update_user(self, user_id: int, **kwargs):
        """Обновить данные пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [user_id]
        
        cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", values)
        conn.commit()
        conn.close()
    
    # ===== ЗАКАЗЫ =====
    def create_order(self, customer_id: int, title: str, description: str,
                     budget: float, currency: str, deadline: str,
                     category: str = None, subcategory: str = None) -> int:  # ДОБАВИТЬ
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO orders (customer_id, title, description, budget, 
                              currency, deadline, category, subcategory, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (customer_id, title, description, budget, currency,
              deadline, category, subcategory, OrderStatus.OPEN.value))  # ДОБАВИТЬ

        order_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return order_id

    def get_open_orders_by_category(self, category: str = None, subcategory: str = None,
                                    limit: int = 20, offset: int = 0) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()

        query = 'SELECT * FROM orders WHERE status = ?'
        params = [OrderStatus.OPEN.value]

        if category and category != 'all':
            query += ' AND category = ?'
            params.append(category)

        if subcategory and subcategory != 'all':
            query += ' AND subcategory = ?'
            params.append(subcategory)

        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def count_open_orders_by_category(self, category: str = None, subcategory: str = None) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()

        query = 'SELECT COUNT(*) as count FROM orders WHERE status = ?'
        params = [OrderStatus.OPEN.value]

        if category and category != 'all':
            query += ' AND category = ?'
            params.append(category)

        if subcategory and subcategory != 'all':
            query += ' AND subcategory = ?'
            params.append(subcategory)

        cursor.execute(query, params)
        count = cursor.fetchone()['count']
        conn.close()
        return count
    
    def get_order(self, order_id: int) -> Optional[Dict]:
        """Получить заказ"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_open_orders(self, limit: int = 20) -> List[Dict]:
        """Получить открытые заказы"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM orders 
            WHERE status = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (OrderStatus.OPEN.value, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_user_orders(self, user_id: int) -> List[Dict]:
        """Получить заказы пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM orders 
            WHERE customer_id = ? 
            ORDER BY created_at DESC
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def update_order_status(self, order_id: int, status: str, **kwargs):
        """Обновить статус заказа"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        updates = {'status': status}
        updates.update(kwargs)
        
        set_clause = ', '.join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values()) + [order_id]
        
        cursor.execute(f"UPDATE orders SET {set_clause} WHERE order_id = ?", values)
        conn.commit()
        conn.close()
    
    # ===== ОТКЛИКИ =====
    def create_response(self, order_id: int, freelancer_id: int, 
                       description: str, proposed_price: float, 
                       proposed_timeline: str) -> Optional[int]:
        """Создать отклик"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO responses 
                (order_id, freelancer_id, description, proposed_price, 
                 proposed_timeline, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (order_id, freelancer_id, description, proposed_price, 
                  proposed_timeline, ResponseStatus.PENDING.value))
            
            response_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return response_id
        except sqlite3.IntegrityError:
            conn.close()
            return None
    
    def get_response(self, response_id: int) -> Optional[Dict]:
        """Получить отклик"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM responses WHERE response_id = ?", (response_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_order_responses(self, order_id: int) -> List[Dict]:
        """Получить отклики на заказ"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM responses 
            WHERE order_id = ? 
            ORDER BY created_at ASC
        ''', (order_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_freelancer_active_responses(self, freelancer_id: int) -> List[Dict]:
        """Получить активные отклики фрилансера"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM responses 
            WHERE freelancer_id = ? AND status = ?
        ''', (freelancer_id, ResponseStatus.PENDING.value))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def update_response_status(self, response_id: int, status: str):
        """Обновить статус отклика"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE responses SET status = ? WHERE response_id = ?",
            (status, response_id)
        )
        conn.commit()
        conn.close()
    
    # ===== ПЛАТЕЖИ =====
    def create_payment(self, order_id: int, amount: float, currency: str,
                      customer_id: int, freelancer_id: int, 
                      invoice_id: Optional[int] = None) -> int:
        """Создать платеж"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO payments (order_id, invoice_id, amount, currency, 
                                status, customer_id, freelancer_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (order_id, invoice_id, amount, currency, 
              PaymentStatus.PENDING.value, customer_id, freelancer_id))
        
        payment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return payment_id
    
    def get_payment(self, payment_id: int) -> Optional[Dict]:
        """Получить платеж"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_payment_by_invoice(self, invoice_id: int) -> Optional[Dict]:
        """Получить платеж по invoice_id"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payments WHERE invoice_id = ?", (invoice_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def update_payment(self, payment_id: int, **kwargs):
        """Обновить платеж"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [payment_id]
        
        cursor.execute(f"UPDATE payments SET {set_clause} WHERE payment_id = ?", values)
        conn.commit()
        conn.close()
    
    # ===== ТИКЕТЫ =====
    def create_ticket(self, order_id: int, user_id: int, description: str) -> int:
        """Создать тикет"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO tickets (order_id, user_id, description, status)
            VALUES (?, ?, ?, ?)
        ''', (order_id, user_id, description, TicketStatus.OPEN.value))
        
        ticket_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return ticket_id
    
    def get_ticket(self, ticket_id: int) -> Optional[Dict]:
        """Получить тикет"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_open_tickets(self) -> List[Dict]:
        """Получить открытые тикеты"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM tickets 
            WHERE status IN (?, ?)
            ORDER BY created_at DESC
        ''', (TicketStatus.OPEN.value, TicketStatus.IN_REVIEW.value))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def update_ticket(self, ticket_id: int, **kwargs):
        """Обновить тикет"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [ticket_id]
        
        cursor.execute(f"UPDATE tickets SET {set_clause} WHERE ticket_id = ?", values)
        conn.commit()
        conn.close()
    
    # ===== ОТЗЫВЫ =====
    def create_review(self, order_id: int, from_user_id: int, 
                     to_user_id: int, rating: int, comment: str):
        """Создать отзыв"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO reviews (order_id, from_user_id, to_user_id, rating, comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, from_user_id, to_user_id, rating, comment))
        
        conn.commit()
        conn.close()
        
        self.recalculate_rating(to_user_id)
    
    def recalculate_rating(self, user_id: int):
        """Пересчитать средний рейтинг пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT AVG(rating) as avg_rating, COUNT(*) as count
            FROM reviews 
            WHERE to_user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        avg_rating = row['avg_rating'] if row['avg_rating'] else 0
        
        cursor.execute(
            "UPDATE users SET rating = ? WHERE user_id = ?",
            (avg_rating, user_id)
        )
        
        conn.commit()
        conn.close()

# Инициализация БД
db = Database()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id in ADMIN_IDS

def calculate_service_fee(amount: float) -> float:
    """Рассчитать комиссию сервиса"""
    return round(amount * SERVICE_FEE / 100, 2)

def calculate_freelancer_amount(total_amount: float) -> float:
    """Рассчитать сумму для фрилансера (без комиссии)"""
    return round(total_amount * (100 - SERVICE_FEE) / 100, 2)

def get_main_keyboard(user_role: str, user_id: int) -> ReplyKeyboardMarkup:
    """Получить главную клавиатуру"""
    keyboard = []
    
    if user_role in [UserRole.CUSTOMER.value, UserRole.BOTH.value]:
        keyboard.append(['📝 Создать заказ', '📋 Мои заказы'])
    
    if user_role in [UserRole.FREELANCER.value, UserRole.BOTH.value]:
        keyboard.append(['🔍 Найти заказы', '💼 Мои отклики'])
    
    keyboard.append(['👤 Профиль', 'ℹ️ Помощь'])
    
    if is_admin(user_id):
        keyboard.append(['⚙️ Админ-панель'])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def format_order_info(order: Dict, show_fee: bool = False, detailed: bool = False) -> str:
    """Форматировать информацию о заказе"""
    status_emoji = {
        OrderStatus.OPEN.value: "🟢",
        OrderStatus.IN_PROGRESS.value: "🟡",
        OrderStatus.WORK_COMPLETED.value: "✅",
        OrderStatus.AWAITING_PAYMENT.value: "💰",
        OrderStatus.PAYMENT_RECEIVED.value: "💸",
        OrderStatus.WORK_DELIVERED.value: "📦",
        OrderStatus.NEEDS_REVISION.value: "🔄",
        OrderStatus.PENDING_PAYOUT.value: "⏳",
        OrderStatus.COMPLETED.value: "✅",
        OrderStatus.CANCELLED.value: "❌",
        OrderStatus.DISPUTED.value: "⚠️"
    }
    
    status_text = {
        OrderStatus.OPEN.value: "Открыт",
        OrderStatus.IN_PROGRESS.value: "В работе",
        OrderStatus.WORK_COMPLETED.value: "Работа выполнена",
        OrderStatus.AWAITING_PAYMENT.value: "Ожидает оплаты",
        OrderStatus.PAYMENT_RECEIVED.value: "Оплачен",
        OrderStatus.WORK_DELIVERED.value: "Работа передана",
        OrderStatus.NEEDS_REVISION.value: "Нужны доработки",
        OrderStatus.PENDING_PAYOUT.value: "Ожидает выплаты",
        OrderStatus.COMPLETED.value: "Завершен",
        OrderStatus.CANCELLED.value: "Отменен",
        OrderStatus.DISPUTED.value: "Спор"
    }
    
    text = f"{status_emoji.get(order['status'], '⚪')} <b>{order['title']}</b>\n\n"
    
    budget = order['budget']
    currency = order['currency']
    
    if show_fee:
        fee = calculate_service_fee(budget)
        freelancer_amount = calculate_freelancer_amount(budget)
        text += f"💰 Бюджет заказчика: {budget} {currency}\n"
        text += f"💵 Вы получите: {freelancer_amount} {currency}\n"
        text += f"📊 Комиссия сервиса ({SERVICE_FEE}%): {fee} {currency}\n"
    else:
        text += f"💰 Бюджет: {budget} {currency}\n"
    
    text += f"📅 Срок: {order['deadline']}\n"
    if order.get('category') and order['category'] in CATEGORIES:
        cat_name = CATEGORIES[order['category']]['name']
        if order.get('subcategory'):
            subcat = CATEGORIES[order['category']]['subcategories'].get(order['subcategory'], '')
            if subcat:
                text += f"📂 Категория: {cat_name} → {subcat}\n"
        else:
            text += f"📂 Категория: {cat_name}\n"
    text += f"📊 Статус: {status_text.get(order['status'], order['status'])}\n"
    
    if detailed:
        text += f"\n📝 Описание:\n{order['description']}\n"
        text += f"\n🆔 ID заказа: {order['order_id']}\n"
        text += f"📆 Создан: {order['created_at'][:16]}"
    
    return text

def format_user_profile(user: Dict) -> str:
    """Форматировать профиль пользователя"""
    role_text = {
        UserRole.CUSTOMER.value: "👔 Заказчик",
        UserRole.FREELANCER.value: "💼 Исполнитель",
        UserRole.BOTH.value: "👔💼 Заказчик и Исполнитель"
    }
    
    text = f"<b>Профиль пользователя</b>\n\n"
    text += f"👤 Имя: {user['name']}\n"
    text += f"🎭 Роль: {role_text.get(user['role'], user['role'])}\n"
    
    if user['company']:
        text += f"🏢 Компания: {user['company']}\n"
    
    if user['skills']:
        text += f"🔧 Навыки: {user['skills']}\n"
    
    if user['hourly_rate']:
        text += f"💵 Ставка: {user['hourly_rate']} руб/час\n"
    
    text += f"⭐ Рейтинг: {user['rating']:.1f}/5.0\n"
    text += f"✅ Завершено заказов: {user['completed_orders']}\n"
    
    if user['description']:
        text += f"\n📝 О себе:\n{user['description']}\n"
    
    if user['portfolio']:
        text += f"\n🎨 Портфолио:\n{user['portfolio']}"
    
    return text

# ==================== КОМАНДЫ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start"""
    user = update.effective_user
    existing_user = db.get_user(user.id)
    
    if existing_user:
        await update.message.reply_text(
            f"С возвращением, {existing_user['name']}! 👋\n\n"
            "Используйте меню для навигации.",
            reply_markup=get_main_keyboard(existing_user['role'], user.id)
        )
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("👔 Заказчик", callback_data="role_customer")],
        [InlineKeyboardButton("💼 Исполнитель", callback_data="role_freelancer")],
        [InlineKeyboardButton("👔💼 Обе роли", callback_data="role_both")]
    ]
    
    await update.message.reply_text(
        "👋 Добро пожаловать в Freelance Bot!\n\n"
        "Платформа для размещения и поиска заказов на фриланс с оплатой в криптовалюте.\n\n"
        "🔐 Безопасная эскроу-система\n"
        "💎 Оплата в TON или USDT\n"
        f"📊 Комиссия сервиса: {SERVICE_FEE}%\n\n"
        "Для начала выберите вашу роль:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return CHOOSING_ROLE

async def choose_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора роли"""
    query = update.callback_query
    await query.answer()
    
    role = query.data.replace("role_", "")
    context.user_data['role'] = role
    
    role_text = {
        UserRole.CUSTOMER.value: "Заказчик",
        UserRole.FREELANCER.value: "Исполнитель",
        UserRole.BOTH.value: "Заказчик и Исполнитель"
    }
    
    await query.edit_message_text(
        f"Отлично! Вы выбрали роль: {role_text[role]}\n\n"
        "Давайте заполним ваш профиль.\n\n"
        "Как вас зовут? (ФИО или название компании)"
    )
    
    if role == UserRole.CUSTOMER.value:
        return CUSTOMER_NAME
    else:
        return FREELANCER_NAME

# ===== РЕГИСТРАЦИЯ ЗАКАЗЧИКА =====
async def customer_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Имя заказчика"""
    context.user_data['name'] = update.message.text
    
    await update.message.reply_text(
        "📝 Введите название вашей компании (или пропустите, написав /skip):"
    )
    
    return CUSTOMER_COMPANY

async def customer_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Компания заказчика"""
    if update.message.text != '/skip':
        context.user_data['company'] = update.message.text
    
    await update.message.reply_text(
        "📝 Расскажите немного о себе и сфере деятельности:"
    )
    
    return CUSTOMER_DESCRIPTION

async def customer_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Описание заказчика"""
    context.user_data['description'] = update.message.text
    user = update.effective_user
    
    db.create_user(
        user_id=user.id,
        username=user.username or "",
        role=context.user_data['role'],
        name=context.user_data['name'],
        company=context.user_data.get('company', ''),
        description=context.user_data['description']
    )
    
    await update.message.reply_text(
        "✅ Регистрация завершена!\n\n"
        "Теперь вы можете создавать заказы и нанимать исполнителей.",
        reply_markup=get_main_keyboard(context.user_data['role'], user.id)
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# ===== РЕГИСТРАЦИЯ ИСПОЛНИТЕЛЯ =====
async def freelancer_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Имя исполнителя"""
    context.user_data['name'] = update.message.text
    
    await update.message.reply_text(
        "🔧 Укажите ваши ключевые навыки (через запятую):\n\n"
        "Например: Python, Django, PostgreSQL, Docker"
    )
    
    return FREELANCER_SKILLS

async def freelancer_skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Навыки исполнителя"""
    context.user_data['skills'] = update.message.text
    
    await update.message.reply_text(
        "🎨 Добавьте ссылки на ваше портфолио или пропустите (/skip):"
    )
    
    return FREELANCER_PORTFOLIO

async def freelancer_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Портфолио исполнителя"""
    if update.message.text != '/skip':
        context.user_data['portfolio'] = update.message.text
    
    await update.message.reply_text(
        "💵 Укажите вашу почасовую ставку в рублях:\n\n"
        "Например: 2000"
    )
    
    return FREELANCER_RATE

async def freelancer_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ставка исполнителя"""
    try:
        rate = int(update.message.text)
        context.user_data['hourly_rate'] = rate
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число")
        return FREELANCER_RATE
    
    user = update.effective_user
    
    db.create_user(
        user_id=user.id,
        username=user.username or "",
        role=context.user_data['role'],
        name=context.user_data['name'],
        skills=context.user_data['skills'],
        portfolio=context.user_data.get('portfolio', ''),
        hourly_rate=context.user_data['hourly_rate']
    )
    
    await update.message.reply_text(
        "✅ Регистрация завершена!\n\n"
        "Теперь вы можете откликаться на заказы.",
        reply_markup=get_main_keyboard(context.user_data['role'], user.id)
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# ===== СОЗДАНИЕ ЗАКАЗА =====
async def create_order_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало создания заказа"""
    user = db.get_user(update.effective_user.id)
    
    if not user or user['role'] == UserRole.FREELANCER.value:
        await update.message.reply_text(
            "❌ Только заказчики могут создавать заказы."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📝 <b>Создание заказа</b>\n\n"
        "Введите название заказа:",
        parse_mode='HTML'
    )
    
    return ORDER_TITLE

async def order_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Название заказа"""
    context.user_data['order_title'] = update.message.text
    
    await update.message.reply_text(
        "📝 Опишите подробно, что нужно сделать:"
    )
    
    return ORDER_DESCRIPTION

async def order_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Описание заказа"""
    context.user_data['order_description'] = update.message.text
    
    await update.message.reply_text(
        "💰 Укажите бюджет (число):\n\n"
        "Например: 100"
    )
    
    return ORDER_BUDGET


async def order_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Бюджет заказа"""
    try:
        budget = float(update.message.text)
        context.user_data['order_budget'] = budget
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число")
        return ORDER_BUDGET

    # Показываем категории
    keyboard = []
    for cat_id, cat_data in CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(
            cat_data['name'],
            callback_data=f"cat_{cat_id}"
        )])

    await update.message.reply_text(
        "📂 Выберите категорию заказа:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return ORDER_CATEGORY


async def order_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор категории"""
    query = update.callback_query
    await query.answer()

    category = query.data.replace("cat_", "")
    context.user_data['order_category'] = category

    # Показываем подкатегории
    subcats = CATEGORIES[category]['subcategories']
    keyboard = []
    for subcat_id, subcat_name in subcats.items():
        keyboard.append([InlineKeyboardButton(
            subcat_name,
            callback_data=f"subcat_{subcat_id}"
        )])

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_categories")])

    await query.edit_message_text(
        f"📂 {CATEGORIES[category]['name']}\n\nВыберите подкатегорию:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return ORDER_SUBCATEGORY


async def order_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор подкатегории"""
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_categories":
        # Возврат к выбору категории
        keyboard = []
        for cat_id, cat_data in CATEGORIES.items():
            keyboard.append([InlineKeyboardButton(
                cat_data['name'],
                callback_data=f"cat_{cat_id}"
            )])

        await query.edit_message_text(
            "📂 Выберите категорию заказа:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ORDER_CATEGORY

    subcategory = query.data.replace("subcat_", "")
    context.user_data['order_subcategory'] = subcategory

    # Показываем валюты
    keyboard = [
        [InlineKeyboardButton("TON", callback_data="currency_TON")],
        [InlineKeyboardButton("USDT", callback_data="currency_USDT")]
    ]

    await query.edit_message_text(
        "💎 Выберите валюту для оплаты:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return ORDER_CURRENCY

async def order_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Валюта заказа"""
    query = update.callback_query
    await query.answer()
    
    currency = query.data.replace("currency_", "")
    context.user_data['order_currency'] = currency
    
    await query.edit_message_text(
        f"✅ Выбрана валюта: {currency}\n\n"
        "📅 Укажите срок выполнения:\n"
        "Например: 7 дней, До 15 марта, 2 недели"
    )
    
    return ORDER_DEADLINE


async def order_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Срок заказа"""
    context.user_data['order_deadline'] = update.message.text

    user = update.effective_user

    order_id = db.create_order(
        customer_id=user.id,
        title=context.user_data['order_title'],
        description=context.user_data['order_description'],
        budget=context.user_data['order_budget'],
        currency=context.user_data['order_currency'],
        deadline=context.user_data['order_deadline'],
        category=context.user_data.get('order_category'),  # ДОБАВЛЕНО
        subcategory=context.user_data.get('order_subcategory')  # ДОБАВЛЕНО
    )

    order = db.get_order(order_id)

    await update.message.reply_text(
        "✅ <b>Заказ успешно создан!</b>\n\n" +
        format_order_info(order, detailed=True) +
        "\n\n⚠️ Когда исполнитель будет выбран, вам нужно будет оплатить заказ.",
        parse_mode='HTML',
        reply_markup=get_main_keyboard(db.get_user(user.id)['role'], user.id)
    )

    context.user_data.clear()
    return ConversationHandler.END

# ===== ПРОСМОТР ЗАКАЗОВ =====
async def find_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Найти открытые заказы - выбор категории"""
    user = db.get_user(update.effective_user.id)

    if not user or user['role'] == UserRole.CUSTOMER.value:
        await update.message.reply_text("❌ Эта функция доступна только исполнителям.")
        return

    keyboard = [[InlineKeyboardButton("📋 Все", callback_data="browse_cat_all_0")]]
    for cat_id, cat_data in CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(cat_data['name'], callback_data=f"browse_cat_{cat_id}_0")])

    await update.message.reply_text(
        "🔍 <b>Поиск заказов</b>\n\nВыберите категорию:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def browse_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр заказов с выбором подкатегории"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split('_')
    category = parts[2]

    # Если это выбор категории - показываем подкатегории
    if len(parts) == 4 and parts[3] == '0' and category != 'all':
        subcats = CATEGORIES[category]['subcategories']
        keyboard = [[InlineKeyboardButton("📋 Все подкатегории", callback_data=f"browse_subcat_{category}_all_0")]]

        for subcat_id, subcat_name in subcats.items():
            keyboard.append([InlineKeyboardButton(
                subcat_name,
                callback_data=f"browse_subcat_{category}_{subcat_id}_0"
            )])

        keyboard.append([InlineKeyboardButton("◀️ К категориям", callback_data="back_to_cat_select")])

        await query.edit_message_text(
            f"📂 <b>{CATEGORIES[category]['name']}</b>\n\nВыберите подкатегорию:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Иначе показываем заказы
    page = int(parts[3])

    orders = db.get_open_orders_by_category(
        category=None if category == 'all' else category,
        limit=1,
        offset=page
    )

    total = db.count_open_orders_by_category(
        category=None if category == 'all' else category
    )

    if not orders:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_cat_select")]]
        await query.edit_message_text("😔 Заказов пока нет", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    order = orders[0]
    cat_name = CATEGORIES.get(category, {}).get('name', '📋 Все') if category != 'all' else "📋 Все"

    text = f"🔍 <b>{cat_name}</b>\n\n"
    text += f"Заказ {page + 1} из {total}\n\n"
    text += format_order_info(order, show_fee=True, detailed=True)

    keyboard = []
    row = []

    if page > 0:
        row.append(InlineKeyboardButton("◀️", callback_data=f"browse_cat_{category}_{page - 1}"))

    row.append(InlineKeyboardButton("✉️ Откликнуться", callback_data=f"respond_order_{order['order_id']}"))
    row.append(InlineKeyboardButton(f"{page + 1}/{total}", callback_data="page_info"))

    if page + 1 < total:
        row.append(InlineKeyboardButton("▶️", callback_data=f"browse_cat_{category}_{page + 1}"))

    keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_subcat_{category}")])

    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def back_to_subcat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Назад к подкатегориям"""
    query = update.callback_query
    await query.answer()

    category = query.data.split('_')[3]

    subcats = CATEGORIES[category]['subcategories']
    keyboard = [[InlineKeyboardButton("📋 Все подкатегории", callback_data=f"browse_subcat_{category}_all_0")]]

    for subcat_id, subcat_name in subcats.items():
        keyboard.append([InlineKeyboardButton(
            subcat_name,
            callback_data=f"browse_subcat_{category}_{subcat_id}_0"
        )])

    keyboard.append([InlineKeyboardButton("◀️ К категориям", callback_data="back_to_cat_select")])

    await query.edit_message_text(
        f"📂 <b>{CATEGORIES[category]['name']}</b>\n\nВыберите подкатегорию:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def browse_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр заказов по подкатегории"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split('_')
    category = parts[2]
    subcategory = parts[3]
    page = int(parts[4])

    orders = db.get_open_orders_by_category(
        category=category,
        subcategory=None if subcategory == 'all' else subcategory,
        limit=1,
        offset=page
    )

    total = db.count_open_orders_by_category(
        category=category,
        subcategory=None if subcategory == 'all' else subcategory
    )

    if not orders:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data=f"browse_cat_{category}_0")]]
        await query.edit_message_text("😔 Заказов пока нет", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    order = orders[0]
    cat_name = CATEGORIES[category]['name']
    subcat_name = CATEGORIES[category]['subcategories'].get(subcategory, 'Все') if subcategory != 'all' else 'Все'

    text = f"🔍 <b>{cat_name} → {subcat_name}</b>\n\n"
    text += f"Заказ {page + 1} из {total}\n\n"
    text += format_order_info(order, show_fee=True, detailed=True)

    keyboard = []
    row = []

    if page > 0:
        row.append(InlineKeyboardButton("◀️", callback_data=f"browse_subcat_{category}_{subcategory}_{page - 1}"))

    row.append(InlineKeyboardButton("✉️ Откликнуться", callback_data=f"respond_order_{order['order_id']}"))
    row.append(InlineKeyboardButton(f"{page + 1}/{total}", callback_data="page_info"))

    if page + 1 < total:
        row.append(InlineKeyboardButton("▶️", callback_data=f"browse_subcat_{category}_{subcategory}_{page + 1}"))

    keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"browse_cat_{category}_0")])

    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def back_to_cat_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к категориям"""
    query = update.callback_query
    await query.answer()

    keyboard = [[InlineKeyboardButton("📋 Все", callback_data="browse_cat_all_0")]]
    for cat_id, cat_data in CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(cat_data['name'], callback_data=f"browse_cat_{cat_id}_0")])

    await query.edit_message_text(
        "🔍 <b>Поиск заказов</b>\n\nВыберите категорию:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============= 9. ДОСТУПНЫЙ БАЛАНС ДЛЯ АДМИНА =============

async def admin_available_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать доступный баланс (за вычетом эскроу)"""
    query = update.callback_query
    await query.answer()

    if not is_admin(update.effective_user.id):
        await query.edit_message_text("❌ Нет прав")
        return

    balance = await crypto_bot.get_balance()

    if not balance:
        await query.edit_message_text("❌ Ошибка получения баланса")
        return

    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT p.currency, SUM(p.amount) as total
        FROM payments p
        JOIN orders o ON p.order_id = o.order_id
        WHERE p.status = 'paid'
        AND o.status NOT IN ('completed', 'cancelled', 'disputed')
        GROUP BY p.currency
    ''')

    frozen = {}
    for row in cursor.fetchall():
        frozen[row['currency']] = float(row['total']) if row['total'] else 0

    conn.close()

    text = "💰 <b>Баланс приложения</b>\n\n"

    for item in balance:
        currency = item['currency_code']
        total = float(item['available'])
        frozen_amount = frozen.get(currency, 0)
        available = total - frozen_amount

        text += f"<b>{currency}:</b>\n"
        text += f"  Всего: {total}\n"
        text += f"  На эскроу: {frozen_amount}\n"
        text += f"  ✅ <b>Доступно: {available}</b>\n\n"

    text += "ℹ️ Доступно = Баланс - Активные заказы"

    # ДОБАВИТЬ кнопку назад
    keyboard = [[InlineKeyboardButton("◀️ Админ-панель", callback_data="back_to_admin")]]

    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def view_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр заказа"""
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split('_')[2])
    order = db.get_order(order_id)

    if not order:
        await query.edit_message_text("❌ Заказ не найден")
        return

    customer = db.get_user(order['customer_id'])

    text = format_order_info(order, show_fee=True, detailed=True)
    text += f"\n\n👤 <b>Заказчик:</b>\n"
    text += f"Имя: {customer['name']}\n"
    if customer['company']:
        text += f"Компания: {customer['company']}\n"
    text += f"⭐ Рейтинг: {customer['rating']:.1f}/5.0"  # ДОБАВЛЕНО отображение рейтинга

    responses = db.get_order_responses(order_id)
    text += f"\n\n💬 Откликов: {len(responses)}"

    keyboard = []

    # Действия в зависимости от статуса
    if order['status'] == OrderStatus.OPEN.value:
        keyboard.append([InlineKeyboardButton(
            "✉️ Откликнуться",
            callback_data=f"respond_order_{order_id}"
        )])

    # ДОБАВИТЬ кнопку "Назад к откликам" если пришли из списка откликов
    if context.user_data.get('my_responses_list'):
        keyboard.append([InlineKeyboardButton("◀️ К моим откликам", callback_data="back_to_my_responses")])

    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )


async def back_to_my_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к списку откликов"""
    query = update.callback_query
    await query.answer()

    responses = context.user_data.get('my_responses_list')
    if not responses:
        # Загружаем заново
        user = db.get_user(query.from_user.id)
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*, o.title, o.budget, o.currency, o.status as order_status
            FROM responses r
            JOIN orders o ON r.order_id = o.order_id
            WHERE r.freelancer_id = ?
            ORDER BY r.created_at DESC
        ''', (query.from_user.id,))
        responses = [dict(row) for row in cursor.fetchall()]
        conn.close()
        context.user_data['my_responses_list'] = responses

    if responses:
        await show_my_response(query, context, 0)
    else:
        await query.edit_message_text("💼 У вас пока нет откликов.")


async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Мои заказы - ОДНА КАРТОЧКА"""
    user = db.get_user(update.effective_user.id)

    if not user or user['role'] == UserRole.FREELANCER.value:
        await update.message.reply_text("❌ У вас нет заказов")
        return

    orders = db.get_user_orders(update.effective_user.id)

    if not orders:
        await update.message.reply_text("📋 У вас пока нет заказов.\n\nСоздайте первый!")
        return

    context.user_data['my_orders_list'] = orders
    await show_my_order(update.message, context, 0)


async def show_my_order(msg, context: ContextTypes.DEFAULT_TYPE, index: int):
    """Показать один заказ"""
    orders = context.user_data.get('my_orders_list', [])
    if not orders or index < 0 or index >= len(orders):
        return

    order = orders[index]
    text = f"📋 <b>Заказ {index + 1} из {len(orders)}</b>\n\n"
    text += format_order_info(order, detailed=True)

    keyboard = []
    row = []

    if index > 0:
        row.append(InlineKeyboardButton("◀️", callback_data=f"my_order_{index - 1}"))

    row.append(InlineKeyboardButton("⚙️ Управление", callback_data=f"manage_order_{order['order_id']}"))

    if order['status'] == OrderStatus.OPEN.value:
        resp_count = len(db.get_order_responses(order['order_id']))
        row.append(InlineKeyboardButton(f"💬 ({resp_count})", callback_data=f"order_responses_{order['order_id']}"))

    row.append(InlineKeyboardButton(f"{index + 1}/{len(orders)}", callback_data="page_info"))

    if index + 1 < len(orders):
        row.append(InlineKeyboardButton("▶️", callback_data=f"my_order_{index + 1}"))

    keyboard.append(row)

    if hasattr(msg, 'edit_message_text'):
        await msg.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await msg.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def my_order_navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Навигация по моим заказам"""
    query = update.callback_query
    await query.answer()
    index = int(query.data.split('_')[2])
    await show_my_order(query, context, index)


async def manage_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление заказом"""
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split('_')[2])
    order = db.get_order(order_id)

    if not order:
        await query.edit_message_text("❌ Заказ не найден")
        return

    text = format_order_info(order, detailed=True)
    keyboard = []

    if order['status'] == OrderStatus.OPEN.value:
        responses = db.get_order_responses(order_id)
        keyboard.append([InlineKeyboardButton(
            f"💬 Отклики ({len(responses)})",
            callback_data=f"order_responses_{order_id}"
        )])

    elif order['status'] == OrderStatus.IN_PROGRESS.value:
        keyboard.append([
            InlineKeyboardButton(
                "❌ Отменить работу с исполнителем",
                callback_data=f"cancel_order_{order_id}"
            )
        ])
        if order['freelancer_id']:
            freelancer = db.get_user(order['freelancer_id'])
            text += f"\n\n👤 <b>Исполнитель:</b>\n{freelancer['name']}"
            text += f"\n💬 Контакт: @{freelancer['username'] or 'не указан'}"

    elif order['status'] == OrderStatus.WORK_COMPLETED.value:
        keyboard.append([
            InlineKeyboardButton(
                "💰 Оплатить заказ",
                callback_data=f"pay_order_{order_id}"
            )
        ])
        text += "\n\n⚠️ Исполнитель сообщил о завершении работы.\nОплатите заказ, чтобы получить результат."

    elif order['status'] == OrderStatus.PAYMENT_RECEIVED.value:
        text += "\n\n✅ Оплата получена!\nОжидайте передачи работы от исполнителя."

    elif order['status'] == OrderStatus.WORK_DELIVERED.value:
        keyboard.append([
            InlineKeyboardButton(
                "✅ Работа выполнена корректно",
                callback_data=f"approve_work_{order_id}"
            )
        ], [
            InlineKeyboardButton(
                "🔄 Нужны доработки",
                callback_data=f"request_revision_{order_id}"
            ),
            InlineKeyboardButton(
                "⚠️ Проблема",
                callback_data=f"dispute_order_{order_id}"
            )
        ])
        text += "\n\n📦 Работа передана! Проверьте результат."

    elif order['status'] == OrderStatus.NEEDS_REVISION.value:
        text += "\n\n🔄 Исполнитель работает над доработками."

    elif order['status'] == OrderStatus.PENDING_PAYOUT.value:
        text += "\n\n⏳ Ожидаем подтверждения получения оплаты от исполнителя."

    # ДОБАВИТЬ КНОПКУ "НАЗАД" В КОНЕЦ
    keyboard.append([InlineKeyboardButton("◀️ К моим заказам", callback_data="back_to_my_orders")])

    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )


async def back_to_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к списку моих заказов"""
    query = update.callback_query
    await query.answer()

    orders = context.user_data.get('my_orders_list')
    if not orders:
        # Если список потерян, загружаем заново
        user = db.get_user(query.from_user.id)
        orders = db.get_user_orders(query.from_user.id)
        context.user_data['my_orders_list'] = orders

    if orders:
        await show_my_order(query, context, 0)
    else:
        await query.edit_message_text("📋 У вас пока нет заказов.\n\nСоздайте первый!")


async def order_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр откликов с пагинацией"""
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split('_')[2])
    order = db.get_order(order_id)
    responses = db.get_order_responses(order_id)

    if not responses:
        await query.edit_message_text("💬 На этот заказ пока нет откликов.")
        return

    context.user_data['order_responses_list'] = responses
    context.user_data['current_order_id'] = order_id
    await show_order_response(query, context, 0)


async def show_order_response(msg, context: ContextTypes.DEFAULT_TYPE, index: int):
    """Показать один отклик"""
    responses = context.user_data.get('order_responses_list', [])
    order_id = context.user_data.get('current_order_id')

    if not responses or index < 0 or index >= len(responses):
        return

    response = responses[index]
    order = db.get_order(order_id)
    freelancer = db.get_user(response['freelancer_id'])

    text = f"💬 <b>Отклик {index + 1} из {len(responses)}</b>\n\n"
    text += f"👤 Исполнитель: {freelancer['name']}\n"
    text += f"⭐ Рейтинг: {freelancer['rating']:.1f}/5.0 ({freelancer['completed_orders']} заказов)\n"
    text += f"💰 Цена: {response['proposed_price']} {order['currency']}\n"
    text += f"📅 Срок: {response['proposed_timeline']}\n\n"
    text += f"📝 Описание:\n{response['description']}\n\n"
    text += f"🔧 Навыки: {freelancer['skills'] or 'не указаны'}"

    keyboard = []

    # Действия (если отклик в ожидании)
    if response['status'] == ResponseStatus.PENDING.value:
        action_row = [
            InlineKeyboardButton("✅ Принять", callback_data=f"accept_response_{response['response_id']}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_response_{response['response_id']}")
        ]
        keyboard.append(action_row)

    # Навигация
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"view_response_{index - 1}"))

    nav_row.append(InlineKeyboardButton(f"{index + 1}/{len(responses)}", callback_data="page_info"))

    if index + 1 < len(responses):
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"view_response_{index + 1}"))

    keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("◀️ К заказу", callback_data=f"manage_order_{order_id}")])

    if hasattr(msg, 'edit_message_text'):
        await msg.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await msg.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def view_response_navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Навигация по откликам"""
    query = update.callback_query
    await query.answer()
    index = int(query.data.split('_')[2])
    await show_order_response(query, context, index)

# ===== СОЗДАНИЕ ОТКЛИКА =====
async def respond_to_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало создания отклика"""
    query = update.callback_query
    await query.answer()
    
    order_id = int(query.data.split('_')[2])
    user = db.get_user(update.effective_user.id)
    
    order = db.get_order(order_id)
    if order['status'] != OrderStatus.OPEN.value:
        await query.edit_message_text("❌ Этот заказ уже недоступен для откликов.")
        return ConversationHandler.END
    
    active_responses = db.get_freelancer_active_responses(update.effective_user.id)
    if len(active_responses) >= MAX_ACTIVE_RESPONSES:
        await query.edit_message_text(
            f"❌ У вас уже {MAX_ACTIVE_RESPONSES} активных откликов.\n\n"
            "Дождитесь ответа по существующим откликам."
        )
        return ConversationHandler.END
    
    order_responses = db.get_order_responses(order_id)
    if len(order_responses) >= MAX_RESPONSES_PER_ORDER:
        await query.edit_message_text(
            "❌ На этот заказ уже максимальное количество откликов."
        )
        return ConversationHandler.END
    
    for resp in order_responses:
        if resp['freelancer_id'] == update.effective_user.id:
            await query.edit_message_text(
                "❌ Вы уже откликнулись на этот заказ."
            )
            return ConversationHandler.END
    
    context.user_data['response_order_id'] = order_id
    
    await query.edit_message_text(
        f"✉️ <b>Отклик на заказ:</b>\n{order['title']}\n\n"
        "Расскажите, почему вы подходите для этого заказа:",
        parse_mode='HTML'
    )
    
    return RESPONSE_DESCRIPTION

async def response_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Описание отклика"""
    context.user_data['response_description'] = update.message.text
    
    order = db.get_order(context.user_data['response_order_id'])
    
    await update.message.reply_text(
        f"💰 Укажите вашу цену в {order['currency']}:\n\n"
        f"Бюджет заказчика: {order['budget']} {order['currency']}"
    )
    
    return RESPONSE_PRICE

async def response_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Цена в отклике"""
    try:
        price = float(update.message.text)
        context.user_data['response_price'] = price
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число")
        return RESPONSE_PRICE
    
    await update.message.reply_text(
        "📅 В какой срок вы готовы выполнить заказ?"
    )
    
    return RESPONSE_TIMELINE

async def response_timeline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Срок в отклике"""
    context.user_data['response_timeline'] = update.message.text
    
    user = update.effective_user
    
    response_id = db.create_response(
        order_id=context.user_data['response_order_id'],
        freelancer_id=user.id,
        description=context.user_data['response_description'],
        proposed_price=context.user_data['response_price'],
        proposed_timeline=context.user_data['response_timeline']
    )
    
    if response_id:
        order = db.get_order(context.user_data['response_order_id'])
        
        await update.message.reply_text(
            "✅ Ваш отклик успешно отправлен!\n\n"
            "Заказчик получил уведомление и рассмотрит ваше предложение.",
            reply_markup=get_main_keyboard(db.get_user(user.id)['role'], user.id)
        )
        
        try:
            await context.bot.send_message(
                chat_id=order['customer_id'],
                text=f"🔔 <b>Новый отклик на ваш заказ!</b>\n\n"
                     f"Заказ: {order['title']}\n"
                     f"Исполнитель: {db.get_user(user.id)['name']}\n"
                     f"Цена: {context.user_data['response_price']} {order['currency']}\n\n"
                     f"Посмотрите все отклики в разделе 'Мои заказы'",
                parse_mode='HTML'
            )
        except:
            pass
    else:
        await update.message.reply_text(
            "❌ Ошибка при создании отклика."
        )
    
    context.user_data.clear()
    return ConversationHandler.END

# [ПРОДОЛЖЕНИЕ В СЛЕДУЮЩЕЙ ЧАСТИ - ПЛАТЕЖИ И АДМИНКА]

# ===== УПРАВЛЕНИЕ ОТКЛИКАМИ =====
async def accept_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принять отклик"""
    query = update.callback_query
    await query.answer()
    
    response_id = int(query.data.split('_')[2])
    response = db.get_response(response_id)
    order = db.get_order(response['order_id'])
    
    if order['customer_id'] != update.effective_user.id:
        await query.edit_message_text("❌ Это не ваш заказ")
        return
    
    # Обновляем статус отклика
    db.update_response_status(response_id, ResponseStatus.ACCEPTED.value)
    
    # Отклоняем остальные отклики
    all_responses = db.get_order_responses(order['order_id'])
    for resp in all_responses:
        if resp['response_id'] != response_id and resp['status'] == ResponseStatus.PENDING.value:
            db.update_response_status(resp['response_id'], ResponseStatus.REJECTED.value)
    
    # Обновляем заказ - переводим в работу (БЕЗ оплаты)
    db.update_order_status(
        order['order_id'],
        OrderStatus.IN_PROGRESS.value,
        freelancer_id=response['freelancer_id'],
        started_at=datetime.now().isoformat()
    )
    
    final_price = response['proposed_price']
    freelancer = db.get_user(response['freelancer_id'])
    
    await query.edit_message_text(
        f"✅ <b>Отклик принят!</b>\n\n"
        f"Исполнитель: {freelancer['name']}\n"
        f"Цена: {final_price} {order['currency']}\n"
        f"Срок: {response['proposed_timeline']}\n\n"
        f"📋 <b>Следующие шаги:</b>\n"
        f"1. Исполнитель начинает работу\n"
        f"2. После выполнения исполнитель сдает работу\n"
        f"3. Вы проверяете работу\n"
        f"4. Если все ОК - оплачиваете\n"
        f"5. Исполнитель получает средства\n\n"
        f"⚠️ <b>Важно:</b> Оплата происходит ПОСЛЕ сдачи и проверки работы.\n\n"
        f"💬 Свяжитесь с исполнителем: @{freelancer['username'] or 'не указан'}",
        parse_mode='HTML'
    )
    
    # Уведомляем исполнителя
    try:
        await context.bot.send_message(
            chat_id=response['freelancer_id'],
            text=f"🎉 <b>Ваш отклик принят!</b>\n\n"
                 f"Заказ: {order['title']}\n"
                 f"Цена: {final_price} {order['currency']}\n"
                 f"Срок: {response['proposed_timeline']}\n\n"
                 f"✅ Можете приступать к работе!\n\n"
                 f"📋 <b>Порядок работы:</b>\n"
                 f"1. Выполните работу\n"
                 f"2. Нажмите 'Сдать работу' в разделе 'Мои отклики'\n"
                 f"3. Заказчик проверит и оплатит\n"
                 f"4. Вы получите средства автоматически\n\n"
                 f"💬 Связаться с заказчиком: @{db.get_user(order['customer_id'])['username'] or 'не указан'}",
            parse_mode='HTML'
        )
    except:
        pass

async def reject_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отклонить отклик"""
    query = update.callback_query
    await query.answer()
    
    response_id = int(query.data.split('_')[2])
    response = db.get_response(response_id)
    order = db.get_order(response['order_id'])
    
    if order['customer_id'] != update.effective_user.id:
        await query.edit_message_text("❌ Это не ваш заказ")
        return
    
    db.update_response_status(response_id, ResponseStatus.REJECTED.value)
    
    await query.edit_message_text("✅ Отклик отклонен.")

async def cancel_order_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить работу и вернуть заказ в открытое состояние"""
    query = update.callback_query
    await query.answer()
    
    order_id = int(query.data.split('_')[3])
    order = db.get_order(order_id)
    
    if order['customer_id'] != update.effective_user.id:
        await query.edit_message_text("❌ Это не ваш заказ")
        return
    
    # Проверяем, что заказ можно отменить
    if order['status'] not in [OrderStatus.IN_PROGRESS.value, OrderStatus.AWAITING_PAYMENT.value]:
        await query.edit_message_text(
            f"❌ Нельзя отменить заказ в статусе '{order['status']}'"
        )
        return
    
    # Проверяем, что оплаты не было
    if order.get('payment_id'):
        payment = db.get_payment(order['payment_id'])
        if payment and payment['status'] != PaymentStatus.PENDING.value:
            await query.edit_message_text(
                "❌ Заказ уже оплачен. Для возврата создайте тикет."
            )
            return
    
    # Возвращаем все отклики в статус ожидания
    responses = db.get_order_responses(order_id)
    for resp in responses:
        if resp['status'] in [ResponseStatus.ACCEPTED.value, ResponseStatus.REJECTED.value]:
            db.update_response_status(resp['response_id'], ResponseStatus.PENDING.value)
    
    # Возвращаем заказ в открытое состояние
    db.update_order_status(
        order_id,
        OrderStatus.OPEN.value,
        freelancer_id=None,
        started_at=None
    )
    
    await query.edit_message_text(
        "✅ <b>Заказ возвращен в открытое состояние</b>\n\n"
        "Все отклики снова доступны для рассмотрения.\n"
        "Вы можете выбрать другого исполнителя.",
        parse_mode='HTML'
    )
    
    # Уведомляем бывшего исполнителя
    if order['freelancer_id']:
        try:
            await context.bot.send_message(
                chat_id=order['freelancer_id'],
                text=f"ℹ️ <b>Заказчик отменил работу</b>\n\n"
                     f"Заказ: {order['title']}\n\n"
                     f"Заказ возвращен в открытое состояние.\n"
                     f"Ваш отклик снова активен.",
                parse_mode='HTML'
            )
        except:
            pass

# ===== ОПЛАТА ЗАКАЗА =====
async def pay_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать инвойс для оплаты заказа"""
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split('_')[2])
    order = db.get_order(order_id)

    if order['customer_id'] != update.effective_user.id:
        await query.edit_message_text("❌ Это не ваш заказ")
        return

    # ПРОВЕРЯЕМ: может заказ уже оплачен?
    if order.get('payment_id'):
        payment = db.get_payment(order['payment_id'])
        if payment and payment['status'] in [PaymentStatus.PAID.value, PaymentStatus.COMPLETED.value]:
            await query.edit_message_text(
                "✅ Этот заказ уже оплачен!\n\n"
                "Ожидайте передачи работы от исполнителя.",
                parse_mode='HTML'
            )
            return

    if order['status'] != OrderStatus.WORK_COMPLETED.value:
        await query.edit_message_text("❌ Работа еще не завершена")
        return

    # Получаем согласованную цену
    responses = db.get_order_responses(order_id)
    accepted_response = None
    for resp in responses:
        if resp['status'] == ResponseStatus.ACCEPTED.value:
            accepted_response = resp
            break

    if not accepted_response:
        await query.edit_message_text("❌ Не найден принятый отклик")
        return

    amount = accepted_response['proposed_price']
    currency = order['currency']

    await query.edit_message_text("⏳ Создаю инвойс для оплаты...")

    # Создаем инвойс
    payload = f"order_{order_id}"
    description = f"Оплата заказа: {order['title']}"

    invoice = await crypto_bot.create_invoice(
        amount=amount,
        currency=currency,
        description=description,
        payload=payload
    )

    if not invoice:
        await query.edit_message_text(
            "❌ Ошибка при создании инвойса.\n"
            "Попробуйте позже или обратитесь в поддержку."
        )
        return

    # Сохраняем платеж
    payment_id = db.create_payment(
        order_id=order_id,
        amount=amount,
        currency=currency,
        customer_id=order['customer_id'],
        freelancer_id=order['freelancer_id'],
        invoice_id=invoice['invoice_id']
    )

    # Обновляем заказ
    db.update_order_status(
        order_id,
        OrderStatus.AWAITING_PAYMENT.value,
        payment_id=payment_id
    )

    # Отправляем ссылку
    pay_url = invoice['bot_invoice_url']
    keyboard = [[InlineKeyboardButton("💰 Оплатить", url=pay_url)]]

    fee = calculate_service_fee(amount)
    freelancer_amount = calculate_freelancer_amount(amount)

    await query.edit_message_text(
        f"💰 <b>Оплата заказа</b>\n\n"
        f"📋 Заказ: {order['title']}\n"
        f"💵 Сумма: {amount} {currency}\n\n"
        f"<b>Распределение:</b>\n"
        f"👷 Исполнителю: {freelancer_amount} {currency}\n"
        f"📊 Комиссия ({SERVICE_FEE}%): {fee} {currency}\n\n"
        f"⚠️ <b>Важно!</b>\n"
        f"После оплаты деньги будут заморожены на эскроу.\n"
        f"Исполнитель передаст вам работу.\n"
        f"После вашего подтверждения деньги поступят исполнителю.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # Проверка оплаты
    context.job_queue.run_once(
        check_payment,
        when=10,
        data={'payment_id': payment_id, 'invoice_id': invoice['invoice_id']},
        name=f"check_payment_{payment_id}"
    )

async def check_payment(context: ContextTypes.DEFAULT_TYPE):
    """Проверить статус оплаты"""
    job_data = context.job.data
    payment_id = job_data['payment_id']
    invoice_id = job_data['invoice_id']
    
    payment = db.get_payment(payment_id)
    if not payment or payment['status'] != PaymentStatus.PENDING.value:
        return
    
    # Проверяем статус инвойса
    invoice = await crypto_bot.get_invoice(invoice_id)
    
    if invoice and invoice.get('status') == 'paid':
        # Оплата прошла успешно - деньги на эскроу
        db.update_payment(
            payment_id,
            status=PaymentStatus.PAID.value,
            paid_at=datetime.now().isoformat()
        )
        
        order = db.get_order(payment['order_id'])
        db.update_order_status(
            payment['order_id'],
            OrderStatus.PAYMENT_RECEIVED.value
        )
        
        # Уведомляем заказчика
        try:
            await context.bot.send_message(
                chat_id=payment['customer_id'],
                text=f"✅ <b>Оплата получена!</b>\n\n"
                     f"Заказ: {order['title']}\n"
                     f"Сумма: {payment['amount']} {payment['currency']}\n\n"
                     f"💰 Средства заморожены на эскроу.\n"
                     f"Исполнитель получил уведомление и передаст вам работу.",
                parse_mode='HTML'
            )
        except:
            pass
        
        # Уведомляем исполнителя
        try:
            keyboard = [[
                InlineKeyboardButton(
                    "📤 Передать работу", 
                    callback_data=f"deliver_work_{payment['order_id']}"
                )
            ]]
            
            await context.bot.send_message(
                chat_id=payment['freelancer_id'],
                text=f"💰 <b>Заказ оплачен!</b>\n\n"
                     f"Заказ: {order['title']}\n"
                     f"Сумма: {payment['amount']} {payment['currency']}\n\n"
                     f"✅ Заказчик оплатил! Деньги на эскроу.\n\n"
                     f"📤 <b>Следующий шаг:</b>\n"
                     f"Нажмите 'Передать работу' и отправьте результат заказчику.\n"
                     f"После подтверждения деньги поступят на ваш кошелек.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass
    else:
        # Оплата еще не прошла
        context.job_queue.run_once(
            check_payment,
            when=30,
            data=job_data,
            name=f"check_payment_{payment_id}"
        )

# ===== МОИ ОТКЛИКИ =====
async def my_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Мои отклики - ОДНА КАРТОЧКА"""
    user = db.get_user(update.effective_user.id)

    if not user or user['role'] == UserRole.CUSTOMER.value:
        await update.message.reply_text("❌ У вас нет откликов")
        return

    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, o.title, o.budget, o.currency, o.status as order_status
        FROM responses r
        JOIN orders o ON r.order_id = o.order_id
        WHERE r.freelancer_id = ?
        ORDER BY r.created_at DESC
    ''', (update.effective_user.id,))
    responses = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not responses:
        await update.message.reply_text("💼 Пока нет откликов.\n\nНайдите заказы!")
        return

    context.user_data['my_responses_list'] = responses
    await show_my_response(update.message, context, 0)


async def show_my_response(msg, context: ContextTypes.DEFAULT_TYPE, index: int):
    """Показать один отклик"""
    responses = context.user_data.get('my_responses_list', [])
    if not responses or index < 0 or index >= len(responses):
        return

    response = responses[index]
    status_emoji = {"pending": "⏳", "accepted": "✅", "rejected": "❌"}

    text = f"💼 <b>Отклик {index + 1} из {len(responses)}</b>\n\n"
    text += f"{status_emoji.get(response['status'], '⚪')} <b>{response['title']}</b>\n\n"
    text += f"💰 {response['proposed_price']} {response['currency']}\n"
    text += f"📅 {response['proposed_timeline']}\n"

    keyboard = []
    row = []

    if index > 0:
        row.append(InlineKeyboardButton("◀️", callback_data=f"my_response_{index - 1}"))

    row.append(InlineKeyboardButton("📋 Заказ", callback_data=f"view_order_{response['order_id']}"))

    # Добавляем действия в зависимости от статуса
    if response['status'] == 'accepted':
        if response['order_status'] in ['in_progress', 'needs_revision']:
            row.append(InlineKeyboardButton("✅ Готово", callback_data=f"mark_completed_{response['order_id']}"))
        elif response['order_status'] in ['payment_received', 'work_delivered', 'needs_revision']:
            # Проверяем: может работа уже оплачена?
            order = db.get_order(response['order_id'])
            if order.get('payment_id'):
                payment = db.get_payment(order['payment_id'])
                if payment and payment['status'] in ['paid', 'completed']:
                    row.append(InlineKeyboardButton("📤 Передать", callback_data=f"deliver_work_{response['order_id']}"))

    row.append(InlineKeyboardButton(f"{index + 1}/{len(responses)}", callback_data="page_info"))

    if index + 1 < len(responses):
        row.append(InlineKeyboardButton("▶️", callback_data=f"my_response_{index + 1}"))

    keyboard.append(row)

    if hasattr(msg, 'edit_message_text'):
        await msg.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await msg.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def my_response_navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Навигация по откликам"""
    query = update.callback_query
    await query.answer()
    index = int(query.data.split('_')[2])
    await show_my_response(query, context, index)

# ===== ЗАЯВЛЕНИЕ О ВЫПОЛНЕНИИ =====
async def mark_completed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Исполнитель сообщает о выполнении работы"""
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split('_')[2])
    order = db.get_order(order_id)

    if order['freelancer_id'] != update.effective_user.id:
        await query.edit_message_text("❌ Это не ваш заказ")
        return

    if order['status'] not in [OrderStatus.IN_PROGRESS.value, OrderStatus.NEEDS_REVISION.value]:
        await query.edit_message_text("❌ Неверный статус заказа")
        return

    # ПРОВЕРЯЕМ: есть ли уже оплата?
    payment = None
    if order.get('payment_id'):
        payment = db.get_payment(order['payment_id'])

    # Если оплата УЖЕ есть (повторная сдача после доработок)
    if payment and payment['status'] in [PaymentStatus.PAID.value, PaymentStatus.COMPLETED.value]:
        # Сразу переводим в "оплачено, можно передавать работу"
        db.update_order_status(order_id, OrderStatus.PAYMENT_RECEIVED.value)

        await query.edit_message_text(
            "✅ <b>Вы сообщили о выполнении работы!</b>\n\n"
            "Заказ уже оплачен.\n"
            "Теперь можете передать результат заказчику.",
            parse_mode='HTML'
        )

        # Уведомляем заказчика что работа готова к передаче
        try:
            await context.bot.send_message(
                chat_id=order['customer_id'],
                text=f"✅ <b>Исполнитель завершил доработки!</b>\n\n"
                     f"Заказ: {order['title']}\n\n"
                     f"Ожидайте передачи обновленной работы.",
                parse_mode='HTML'
            )
        except:
            pass

        return

    # Если оплаты НЕТ (первая сдача)
    db.update_order_status(order_id, OrderStatus.WORK_COMPLETED.value)

    await query.edit_message_text(
        "✅ <b>Вы сообщили о выполнении работы!</b>\n\n"
        "Заказчик получил уведомление.\n"
        "После оплаты вы сможете передать работу.",
        parse_mode='HTML'
    )

    # Уведомляем заказчика об оплате
    try:
        keyboard = [[
            InlineKeyboardButton(
                "💰 Оплатить заказ",
                callback_data=f"pay_order_{order_id}"
            )
        ]]

        await context.bot.send_message(
            chat_id=order['customer_id'],
            text=f"✅ <b>Исполнитель завершил работу!</b>\n\n"
                 f"Заказ: {order['title']}\n\n"
                 f"⚠️ <b>Следующий шаг:</b>\n"
                 f"1. Оплатите заказ\n"
                 f"2. Исполнитель передаст вам результат\n"
                 f"3. Проверите и подтвердите\n\n"
                 f"Нажмите 'Оплатить заказ' когда будете готовы.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except:
        pass

# ===== ПЕРЕДАЧА РАБОТЫ (ПОСЛЕ ОПЛАТЫ) =====
async def deliver_work(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Передача работы заказчику после оплаты"""
    query = update.callback_query
    await query.answer()
    
    order_id = int(query.data.split('_')[2])
    order = db.get_order(order_id)
    
    if order['freelancer_id'] != update.effective_user.id:
        await query.edit_message_text("❌ Это не ваш заказ")
        return ConversationHandler.END
    
    if order['status'] != OrderStatus.PAYMENT_RECEIVED.value:
        await query.edit_message_text("❌ Заказчик еще не оплатил")
        return ConversationHandler.END
    
    context.user_data['deliver_order_id'] = order_id
    
    await query.edit_message_text(
        f"📤 <b>Передача работы</b>\n\n"
        f"Заказ: {order['title']}\n\n"
        f"⚠️ <b>Важно!</b> Заказчик уже оплатил.\n"
        f"Деньги на эскроу, будут переведены после подтверждения.\n\n"
        f"Пришлите результат работы:\n"
        f"- Ссылки на файлы\n"
        f"- GitHub репозиторий\n"
        f"- Демо\n"
        f"- Доступы\n"
        f"- Инструкции",
        parse_mode='HTML'
    )
    
    return WORK_DELIVERY

async def work_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка передачи работы"""
    order_id = context.user_data['deliver_order_id']
    delivery_message = update.message.text
    
    # Обновляем статус - работа передана
    db.update_order_status(order_id, OrderStatus.WORK_DELIVERED.value)
    
    order = db.get_order(order_id)
    
    await update.message.reply_text(
        "✅ <b>Работа передана заказчику!</b>\n\n"
        "Заказчик проверит результат.\n"
        "После подтверждения деньги поступят на ваш кошелек.",
        parse_mode='HTML',
        reply_markup=get_main_keyboard(db.get_user(update.effective_user.id)['role'], update.effective_user.id)
    )
    
    # Уведомляем заказчика
    try:
        keyboard = [[
            InlineKeyboardButton(
                "✅ Работа выполнена корректно", 
                callback_data=f"approve_work_{order_id}"
            )
        ],[
            InlineKeyboardButton(
                "🔄 Нужны доработки", 
                callback_data=f"request_revision_{order_id}"
            ),
            InlineKeyboardButton(
                "⚠️ Проблема", 
                callback_data=f"dispute_order_{order_id}"
            )
        ]]
        
        await context.bot.send_message(
            chat_id=order['customer_id'],
            text=f"📦 <b>Работа передана!</b>\n\n"
                 f"Заказ: {order['title']}\n\n"
                 f"<b>Результат от исполнителя:</b>\n{delivery_message}\n\n"
                 f"⚠️ <b>Проверьте работу!</b>\n\n"
                 f"Если всё корректно - подтвердите.\n"
                 f"Если нужны доработки - укажите что исправить.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except:
        pass
    
    context.user_data.clear()
    return ConversationHandler.END

# ===== ПОДТВЕРЖДЕНИЕ РАБОТЫ =====
async def approve_work(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Заказчик подтверждает корректное выполнение"""
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split('_')[2])
    order = db.get_order(order_id)

    if order['customer_id'] != update.effective_user.id:
        await query.edit_message_text("❌ Это не ваш заказ")
        return

    if order['status'] != OrderStatus.WORK_DELIVERED.value:
        await query.edit_message_text("❌ Работа еще не передана")
        return

    await query.edit_message_text("⏳ Обрабатываем выплату...")

    payment = db.get_payment(order['payment_id'])

    if not payment:
        await query.edit_message_text("❌ Платеж не найден")
        return

    db.update_order_status(order_id, OrderStatus.PENDING_PAYOUT.value)

    freelancer_amount = calculate_freelancer_amount(payment['amount'])
    transfer_id = f"order_{order_id}_payment_{payment['payment_id']}"

    transfer = await crypto_bot.transfer(
        user_id=order['freelancer_id'],
        amount=freelancer_amount,
        currency=payment['currency'],
        spend_id=transfer_id
    )

    if not transfer:
        ticket_id = db.create_ticket(
            order_id,
            order['freelancer_id'],
            f"Автоматический тикет: Ошибка выплаты. Payment ID: {payment['payment_id']}"
        )
        db.update_order_status(order_id, OrderStatus.DISPUTED.value)

        await query.edit_message_text(
            "❌ Ошибка при переводе средств.\n"
            "Создан тикет для администратора.\n"
            "Мы решим проблему в ближайшее время."
        )

        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"🆘 <b>Ошибка выплаты! Тикет #{ticket_id}</b>\n\n"
                         f"Заказ ID: {order_id}\n"
                         f"Не удалось перевести {freelancer_amount} {payment['currency']}\n"
                         f"Требуется вмешательство!",
                    parse_mode='HTML'
                )
            except:
                pass
        return

    db.update_payment(
        payment['payment_id'],
        status=PaymentStatus.COMPLETED.value,
        transfer_id=transfer_id,
        completed_at=datetime.now().isoformat()
    )

    fee = calculate_service_fee(payment['amount'])

    # ЗАМЕНИТЬ финальное сообщение на запрос оценки
    keyboard = []
    for rating in [5, 4, 3, 2, 1]:
        stars = "⭐" * rating
        keyboard.append([InlineKeyboardButton(
            f"{stars} ({rating})",
            callback_data=f"rate_freelancer_{order_id}_{rating}"
        )])
    keyboard.append([InlineKeyboardButton("⏭ Пропустить", callback_data=f"skip_rating_{order_id}")])

    await query.edit_message_text(
        f"✅ <b>Выплата отправлена!</b>\n\n"
        f"Исполнителю переведено: {freelancer_amount} {payment['currency']}\n"
        f"Комиссия сервиса: {fee} {payment['currency']}\n\n"
        f"⭐ <b>Оцените исполнителя:</b>\n"
        f"Как вам работа {db.get_user(order['freelancer_id'])['name']}?",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # Уведомляем исполнителя (без изменений)
    try:
        keyboard_freelancer = [[
            InlineKeyboardButton(
                "✅ Подтвердить получение оплаты",
                callback_data=f"confirm_payout_{order_id}"
            )
        ]]

        await context.bot.send_message(
            chat_id=order['freelancer_id'],
            text=f"💰 <b>Выплата отправлена!</b>\n\n"
                 f"Заказ: {order['title']}\n"
                 f"Сумма: {freelancer_amount} {payment['currency']}\n\n"
                 f"✅ Средства переведены на ваш @CryptoBot кошелек.\n"
                 f"Проверьте баланс в @CryptoBot\n\n"
                 f"Пожалуйста, подтвердите получение.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard_freelancer)
        )
    except:
        pass


async def rate_freelancer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оценка исполнителя от заказчика"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split('_')
    order_id = int(parts[2])
    rating = int(parts[3])

    order = db.get_order(order_id)

    # Сразу сохраняем оценку БЕЗ комментария
    db.create_review(
        order_id,
        order['customer_id'],
        order['freelancer_id'],
        rating,
        ""
    )

    await query.edit_message_text(
        f"⭐ Спасибо за оценку {rating}/5!\n\n"
        f"Заказ завершен.",
        parse_mode='HTML'
    )


async def skip_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить оценку"""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "✅ Спасибо за работу!\n\n"
        "Заказ завершен.",
        parse_mode='HTML'
    )

# ===== ЗАПРОС ДОРАБОТОК =====
async def request_revision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Заказчик запрашивает доработки"""
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split('_')[2])
    order = db.get_order(order_id)

    if order['customer_id'] != update.effective_user.id:
        await query.edit_message_text("❌ Это не ваш заказ")
        return ConversationHandler.END

    context.user_data['revision_order_id'] = order_id

    await query.edit_message_text(
        f"🔄 <b>Запрос доработок</b>\n\n"
        f"Заказ: {order['title']}\n\n"
        f"Опишите подробно, что нужно исправить или доработать:",
        parse_mode='HTML'
    )

    return TICKET_DESCRIPTION


async def revision_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка запроса доработок"""
    order_id = context.user_data['revision_order_id']
    revision_message = update.message.text

    # Возвращаем в статус "Нужны доработки"
    # ВАЖНО: НЕ трогаем payment_id - оплата остается!
    db.update_order_status(order_id, OrderStatus.NEEDS_REVISION.value)

    order = db.get_order(order_id)

    await update.message.reply_text(
        "🔄 <b>Запрос отправлен!</b>\n\n"
        "Исполнитель получил список доработок.\n"
        "Он сможет снова отметить работу как выполненную после исправлений.",
        parse_mode='HTML',
        reply_markup=get_main_keyboard(db.get_user(update.effective_user.id)['role'], update.effective_user.id)
    )

    # Уведомляем исполнителя
    try:
        await context.bot.send_message(
            chat_id=order['freelancer_id'],
            text=f"🔄 <b>Нужны доработки</b>\n\n"
                 f"Заказ: {order['title']}\n\n"
                 f"<b>Комментарий заказчика:</b>\n{revision_message}\n\n"
                 f"Пожалуйста, внесите исправления и снова отметьте работу как выполненную.",
            parse_mode='HTML'
        )
    except:
        pass

    context.user_data.clear()
    return ConversationHandler.END

# ===== ПОДТВЕРЖДЕНИЕ ПОЛУЧЕНИЯ ОПЛАТЫ =====
async def confirm_payout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Исполнитель подтверждает получение оплаты"""
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split('_')[2])
    order = db.get_order(order_id)

    if order['freelancer_id'] != update.effective_user.id:
        await query.edit_message_text("❌ Это не ваш заказ")
        return

    if order['status'] != OrderStatus.PENDING_PAYOUT.value:
        await query.edit_message_text("❌ Неверный статус заказа")
        return

    # Завершаем заказ
    db.update_order_status(
        order_id,
        OrderStatus.COMPLETED.value,
        completed_at=datetime.now().isoformat()
    )

    # Обновляем счетчик
    freelancer = db.get_user(order['freelancer_id'])
    db.update_user(
        order['freelancer_id'],
        completed_orders=freelancer['completed_orders'] + 1
    )

    payment = db.get_payment(order['payment_id'])
    freelancer_amount = calculate_freelancer_amount(payment['amount'])

    # ДОБАВЛЯЕМ ЗАПРОС ОЦЕНКИ ОТ ИСПОЛНИТЕЛЯ
    keyboard = []
    for rating in [5, 4, 3, 2, 1]:
        stars = "⭐" * rating
        keyboard.append([InlineKeyboardButton(
            f"{stars} ({rating})",
            callback_data=f"rate_customer_{order_id}_{rating}"
        )])
    keyboard.append([InlineKeyboardButton("⏭ Пропустить", callback_data=f"skip_rating_{order_id}")])

    await query.edit_message_text(
        f"🎉 <b>Заказ завершен!</b>\n\n"
        f"Получено: {freelancer_amount} {payment['currency']}\n\n"
        f"⭐ <b>Оцените заказчика:</b>\n"
        f"Как вам было работать с {db.get_user(order['customer_id'])['name']}?",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def rate_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оценка заказчика от исполнителя"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split('_')
    order_id = int(parts[2])
    rating = int(parts[3])

    order = db.get_order(order_id)

    # Сразу сохраняем оценку БЕЗ комментария
    db.create_review(
        order_id,
        order['freelancer_id'],
        order['customer_id'],
        rating,
        ""
    )

    await query.edit_message_text(
        f"⭐ Спасибо за оценку {rating}/5!\n\n"
        f"Заказ завершен.",
        parse_mode='HTML'
    )


# ===== СИСТЕМА ТИКЕТОВ =====
async def dispute_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало создания тикета"""
    query = update.callback_query
    await query.answer()
    
    order_id = int(query.data.split('_')[2])
    order = db.get_order(order_id)
    
    context.user_data['ticket_order_id'] = order_id
    
    await query.edit_message_text(
        f"⚠️ <b>Обращение в поддержку</b>\n\n"
        f"Заказ: {order['title']}\n\n"
        f"Опишите возникшую проблему подробно:",
        parse_mode='HTML'
    )
    
    return TICKET_DESCRIPTION

async def ticket_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Создание тикета"""
    description = update.message.text
    order_id = context.user_data['ticket_order_id']
    user_id = update.effective_user.id
    
    ticket_id = db.create_ticket(order_id, user_id, description)
    
    # Обновляем статус заказа
    db.update_order_status(order_id, OrderStatus.DISPUTED.value)
    
    order = db.get_order(order_id)
    
    await update.message.reply_text(
        f"✅ Тикет #{ticket_id} создан!\n\n"
        f"Администратор рассмотрит вашу проблему в ближайшее время.\n"
        f"Вы получите уведомление о решении.",
        reply_markup=get_main_keyboard(db.get_user(user_id)['role'], user_id)
    )
    
    # Уведомляем администраторов
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🆘 <b>Новый тикет #{ticket_id}</b>\n\n"
                     f"Заказ: {order['title']}\n"
                     f"От пользователя: {update.effective_user.id}\n\n"
                     f"Проблема:\n{description}\n\n"
                     f"Используйте админ-панель для управления.",
                parse_mode='HTML'
            )
        except:
            pass
    
    context.user_data.clear()
    return ConversationHandler.END

# ===== АДМИН-ПАНЕЛЬ =====
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ У вас нет прав администратора")
        return

    open_tickets = db.get_open_tickets()

    keyboard = [
        [InlineKeyboardButton(
            f"🎫 Тикеты ({len(open_tickets)})",
            callback_data="admin_tickets"
        )],
        [InlineKeyboardButton(
            "💰 Баланс бота",
            callback_data="admin_balance"
        )],
        [InlineKeyboardButton(
            "✅ Доступно для вывода",  # НОВАЯ КНОПКА
            callback_data="admin_available_balance"
        )]
    ]

    await update.message.reply_text(
        "⚙️ <b>Админ-панель</b>\n\n"
        "Выберите действие:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр тикетов"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("❌ У вас нет прав")
        return
    
    tickets = db.get_open_tickets()
    
    if not tickets:
        await query.edit_message_text("✅ Нет открытых тикетов")
        return
    
    await query.edit_message_text(
        f"🎫 <b>Открытые тикеты: {len(tickets)}</b>",
        parse_mode='HTML'
    )
    
    for ticket in tickets:
        order = db.get_order(ticket['order_id'])
        user = db.get_user(ticket['user_id'])
        
        text = f"<b>Тикет #{ticket['ticket_id']}</b>\n\n"
        text += f"📋 Заказ: {order['title']}\n"
        text += f"👤 От: {user['name']} (ID: {user['user_id']})\n"
        text += f"📅 Создан: {ticket['created_at'][:16]}\n\n"
        text += f"<b>Проблема:</b>\n{ticket['description']}"
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "💰 Вернуть заказчику", 
                    callback_data=f"refund_ticket_{ticket['ticket_id']}"
                ),
                InlineKeyboardButton(
                    "✅ Выплатить исполнителю", 
                    callback_data=f"payout_ticket_{ticket['ticket_id']}"
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Закрыть тикет", 
                    callback_data=f"close_ticket_{ticket['ticket_id']}"
                )
            ]
        ]
        
        await query.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def refund_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат средств заказчику"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("❌ Нет прав")
        return
    
    ticket_id = int(query.data.split('_')[2])
    ticket = db.get_ticket(ticket_id)
    order = db.get_order(ticket['order_id'])
    payment = db.get_payment(order['payment_id'])
    
    await query.edit_message_text("⏳ Обработка возврата...")
    
    # Переводим средства обратно заказчику
    transfer_id = f"refund_order_{order['order_id']}"
    
    transfer = await crypto_bot.transfer(
        user_id=order['customer_id'],
        amount=payment['amount'],
        currency=payment['currency'],
        spend_id=transfer_id
    )
    
    if not transfer:
        await query.edit_message_text("❌ Ошибка возврата")
        return
    
    # Обновляем платеж
    db.update_payment(
        payment['payment_id'],
        status=PaymentStatus.REFUNDED.value,
        transfer_id=transfer_id
    )
    
    # Закрываем тикет
    db.update_ticket(
        ticket_id,
        status=TicketStatus.RESOLVED.value,
        admin_id=update.effective_user.id,
        resolution="Возврат средств заказчику",
        resolved_at=datetime.now().isoformat()
    )
    
    # Обновляем заказ
    db.update_order_status(order['order_id'], OrderStatus.CANCELLED.value)
    
    await query.edit_message_text(
        f"✅ Возврат выполнен!\n\n"
        f"Тикет #{ticket_id} закрыт\n"
        f"Сумма {payment['amount']} {payment['currency']} возвращена заказчику"
    )
    
    # Уведомляем заказчика
    try:
        await context.bot.send_message(
            chat_id=order['customer_id'],
            text=f"💰 <b>Возврат средств</b>\n\n"
                 f"По тикету #{ticket_id} принято решение о возврате.\n"
                 f"Сумма {payment['amount']} {payment['currency']} возвращена на ваш кошелек.",
            parse_mode='HTML'
        )
    except:
        pass

async def payout_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выплата исполнителю"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("❌ Нет прав")
        return
    
    ticket_id = int(query.data.split('_')[2])
    ticket = db.get_ticket(ticket_id)
    order = db.get_order(ticket['order_id'])
    payment = db.get_payment(order['payment_id'])
    
    await query.edit_message_text("⏳ Обработка выплаты...")
    
    # Рассчитываем сумму
    freelancer_amount = calculate_freelancer_amount(payment['amount'])
    transfer_id = f"payout_order_{order['order_id']}"
    
    transfer = await crypto_bot.transfer(
        user_id=order['freelancer_id'],
        amount=freelancer_amount,
        currency=payment['currency'],
        spend_id=transfer_id
    )
    
    if not transfer:
        await query.edit_message_text("❌ Ошибка выплаты")
        return
    
    # Обновляем платеж
    db.update_payment(
        payment['payment_id'],
        status=PaymentStatus.COMPLETED.value,
        transfer_id=transfer_id,
        completed_at=datetime.now().isoformat()
    )
    
    # Закрываем тикет
    db.update_ticket(
        ticket_id,
        status=TicketStatus.RESOLVED.value,
        admin_id=update.effective_user.id,
        resolution="Выплата исполнителю",
        resolved_at=datetime.now().isoformat()
    )
    
    # Обновляем заказ
    db.update_order_status(order['order_id'], OrderStatus.COMPLETED.value)
    
    await query.edit_message_text(
        f"✅ Выплата выполнена!\n\n"
        f"Тикет #{ticket_id} закрыт\n"
        f"Сумма {freelancer_amount} {payment['currency']} выплачена исполнителю"
    )
    
    # Уведомляем исполнителя
    try:
        await context.bot.send_message(
            chat_id=order['freelancer_id'],
            text=f"💰 <b>Выплата получена</b>\n\n"
                 f"По тикету #{ticket_id} принято решение о выплате.\n"
                 f"Сумма {freelancer_amount} {payment['currency']} переведена на ваш кошелек.",
            parse_mode='HTML'
        )
    except:
        pass

async def close_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрыть тикет без действий"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("❌ Нет прав")
        return
    
    ticket_id = int(query.data.split('_')[2])
    
    db.update_ticket(
        ticket_id,
        status=TicketStatus.CLOSED.value,
        admin_id=update.effective_user.id,
        resolved_at=datetime.now().isoformat()
    )
    
    await query.edit_message_text(f"✅ Тикет #{ticket_id} закрыт")


async def admin_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр баланса бота"""
    query = update.callback_query
    await query.answer()

    if not is_admin(update.effective_user.id):
        await query.edit_message_text("❌ Нет прав")
        return

    balance = await crypto_bot.get_balance()

    if not balance:
        await query.edit_message_text("❌ Ошибка получения баланса")
        return

    text = "💰 <b>Баланс бота</b>\n\n"

    for item in balance:
        text += f"{item['currency_code']}: {item['available']}\n"

    # ДОБАВИТЬ кнопку назад
    keyboard = [[InlineKeyboardButton("◀️ Админ-панель", callback_data="back_to_admin")]]

    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к админ-панели"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ У вас нет прав администратора")
        return

    open_tickets = db.get_open_tickets()

    keyboard = [
        [InlineKeyboardButton(f"🎫 Тикеты ({len(open_tickets)})", callback_data="admin_tickets")],
        [InlineKeyboardButton("💰 Баланс бота", callback_data="admin_balance")],
        [InlineKeyboardButton("✅ Доступно для вывода", callback_data="admin_available_balance")]
    ]

    await query.edit_message_text(
        "⚙️ <b>Админ-панель</b>\n\nВыберите действие:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ===== ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ =====
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать профиль"""
    user = db.get_user(update.effective_user.id)
    
    if not user:
        await update.message.reply_text(
            "❌ Профиль не найден. Используйте /start для регистрации."
        )
        return
    
    await update.message.reply_text(
        format_user_profile(user),
        parse_mode='HTML'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    help_text = f"""
ℹ️ <b>Справка по Freelance Bot</b>

<b>Процесс работы:</b>
1️⃣ Заказчик создает заказ
2️⃣ Исполнители откликаются
3️⃣ Заказчик выбирает исполнителя
4️⃣ Исполнитель работает
5️⃣ Исполнитель жмет "Работа выполнена"
6️⃣ Заказчик ОПЛАЧИВАЕТ заказ
7️⃣ Исполнитель ПЕРЕДАЕТ работу
8️⃣ Заказчик проверяет:
   ✅ "Работа выполнена корректно" → выплата
   🔄 "Нужны доработки" → исправления
9️⃣ Исполнитель подтверждает получение
🔟 Заказ завершен! ✅

<b>Безопасность:</b>
💰 Оплата ПОСЛЕ заявления о выполнении
🔒 Деньги на эскроу до подтверждения
📦 Работа передается ПОСЛЕ оплаты
✅ Выплата после подтверждения заказчика

<b>Отмена работы:</b>
❌ Можно отменить до оплаты
🔄 Заказ вернется в открытое состояние

<b>Доработки:</b>
🔄 Заказчик может запросить исправления
♻️ Процесс повторяется с шага 5

<b>Валюты:</b>
💎 {', '.join(SUPPORTED_CURRENCIES)}
📊 Комиссия: {SERVICE_FEE}%

<b>Проблемы:</b>
⚠️ Кнопка "Проблема" → тикет админу
"""
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена операции"""
    await update.message.reply_text(
        "❌ Операция отменена.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    user = db.get_user(update.effective_user.id)
    if user:
        await update.message.reply_text(
            "Используйте меню для навигации.",
            reply_markup=get_main_keyboard(user['role'], update.effective_user.id)
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    text = update.message.text
    
    if text == '📝 Создать заказ':
        return await create_order_start(update, context)
    elif text == '📋 Мои заказы':
        return await my_orders(update, context)
    elif text == '🔍 Найти заказы':
        return await find_orders(update, context)
    elif text == '💼 Мои отклики':
        return await my_responses(update, context)
    elif text == '👤 Профиль':
        return await profile(update, context)
    elif text == 'ℹ️ Помощь':
        return await help_command(update, context)
    elif text == '⚙️ Админ-панель':
        return await admin_panel(update, context)


async def save_review_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранить отзыв с комментарием"""
    review = context.user_data.get('pending_review')
    if not review:
        await update.message.reply_text("❌ Ошибка: данные отзыва не найдены")
        return ConversationHandler.END

    comment = update.message.text

    # Создаем отзыв
    db.create_review(
        review['order_id'],
        review['from_user'],
        review['to_user'],
        review['rating'],
        comment
    )

    user = db.get_user(update.effective_user.id)

    await update.message.reply_text(
        "✅ Спасибо за отзыв!\n\n"
        "Заказ завершен.",
        reply_markup=get_main_keyboard(user['role'], update.effective_user.id)
    )

    context.user_data.pop('pending_review', None)
    return ConversationHandler.END


async def skip_review_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пропустить комментарий к отзыву"""
    review = context.user_data.get('pending_review')
    if review:
        # Создаем отзыв без комментария
        db.create_review(
            review['order_id'],
            review['from_user'],
            review['to_user'],
            review['rating'],
            ""
        )

    user = db.get_user(update.effective_user.id)

    await update.message.reply_text(
        "✅ Спасибо!\n\nЗаказ завершен.",
        reply_markup=get_main_keyboard(user['role'], update.effective_user.id)
    )

    context.user_data.pop('pending_review', None)
    return ConversationHandler.END


# ==================== MAIN ====================
def main():
    """Запуск бота"""
    
    application = Application.builder().token(BOT_TOKEN).build()

    review_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(rate_customer, pattern='^rate_customer_'),
            CallbackQueryHandler(rate_freelancer, pattern='^rate_freelancer_')
        ],
        states={
            REVIEW_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_review_comment),
                CommandHandler('skip', skip_review_comment)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # ConversationHandler для регистрации
    registration_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING_ROLE: [CallbackQueryHandler(choose_role, pattern='^role_')],
            CUSTOMER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_name)],
            CUSTOMER_COMPANY: [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_company)],
            CUSTOMER_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_description)],
            FREELANCER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, freelancer_name)],
            FREELANCER_SKILLS: [MessageHandler(filters.TEXT & ~filters.COMMAND, freelancer_skills)],
            FREELANCER_PORTFOLIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, freelancer_portfolio)],
            FREELANCER_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, freelancer_rate)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # ConversationHandler для создания заказа
    create_order_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📝 Создать заказ$'), create_order_start)],
        states={
            ORDER_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_title)],
            ORDER_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_description)],
            ORDER_BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_budget)],
            ORDER_CATEGORY: [CallbackQueryHandler(order_category, pattern='^cat_')],  # ДОБАВИТЬ
            ORDER_SUBCATEGORY: [CallbackQueryHandler(order_subcategory, pattern='^subcat_|^back_to_categories')],
            # ДОБАВИТЬ
            ORDER_CURRENCY: [CallbackQueryHandler(order_currency, pattern='^currency_')],
            ORDER_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_deadline)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # ConversationHandler для отклика
    response_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(respond_to_order, pattern='^respond_order_')],
        states={
            RESPONSE_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, response_description)],
            RESPONSE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, response_price)],
            RESPONSE_TIMELINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, response_timeline)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # ConversationHandler для сдачи/передачи работы
    deliver_work_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(deliver_work, pattern='^deliver_work_')],
        states={
            WORK_DELIVERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, work_delivery)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # ConversationHandler для запроса доработок
    revision_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(request_revision, pattern='^request_revision_')],
        states={
            TICKET_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, revision_description)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    ticket_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(dispute_order, pattern='^dispute_order_')],
        states={
            TICKET_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_description)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Добавляем обработчики
    application.add_handler(registration_handler)
    application.add_handler(create_order_handler)
    application.add_handler(response_handler)
    application.add_handler(deliver_work_handler)
    application.add_handler(revision_handler)
    application.add_handler(ticket_handler)
    application.add_handler(CallbackQueryHandler(back_to_cat_select, pattern='^back_to_cat_select'))
    application.add_handler(CallbackQueryHandler(browse_subcategory, pattern='^browse_subcat_'))
    application.add_handler(CallbackQueryHandler(back_to_subcat, pattern='^back_to_subcat_'))
    # Админ доступный баланс
    application.add_handler(CallbackQueryHandler(admin_available_balance, pattern='^admin_available_balance'))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(view_order, pattern='^view_order_'))
    application.add_handler(CallbackQueryHandler(manage_order, pattern='^manage_order_'))
    application.add_handler(CallbackQueryHandler(order_responses, pattern='^order_responses_'))
    application.add_handler(CallbackQueryHandler(accept_response, pattern='^accept_response_'))
    application.add_handler(CallbackQueryHandler(reject_response, pattern='^reject_response_'))
    application.add_handler(CallbackQueryHandler(cancel_order_progress, pattern='^cancel_order_'))
    application.add_handler(CallbackQueryHandler(mark_completed, pattern='^mark_completed_'))
    application.add_handler(CallbackQueryHandler(pay_order, pattern='^pay_order_'))
    application.add_handler(CallbackQueryHandler(approve_work, pattern='^approve_work_'))
    application.add_handler(CallbackQueryHandler(confirm_payout, pattern='^confirm_payout_'))
    application.add_handler(CallbackQueryHandler(view_response_navigate, pattern='^view_response_'))
    # Кнопки назад
    application.add_handler(CallbackQueryHandler(back_to_my_responses, pattern='^back_to_my_responses'))
    application.add_handler(CallbackQueryHandler(back_to_admin, pattern='^back_to_admin'))

    # Рейтинги (обновленные версии)
    application.add_handler(CallbackQueryHandler(rate_customer, pattern='^rate_customer_'))
    application.add_handler(CallbackQueryHandler(rate_freelancer, pattern='^rate_freelancer_'))

    # Админ handlers
    application.add_handler(CallbackQueryHandler(admin_tickets, pattern='^admin_tickets'))
    application.add_handler(CallbackQueryHandler(admin_balance, pattern='^admin_balance'))
    application.add_handler(CallbackQueryHandler(refund_ticket, pattern='^refund_ticket_'))
    application.add_handler(CallbackQueryHandler(payout_ticket, pattern='^payout_ticket_'))
    application.add_handler(CallbackQueryHandler(close_ticket, pattern='^close_ticket_'))
    
    # Текстовые обработчики
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(browse_category, pattern='^browse_cat_'))
    application.add_handler(CallbackQueryHandler(back_to_cat_select, pattern='^back_to_cat_select'))
    application.add_handler(CallbackQueryHandler(my_order_navigate, pattern='^my_order_'))
    application.add_handler(CallbackQueryHandler(my_response_navigate, pattern='^my_response_'))
    application.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern='^page_info$'))

    # Отзывы и оценки
    application.add_handler(review_handler)
    application.add_handler(CallbackQueryHandler(skip_rating, pattern='^skip_rating_'))

    # Кнопка "Назад к моим заказам"
    application.add_handler(CallbackQueryHandler(back_to_my_orders, pattern='^back_to_my_orders'))
    
    # Запуск бота
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

