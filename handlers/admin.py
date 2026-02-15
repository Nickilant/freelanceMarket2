from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from constants import OrderStatus, PaymentStatus, TicketStatus
from cryptobot_api import crypto_bot
from database import db
from settings import ADMIN_IDS
from utils import is_admin, calculate_freelancer_amount


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


