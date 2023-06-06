import asyncpg

from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, PAYMENT_TOKEN


class Database:
    def __init__(self):
        self.pool = None

    async def create_pool(self):
        self.pool = await asyncpg.create_pool(database=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST,
                                              port=DB_PORT)

    async def init(self):
        # Создание таблиц в базе данных, если их нет
        await self.create_pool()
        await self.pool.execute("""CREATE TABLE IF NOT EXISTS users (
                                    user_id BIGINT PRIMARY KEY,
                                    balance DECIMAL(10,2) DEFAULT 0,
                                    is_admin BOOLEAN NOT NULL DEFAULT false
                                )""")
        await self.pool.execute("""CREATE TABLE IF NOT EXISTS payments (
                                    payment_id SERIAL PRIMARY KEY,
                                    user_id BIGINT NOT NULL,
                                    total_amount INTEGER NOT NULL,
                                    status VARCHAR(20) NOT NULL,
                                    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
                                )""")
        await self.pool.execute("""CREATE TABLE IF NOT EXISTS logs (
                                    id SERIAL PRIMARY KEY,
                                    time TIMESTAMP NOT NULL DEFAULT NOW(),
                                    level VARCHAR(10) NOT NULL,
                                    message TEXT NOT NULL
                                )""")

    async def close(self):
        # Закрытие соединения с базой данных
        await self.pool.close()

        async def log_message(self, level: str, message: str):
            # Логирование сообщения
            await self.pool.execute("INSERT INTO logs (level, message) VALUES ($1, $2)", level, message)

        async def get_users(self):
            # Получение списка пользователей
            return await self.pool.fetch("SELECT user_id, balance FROM users ORDER BY user_id")

        async def get_logs(self):
            # Получение логов
            return await self.pool.fetch("SELECT time, level, message FROM logs ORDER BY id DESC LIMIT 100")

        async def is_admin(self, user_id: int):
            # Проверка, является ли пользователь администратором
            row = await self.pool.fetchrow("SELECT is_admin FROM users WHERE user_id=$1", user_id)
            return row is not None and row[0]

        async def add_admin(self, user_id: int):
            # Добавление пользователя в список администраторов
            await self.pool.execute("INSERT INTO users (user_id, is_admin) VALUES ($1, true) ON CONFLICT DO NOTHING",
                                    user_id)

        async def remove_admin(self, user_id: int):
            # Удаление пользователя из списка администраторов
            await self.pool.execute("UPDATE users SET is_admin = false WHERE user_id=$1", user_id)

        async def get_balance(self, user_id: int):
            # Получение баланса пользователя
            row = await self.pool.fetchrow("SELECT balance FROM users WHERE user_id=$1", user_id)
            return row[0] if row is not None else 0

        async def top_up_balance(self, user_id: int, amount: int):
            # Пополнение баланса пользователя
            await self.pool.execute("UPDATE users SET balance = balance + $2 WHERE user_id=$1", user_id, amount)
            await self.pool.execute(
                "INSERT INTO payments (user_id, total_amount, status) VALUES ($1, $2, 'successful')",
                user_id, amount)

        async def get_last_payment(self, user_id: int):
            # Получение последней платежки пользователя
            return await self.pool.fetchrow("SELECT * FROM payments WHERE user_id=$1 ORDER BY payment_id DESC LIMIT 1")

        def get_payment_token(self):
            # Получение токена платежной системы
            return PAYMENT_TOKEN
