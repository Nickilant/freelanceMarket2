from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from constants import OrderStatus, ResponseStatus, PaymentStatus
from cryptobot_api import crypto_bot
from database import db
from settings import SERVICE_FEE
from utils import calculate_service_fee, calculate_freelancer_amount


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


