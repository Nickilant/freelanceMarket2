from typing import Dict

from telegram import ReplyKeyboardMarkup

from settings import ADMIN_IDS, SERVICE_FEE
from constants import CATEGORIES, OrderStatus, UserRole

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

