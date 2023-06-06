import logging

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ParseMode, PaymentInvoice, LabeledPrice, PreCheckoutQuery, \
    InputTextMessageContent, InlineQueryResultArticle, InlineQuery, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import TOKEN
from db import Database

logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)

# Инициализация диспетчера и хранилища данных
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Объявление базы данных
db = Database()


# Класс для хранения состояний пользователя во время работы с ботом
class PaymentStates(StatesGroup):
    awaiting_sum = State()  # Ожидание ввода суммы пополнения баланса
    awaiting_payment_approval = State()  # Ожидание подтверждения оплаты счета


# Команда /start
@dp.message_handler(Command("start"))
async def start(message: types.Message):
    name = message.from_user.first_name
    text = f"Привет, {name}\n\n" \
           "Я - бот для пополнения баланса.\n" \
           "Нажмите на кнопку, чтобы пополнить баланс"
    keyboard = InlineKeyboardMarkup(row_width=1)
    button = InlineKeyboardButton(text="Пополнить баланс", callback_data="top_up_balance")
    keyboard.add(button)
    await message.answer(text=text, reply_markup=keyboard)


# Обработка нажатия на кнопку пополнения баланса
@dp.callback_query_handler(text="top_up_balance", state=None)
async def top_up_balance(callback_query: types.CallbackQuery):
    await PaymentStates.awaiting_sum.set()
    text = "Введите сумму, на которую вы хотите пополнить баланс"
    await bot.send_message(chat_id=callback_query.from_user.id, text=text)


# Ожидание ввода суммы пополнения баланса
@dp.message_handler(state=PaymentStates.awaiting_sum)
async def process_sum(message: types.Message, state: FSMContext):
    try:
        sum = int(message.text)
        if sum <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("Сумма должна быть положительным числом")
        return

    # Создание нового счета для оплаты
    invoice = PaymentInvoice(currency="RUB", prices=[LabeledPrice(label="Баланс пополнения", amount=sum)],
                             need_shipping_address=False, is_flexible=True)
    # Отправка счета пользователю
    await bot.send_invoice(chat_id=message.from_user.id, title="Пополнение баланса", description="Пополнить баланс",
                            payload="top_up_balance", provider_token=db.get_payment_token(), start_parameter="test",
                            invoice_data=invoice)
    logging.info(f"{message.from_user.id} запросил пополнение баланса на сумму {sum}")
    await PaymentStates.awaiting_payment_approval.set()


# Обработка нажатия на кнопки после создания счета для оплаты
@dp.pre_checkout_query_handler(lambda pre_checkout_query: True)
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


# Обработка результатов оплаты счета
@dp.message_handler(content_types=["successful_payment"])
async def process_successful_payment(message: types.Message):
    user_id = message.successful_payment.from_user.id
    amount = message.successful_payment.total_amount
    await db.top_up_balance(user_id, amount)
    text = f"Баланс пополнен на {amount / 100:.2f} руб."
    await bot.send_message(chat_id=user_id, text=text)


# Обработка нажатия на кнопку проверки статуса оплаты
@dp.callback_query_handler(lambda callback_query: callback_query.data == "check_payment", state=None)
async def check_payment(callback_query: CallbackQuery):
    chat_id = callback_query.from_user.id
    payment = db.get_last_payment(chat_id)
    if payment is not None and payment.status == "successful":
        amount = payment.total_amount / 100
        await db.top_up_balance(chat_id, amount)
        text = f"Баланс пополнен на {amount:.2f} руб."
    else:
        text = "Платеж не прошел"
    await bot.send_message(chat_id=chat_id, text=text)


# Команда /admin
@dp.message_handler(Command("admin"))
async def start_admin(message: types.Message):
    # Проверка, является ли пользователь администратором
    if not db.is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к админ-панели")
        return

    keyboard = InlineKeyboardMarkup(row_width=1)
    users_button = InlineKeyboardButton(text="Пользователи", callback_data="show_users")
    logs_button = InlineKeyboardButton(text="Логи", callback_data="show_logs")
    keyboard.add(users_button, logs_button)
    await message.answer("Выберите раздел админ-панели:", reply_markup=keyboard)


# Обработка нажатия на кнопки разделов админ-панели
@dp.callback_query_handler(lambda callback_query: True)
async def admin_callback(query: CallbackQuery):
    data = query.data

    if data == "show_users":
        users = await db.get_users()
        text = "Список пользователей:\n\n"
        for user in users:
            text += f"{user['user_id']} - {user['balance']:.2f} руб.\n"
        await bot.send_message(chat_id=query.from_user.id, text=text)

    elif data == "show_logs":
        logs = await db.get_logs()
        text = "Логи ошибок и предупреждений:\n\n"
        for log in logs:
            text += f"{log['time']} - {log['level']} - {log['message']}\n"
        await bot.send_message(chat_id=query.from_user.id, text=text)

    elif data.startswith("top_up_balance"):
        user_id = int(data.split("_")[1])
        message_id = int(data.split("_")[2])
        sum = int(data.split("_")[3])

        # Создание нового счета для оплаты
        invoice = PaymentInvoice(currency="RUB", prices=[LabeledPrice(label="Баланс пополнения", amount=sum)],
                                 need_shipping_address=False, is_flexible=True)
        # Отправка счета пользователю
        await bot.send_invoice(chat_id=user_id, title="Пополнение баланса", description="Пополнить баланс",
                               payload="top_up_balance", provider_token=db.get_payment_token(),
                               start_parameter="test", invoice_data=invoice, reply_to_message_id=message_id)


# Обработка запросов Inline Query
@dp.inline_handler(lambda query: True)
async def process_inline_query(query: InlineQuery):
    user_id = query.from_user.id
    balance = db.get_balance(user_id)
    query_text = query.query

    if query_text.isdigit() and balance >= int(query_text):
        amount = int(query_text)
        # Создание нового счета для оплаты
        invoice = PaymentInvoice(currency="RUB", prices=[LabeledPrice(label="Баланс пополнения", amount=amount)],
                                 need_shipping_address=False, is_flexible=True)
        keyboard = InlineKeyboardMarkup(row_width=1)
        url_button = InlineKeyboardButton(text="Оплатить счет", url=invoice.invoice_url)
        check_button = InlineKeyboardButton(text="Проверить оплату", callback_data="check_payment")
        keyboard.add(url_button, check_button)
        results = [
            InlineQueryResultArticle(id="1", title="Пополнить баланс", input_message_content=InputTextMessageContent(
                message_text=f"Создан счет на пополнение баланса на сумму {amount:.2f} руб."), reply_markup=keyboard)]
    else:
        results = [InlineQueryResultArticle(id="1", title="Недостаточно средств",
                                            input_message_content=InputTextMessageContent(
                                                message_text=f"На вашем балансе {balance:.2f} руб. Необходимо больше."))]
    await bot.answer_inline_query(query.id, results, cache_time=0)

if __name__ == '__main__':
        logging.info("Starting bot")
        # Синхронизация базы данных
        db.init()
        # Запуск бота
        try:
            dp.run_forever()
        finally:
            # Закрытие соединения с базой данных
            db.close()
