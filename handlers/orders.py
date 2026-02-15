from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, ContextTypes

from constants import (
    UserRole, OrderStatus, ResponseStatus, PaymentStatus,
    ORDER_TITLE, ORDER_DESCRIPTION, ORDER_BUDGET, ORDER_CATEGORY, ORDER_SUBCATEGORY,
    ORDER_CURRENCY, ORDER_DEADLINE, RESPONSE_DESCRIPTION, RESPONSE_PRICE, RESPONSE_TIMELINE,
    TICKET_DESCRIPTION, WORK_DELIVERY, REVIEW_COMMENT,
    MAX_ACTIVE_RESPONSES, MAX_RESPONSES_PER_ORDER, CATEGORIES, ORDERS_PER_PAGE,
)
from database import db
from cryptobot_api import crypto_bot
from settings import ADMIN_IDS, SERVICE_FEE
from utils import get_main_keyboard, format_order_info, calculate_service_fee, calculate_freelancer_amount


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


