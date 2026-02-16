from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, ContextTypes

from constants import UserRole, VACANCY_TITLE, VACANCY_DESCRIPTION, VACANCY_REQUIREMENTS, VACANCY_CONTACT
from cryptobot_api import crypto_bot
from database import db

VACANCY_POST_PRICE_USDT = 1.0


async def create_vacancy_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = db.get_user(update.effective_user.id)
    if not user or user['role'] == UserRole.FREELANCER.value:
        await update.message.reply_text("❌ Только заказчики могут размещать вакансии.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📢 <b>Размещение вакансии</b>\n\n"
        "Введите название вакансии:",
        parse_mode='HTML'
    )
    return VACANCY_TITLE


async def vacancy_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['vacancy_title'] = update.message.text
    await update.message.reply_text("📝 Опишите вакансию:")
    return VACANCY_DESCRIPTION


async def vacancy_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['vacancy_description'] = update.message.text
    await update.message.reply_text("✅ Укажите требования к кандидату:")
    return VACANCY_REQUIREMENTS


async def vacancy_requirements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['vacancy_requirements'] = update.message.text
    await update.message.reply_text(
        "📞 Оставьте контакты для собеседования (username, tg, email и т.д.):"
    )
    return VACANCY_CONTACT


async def vacancy_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['vacancy_contact'] = update.message.text

    customer = update.effective_user
    vacancy_id = db.create_vacancy(
        customer_id=customer.id,
        title=context.user_data['vacancy_title'],
        description=context.user_data['vacancy_description'],
        requirements=context.user_data['vacancy_requirements'],
        contact=context.user_data['vacancy_contact'],
    )

    invoice = await crypto_bot.create_invoice(
        amount=VACANCY_POST_PRICE_USDT,
        currency='USDT',
        description=f"Размещение вакансии #{vacancy_id}",
        payload=f"vacancy_{vacancy_id}"
    )

    if not invoice:
        await update.message.reply_text(
            "❌ Не удалось создать инвойс на оплату вакансии. Попробуйте позже."
        )
        context.user_data.clear()
        return ConversationHandler.END

    db.set_vacancy_payment(vacancy_id, invoice['invoice_id'], 'pending')

    keyboard = [
        [InlineKeyboardButton("💳 Оплатить 1 USDT", url=invoice['bot_invoice_url'])],
        [InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_vacancy_payment_{vacancy_id}")]
    ]

    await update.message.reply_text(
        "✅ Вакансия создана в черновике.\n\n"
        "Для публикации оплатите размещение: <b>1 USDT</b>.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    context.job_queue.run_once(
        check_vacancy_payment_job,
        when=10,
        data={"vacancy_id": vacancy_id, "invoice_id": invoice['invoice_id']},
        name=f"check_vacancy_payment_{vacancy_id}"
    )

    context.user_data.clear()
    return ConversationHandler.END


async def check_vacancy_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    vacancy_id = int(query.data.split('_')[-1])
    vacancy = db.get_vacancy(vacancy_id)

    if not vacancy or vacancy['customer_id'] != query.from_user.id:
        await query.edit_message_text("❌ Вакансия не найдена.")
        return

    if vacancy['is_paid']:
        await query.edit_message_text("✅ Оплата уже получена, вакансия опубликована.")
        return

    paid = await _check_and_activate_vacancy(vacancy_id, vacancy['payment_invoice_id'], context)
    if paid:
        await query.edit_message_text("✅ Оплата подтверждена! Вакансия опубликована.")
    else:
        await query.answer("⏳ Оплата пока не найдена", show_alert=True)


async def check_vacancy_payment_job(context: ContextTypes.DEFAULT_TYPE):
    vacancy_id = context.job.data['vacancy_id']
    invoice_id = context.job.data['invoice_id']

    paid = await _check_and_activate_vacancy(vacancy_id, invoice_id, context)
    if not paid:
        context.job_queue.run_once(
            check_vacancy_payment_job,
            when=30,
            data={"vacancy_id": vacancy_id, "invoice_id": invoice_id},
            name=f"check_vacancy_payment_{vacancy_id}"
        )


async def _check_and_activate_vacancy(vacancy_id: int, invoice_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    invoice = await crypto_bot.get_invoice(invoice_id)
    if not invoice or invoice.get('status') != 'paid':
        return False

    vacancy = db.get_vacancy(vacancy_id)
    if not vacancy or vacancy['is_paid']:
        return True

    db.mark_vacancy_paid(vacancy_id)

    try:
        await context.bot.send_message(
            chat_id=vacancy['customer_id'],
            text=f"✅ Ваша вакансия «{vacancy['title']}» опубликована и доступна фрилансерам."
        )
    except Exception:
        pass

    return True


async def my_vacancies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user or user['role'] == UserRole.FREELANCER.value:
        await update.message.reply_text("❌ Эта функция доступна только заказчику.")
        return

    await render_my_vacancies(update.message, context, 0)


async def render_my_vacancies(msg, context: ContextTypes.DEFAULT_TYPE, page: int):
    user_id = msg.from_user.id if hasattr(msg, 'from_user') else msg.callback_query.from_user.id
    total = db.count_customer_vacancies(user_id)

    if total == 0:
        text = "📭 У вас пока нет вакансий."
        if hasattr(msg, 'edit_message_text'):
            await msg.edit_message_text(text)
        else:
            await msg.reply_text(text)
        return

    page = max(0, min(page, total - 1))
    vacancy = db.get_customer_vacancies(user_id, limit=1, offset=page)[0]
    responses_count = db.count_vacancy_responses(vacancy['vacancy_id'])

    text = _format_vacancy(vacancy, page + 1, total)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"my_vacancy_{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total}", callback_data="page_info"))
    if page + 1 < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"my_vacancy_{page + 1}"))

    keyboard = [
        nav,
        [InlineKeyboardButton(f"👀 Отклики ({responses_count})", callback_data=f"vacancy_responses_{vacancy['vacancy_id']}_0")]
    ]

    if vacancy['status'] == 'open':
        keyboard.append([InlineKeyboardButton("🔒 Закрыть вакансию", callback_data=f"close_vacancy_{vacancy['vacancy_id']}")])

    if hasattr(msg, 'edit_message_text'):
        await msg.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await msg.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


