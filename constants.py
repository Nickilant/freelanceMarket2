from enum import Enum

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
 TICKET_DESCRIPTION, WORK_DELIVERY, REVIEW_COMMENT,
 VACANCY_TITLE, VACANCY_DESCRIPTION, VACANCY_REQUIREMENTS, VACANCY_CONTACT,
 VACANCY_RESPONSE_TEXT) = range(26)

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
