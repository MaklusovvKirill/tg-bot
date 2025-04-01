import asyncio
from aiogram import Bot
from aiogram import Dispatcher
from aiogram import types
from aiogram import F
from aiogram.utils import executor

API_TOKEN = '7541181061:AAHaKs0CXsP2JWHTBnn0h_nju1JsZen9BNU'


bot = Bot(token=API_TOKEN)
dp = Dispatcher()


def get_timer_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["10 секунд", "30 секунд", "1 минута", "5 минут"]
    keyboard.add(*buttons)
    return keyboard


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот-таймер. Нажмите кнопку ниже, чтобы установить таймер.", reply_markup=get_timer_keyboard())


@dp.message_handler(F.text.in_(["10 секунд", "30 секунд", "1 минута", "5 минут"]))
async def set_timer(message: types.Message):
    time_mapping = {
        "10 секунд": 10,
        "30 секунд": 30,
        "1 минута": 60,
        "5 минут": 300,
    }

    time_seconds = time_mapping[message.text]
    await message.answer(f"Таймер установлен на {time_seconds} секунд.")

    await asyncio.sleep(time_seconds)
    await message.answer("Время вышло!")


@dp.message_handler(commands=['cancel'])
async def cmd_cancel(message: types.Message):
    await message.answer("Таймер отменен.", reply_markup=types.ReplyKeyboardRemove())

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