def _format_vacancy(vacancy: dict, index: int = None, total: int = None) -> str:
    status = "🟢 Открыта" if vacancy['status'] == 'open' else "🔒 Закрыта"
    paid = "✅ Оплачена" if vacancy['is_paid'] else "⏳ Не оплачена"
    head = f"📢 <b>Вакансия {index} из {total}</b>\n\n" if index and total else "📢 <b>Вакансия</b>\n\n"
    return (
        f"{head}"
        f"<b>{vacancy['title']}</b>\n"
        f"{status} | {paid}\n\n"
        f"📝 {vacancy['description']}\n\n"
        f"✅ Требования:\n{vacancy['requirements']}\n\n"
        f"📞 Контакты: {vacancy['contact']}"
    )


async def my_vacancy_navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split('_')[2])
    await render_my_vacancies(query, context, page)


async def browse_vacancies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user or user['role'] == UserRole.CUSTOMER.value:
        await update.message.reply_text("❌ Эта функция доступна только фрилансерам.")
        return

    await render_open_vacancies(update.message, context, 0)


async def render_open_vacancies(msg, context: ContextTypes.DEFAULT_TYPE, page: int):
    total = db.count_open_vacancies()
    if total == 0:
        text = "😔 Открытых вакансий пока нет."
        if hasattr(msg, 'edit_message_text'):
            await msg.edit_message_text(text)
        else:
            await msg.reply_text(text)
        return

    page = max(0, min(page, total - 1))
    vacancy = db.get_open_vacancies(limit=1, offset=page)[0]

    text = _format_vacancy(vacancy, page + 1, total)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"browse_vacancy_{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total}", callback_data="page_info"))
    if page + 1 < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"browse_vacancy_{page + 1}"))

    keyboard = [
        [InlineKeyboardButton("✉️ Откликнуться", callback_data=f"respond_vacancy_{vacancy['vacancy_id']}")],
        nav,
    ]

    if hasattr(msg, 'edit_message_text'):
        await msg.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await msg.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def browse_vacancy_navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split('_')[2])
    await render_open_vacancies(query, context, page)


