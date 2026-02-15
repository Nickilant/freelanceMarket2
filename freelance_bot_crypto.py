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

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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

from settings import BOT_TOKEN, ADMIN_IDS, SERVICE_FEE, SUPPORTED_CURRENCIES, validate_config
from constants import (
    UserRole, OrderStatus, ResponseStatus, PaymentStatus, TicketStatus,
    CHOOSING_ROLE, CUSTOMER_NAME, CUSTOMER_COMPANY, CUSTOMER_DESCRIPTION,
    FREELANCER_NAME, FREELANCER_SKILLS, FREELANCER_PORTFOLIO, FREELANCER_RATE,
    ORDER_TITLE, ORDER_DESCRIPTION, ORDER_BUDGET, ORDER_CATEGORY, ORDER_SUBCATEGORY,
    ORDER_CURRENCY, ORDER_DEADLINE, RESPONSE_DESCRIPTION, RESPONSE_PRICE, RESPONSE_TIMELINE,
    TICKET_DESCRIPTION, WORK_DELIVERY, REVIEW_COMMENT,
    MAX_ACTIVE_RESPONSES, MAX_RESPONSES_PER_ORDER, CATEGORIES, ORDERS_PER_PAGE,
)
from cryptobot_api import crypto_bot
from database import db
from utils import is_admin, calculate_service_fee, calculate_freelancer_amount, get_main_keyboard, format_order_info, format_user_profile

from handlers.orders import (
    create_order_start, order_title, order_description, order_budget, order_category,
    order_subcategory, order_currency, order_deadline, find_orders, browse_category,
    back_to_subcat, browse_subcategory, back_to_cat_select, view_order, back_to_my_responses,
    my_orders, show_my_order, my_order_navigate, manage_order, back_to_my_orders,
    order_responses, show_order_response, view_response_navigate, respond_to_order,
    response_description, response_price, response_timeline, accept_response, reject_response,
    cancel_order_progress, my_responses, show_my_response, my_response_navigate, mark_completed,
    deliver_work, work_delivery, approve_work, rate_freelancer, skip_rating, request_revision,
    revision_description, confirm_payout, rate_customer, dispute_order, ticket_description,
)
from handlers.payments import pay_order, check_payment
from handlers.admin import (
    admin_available_balance, admin_panel, admin_tickets, refund_ticket,
    payout_ticket, close_ticket, admin_balance, back_to_admin,
)

logger = logging.getLogger(__name__)

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






# [ПРОДОЛЖЕНИЕ В СЛЕДУЮЩЕЙ ЧАСТИ - ПЛАТЕЖИ И АДМИНКА]












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
    validate_config()

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
