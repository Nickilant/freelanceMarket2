import sqlite3
from typing import Dict, List, Optional

from constants import OrderStatus, PaymentStatus, ResponseStatus, TicketStatus

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