async def respond_vacancy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    vacancy_id = int(query.data.split('_')[2])
    vacancy = db.get_vacancy(vacancy_id)
    if not vacancy or vacancy['status'] != 'open' or not vacancy['is_paid']:
        await query.edit_message_text("❌ Вакансия недоступна для отклика.")
        return ConversationHandler.END

    context.user_data['respond_vacancy_id'] = vacancy_id
    await query.edit_message_text(
        f"✉️ <b>Отклик на вакансию:</b> {vacancy['title']}\n\n"
        "Напишите короткое сопроводительное сообщение:",
        parse_mode='HTML'
    )
    return VACANCY_DESCRIPTION


async def respond_vacancy_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    vacancy_id = context.user_data.get('respond_vacancy_id')
    if not vacancy_id:
        return ConversationHandler.END

    response_id = db.create_vacancy_response(
        vacancy_id=vacancy_id,
        freelancer_id=update.effective_user.id,
        cover_letter=update.message.text
    )

    if not response_id:
        await update.message.reply_text("❌ Вы уже откликались на эту вакансию.")
        context.user_data.pop('respond_vacancy_id', None)
        return ConversationHandler.END

    vacancy = db.get_vacancy(vacancy_id)
    await update.message.reply_text("✅ Отклик отправлен заказчику.")

    try:
        await context.bot.send_message(
            chat_id=vacancy['customer_id'],
            text=f"📨 Новый отклик на вакансию «{vacancy['title']}»",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "👀 Смотреть отклики",
                callback_data=f"vacancy_responses_{vacancy_id}_0"
            )]])
        )
    except Exception:
        pass

    context.user_data.pop('respond_vacancy_id', None)
    return ConversationHandler.END


async def close_vacancy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    vacancy_id = int(query.data.split('_')[2])
    vacancy = db.get_vacancy(vacancy_id)

    if not vacancy or vacancy['customer_id'] != query.from_user.id:
        await query.edit_message_text("❌ Вакансия не найдена.")
        return

    if vacancy['status'] == 'closed':
        await query.answer("Вакансия уже закрыта", show_alert=True)
        return

    db.close_vacancy(vacancy_id)
    pending_responses = db.get_vacancy_responses_by_status(vacancy_id, 'pending')

    for resp in pending_responses:
        try:
            await context.bot.send_message(
                chat_id=resp['freelancer_id'],
                text=f"🙏 Вакансия «{vacancy['title']}» закрылась.\n"
                     "Спасибо за отклик!"
            )
        except Exception:
            pass

    await query.edit_message_text("🔒 Вакансия закрыта. Непросмотренные кандидаты уведомлены.")


async def vacancy_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, _, vacancy_id, index = query.data.split('_')
    vacancy_id = int(vacancy_id)
    index = int(index)

    vacancy = db.get_vacancy(vacancy_id)
    if not vacancy or vacancy['customer_id'] != query.from_user.id:
        await query.edit_message_text("❌ Вакансия не найдена.")
        return

    responses = db.get_vacancy_responses(vacancy_id)
    if not responses:
        await query.edit_message_text("📭 На эту вакансию пока нет откликов.")
        return

    context.user_data['vacancy_responses_list'] = responses
    context.user_data['vacancy_responses_vacancy_id'] = vacancy_id
    await render_vacancy_response(query, context, index)


async def render_vacancy_response(msg, context: ContextTypes.DEFAULT_TYPE, index: int):
    responses = context.user_data.get('vacancy_responses_list', [])
    vacancy_id = context.user_data.get('vacancy_responses_vacancy_id')

    if not responses:
        return

    index = max(0, min(index, len(responses) - 1))
    response = responses[index]
    freelancer = db.get_user(response['freelancer_id'])
    vacancy = db.get_vacancy(vacancy_id)

    status_map = {
        'pending': '⏳ Ожидает решения',
        'invited': '📞 Приглашен на собеседование',
        'rejected': '❌ Отказ'
    }

    text = (
        f"📨 <b>Отклик {index + 1} из {len(responses)}</b>\n\n"
        f"👤 {freelancer['name']}\n"
        f"⭐ Рейтинг: {freelancer['rating']:.1f}\n"
        f"🔧 Навыки: {freelancer['skills'] or 'не указаны'}\n"
        f"📊 Статус: {status_map.get(response['status'], response['status'])}\n\n"
        f"💬 Сообщение:\n{response['cover_letter']}"
    )

    keyboard = []
    if response['status'] == 'pending' and vacancy['status'] == 'open':
        keyboard.append([
            InlineKeyboardButton("📞 Позвать на собес", callback_data=f"vacancy_invite_{response['response_id']}_{index}"),
            InlineKeyboardButton("❌ Отказать", callback_data=f"vacancy_reject_{response['response_id']}_{index}"),
        ])

    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"vacancy_responses_{vacancy_id}_{index - 1}"))
    nav.append(InlineKeyboardButton(f"{index + 1}/{len(responses)}", callback_data="page_info"))
    if index + 1 < len(responses):
        nav.append(InlineKeyboardButton("▶️", callback_data=f"vacancy_responses_{vacancy_id}_{index + 1}"))

    keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("◀️ К вакансии", callback_data="my_vacancy_0")])

    await msg.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def invite_vacancy_candidate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, _, response_id, index = query.data.split('_')
    response_id = int(response_id)
    index = int(index)

    response = db.get_vacancy_response(response_id)
    if not response:
        await query.edit_message_text("❌ Отклик не найден.")
        return

    vacancy = db.get_vacancy(response['vacancy_id'])
    if vacancy['customer_id'] != query.from_user.id:
        await query.edit_message_text("❌ Нет доступа.")
        return

    db.update_vacancy_response_status(response_id, 'invited')

    customer = db.get_user(vacancy['customer_id'])
    try:
        await context.bot.send_message(
            chat_id=response['freelancer_id'],
            text=(
                f"🎉 Вас пригласили на собеседование по вакансии «{vacancy['title']}»!\n\n"
                f"📞 Контакты заказчика: {vacancy['contact']}\n"
                f"👤 Заказчик: {customer['name']}"
            )
        )
    except Exception:
        pass

    refreshed = db.get_vacancy_responses(vacancy['vacancy_id'])
    context.user_data['vacancy_responses_list'] = refreshed
    await render_vacancy_response(query, context, index)


async def reject_vacancy_candidate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, _, response_id, index = query.data.split('_')
    response_id = int(response_id)
    index = int(index)

    response = db.get_vacancy_response(response_id)
    if not response:
        await query.edit_message_text("❌ Отклик не найден.")
        return

    vacancy = db.get_vacancy(response['vacancy_id'])
    if vacancy['customer_id'] != query.from_user.id:
        await query.edit_message_text("❌ Нет доступа.")
        return

    db.update_vacancy_response_status(response_id, 'rejected')

    try:
        await context.bot.send_message(
            chat_id=response['freelancer_id'],
            text=f"🙏 По вакансии «{vacancy['title']}» сейчас не готовы вас пригласить."
        )
    except Exception:
        pass

    refreshed = db.get_vacancy_responses(vacancy['vacancy_id'])
    context.user_data['vacancy_responses_list'] = refreshed
    await render_vacancy_response(query, context, index)
