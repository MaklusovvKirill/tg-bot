import telebot
from telebot import types
import sqlite3
import datetime
import threading
import time
import os

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8136190646:AAFsj8cIZ2pGOzWkUWO2IW63aLutko2pHFE"  # ЗАМЕНИТЕ НА ВАШ ТОКЕН
DATABASE_NAME = 'reminders_bot.db'
TELEGRAPH_DOCUMENTATION_URL = 'https://telegra.ph/Tut-mogla-byt-vasha-dokumenta-05-13' # ЗАМЕНИТЕ НА ВАШУ ССЫЛКУ

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
bot = telebot.TeleBot(BOT_TOKEN)

# --- УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ ---
def init_db():
    """Инициализирует базу данных и создает таблицу, если она не существует."""
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL,  -- ID пользователя, создавшего напоминание
            target_chat_id INTEGER NOT NULL, -- ID чата для отправки (личный или канал)
            target_type TEXT NOT NULL, -- 'user' или 'channel'
            reminder_datetime TEXT NOT NULL,
            text TEXT NOT NULL,
            photo_id TEXT,
            is_sent INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def add_reminder_to_db(creator_id, target_chat_id, target_type, reminder_datetime, text, photo_id=None):
    """Добавляет новое напоминание в базу данных."""
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO reminders (creator_id, target_chat_id, target_type, reminder_datetime, text, photo_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (creator_id, target_chat_id, target_type, reminder_datetime.strftime('%Y-%m-%d %H:%M:%S'), text, photo_id))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Ошибка при добавлении напоминания в БД: {e}")
    finally:
        conn.close()

def get_user_reminders(creator_id, include_sent=False):
    """Получает все напоминания, созданные пользователем, из БД."""
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cursor = conn.cursor()
    try:
        query = '''
            SELECT id, target_chat_id, target_type, reminder_datetime, text, photo_id, is_sent FROM reminders
            WHERE creator_id = ?
        '''
        params = [creator_id]
        if not include_sent:
            query += ' AND is_sent = 0'
        query += ' ORDER BY reminder_datetime ASC'

        cursor.execute(query, tuple(params))
        reminders = cursor.fetchall()
        return reminders
    except sqlite3.Error as e:
        print(f"Ошибка при получении напоминаний из БД: {e}")
        return []
    finally:
        conn.close()

def get_nearest_personal_reminder(creator_id):
    """Получает ближайшее активное ЛИЧНОЕ напоминание пользователя."""
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cursor = conn.cursor()
    try:
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            SELECT id, reminder_datetime, text, photo_id FROM reminders
            WHERE creator_id = ? AND target_type = 'user' AND is_sent = 0 AND reminder_datetime > ?
            ORDER BY reminder_datetime ASC LIMIT 1
        ''', (creator_id, now_str))
        reminder = cursor.fetchone()
        return reminder
    except sqlite3.Error as e:
        print(f"Ошибка при получении ближайшего личного напоминания: {e}")
        return None
    finally:
        conn.close()

def mark_reminder_as_sent(reminder_id):
    """Помечает напоминание как отправленное."""
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE reminders SET is_sent = 1 WHERE id = ?
        ''', (reminder_id,))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Ошибка при обновлении статуса напоминания: {e}")
    finally:
        conn.close()

# --- ОСНОВНЫЕ КНОПКИ МЕНЮ ---
def get_main_keyboard():
    """Возвращает основную клавиатуру для личного чата."""
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    btn_docs = types.KeyboardButton("📖 Документация")
    btn_new_reminder = types.KeyboardButton("➕ Создать новую напоминалку")
    btn_all_reminders = types.KeyboardButton("📋 Все напоминалки")
    markup.add(btn_new_reminder, btn_all_reminders, btn_docs)
    return markup

# --- ОБРАБОТЧИКИ КОМАНД И СООБЩЕНИЙ ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if message.chat.type == "private":
        user_name = message.from_user.first_name
        welcome_text = (
            f"Привет, {user_name}!\n\n"
            "Я твой бот для создания напоминаний. "
            "Ты можешь создавать напоминания для себя или для каналов, где ты администратор.\n\n"
            "Используй кнопки ниже для управления.\n\n"
            "Если меня упомянуть в групповом чате, "
            "я покажу твое ближайшее активное ЛИЧНОЕ напоминание."
        )
        bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_keyboard())
    else:
        bot.reply_to(message, "Для использования основных функций, пожалуйста, напишите мне в личные сообщения.")

@bot.message_handler(func=lambda message: message.chat.type == "private" and message.text == "📖 Документация")
def show_documentation(message):
    bot.send_message(message.chat.id,
                     f"Полная документация по работе с ботом доступна здесь: {TELEGRAPH_DOCUMENTATION_URL}",
                     reply_markup=get_main_keyboard())

user_data = {} # Словарь для хранения временных данных при создании напоминания

@bot.message_handler(func=lambda message: message.chat.type == "private" and message.text == "➕ Создать новую напоминалку")
def create_new_reminder_start(message):
    user_id = message.from_user.id
    user_data[user_id] = {'creator_id': user_id} # Сохраняем ID создателя
    msg = bot.send_message(message.chat.id,
                           "Хорошо! Давай создадим напоминание.\n\n"
                           "Пожалуйста, введи дату напоминания в формате ГГГГ-ММ-ДД (например, 2025-12-31):",
                           reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, process_date_step)

def process_date_step(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        date_str = message.text
        datetime.datetime.strptime(date_str, '%Y-%m-%d')
        user_data[user_id]['date'] = date_str
        msg = bot.send_message(chat_id,
                               "Отлично! Теперь введи время в формате ЧЧ:ММ (например, 14:30):")
        bot.register_next_step_handler(msg, process_time_step)
    except ValueError:
        msg = bot.send_message(chat_id,
                               "Неверный формат даты. Пожалуйста, попробуй еще раз в формате ГГГГ-ММ-ДД (например, 2025-07-15):")
        bot.register_next_step_handler(msg, process_date_step)
    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка: {e}. Попробуйте начать сначала.", reply_markup=get_main_keyboard())
        if user_id in user_data: del user_data[user_id]

def process_time_step(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        time_str = message.text
        datetime.datetime.strptime(time_str, '%H:%M')
        user_data[user_id]['time'] = time_str

        reminder_dt_str = f"{user_data[user_id]['date']} {user_data[user_id]['time']}"
        reminder_dt = datetime.datetime.strptime(reminder_dt_str, '%Y-%m-%d %H:%M')

        if reminder_dt < datetime.datetime.now():
            msg = bot.send_message(chat_id,
                                   "Это время уже прошло! Пожалуйста, введите будущую дату и время.\n"
                                   "Начнем сначала с даты (ГГГГ-ММ-ДД):")
            # Сбрасываем только дату и время, но не creator_id
            if 'date' in user_data[user_id]: del user_data[user_id]['date']
            if 'time' in user_data[user_id]: del user_data[user_id]['time']
            bot.register_next_step_handler(msg, process_date_step)
            return

        msg = bot.send_message(chat_id,
                               "Теперь введи текст напоминания:")
        bot.register_next_step_handler(msg, process_text_step)
    except ValueError:
        msg = bot.send_message(chat_id,
                               "Неверный формат времени. Пожалуйста, попробуй еще раз в формате ЧЧ:ММ (например, 09:00):")
        bot.register_next_step_handler(msg, process_time_step)
    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка: {e}. Попробуйте начать сначала.", reply_markup=get_main_keyboard())
        if user_id in user_data: del user_data[user_id]

def process_text_step(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        text = message.text
        if not text:
            msg = bot.send_message(chat_id, "Текст напоминания не может быть пустым. Пожалуйста, введите текст:")
            bot.register_next_step_handler(msg, process_text_step)
            return

        user_data[user_id]['text'] = text

        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
        btn_yes = types.KeyboardButton("Да, с фото")
        btn_no = types.KeyboardButton("Нет, без фото")
        markup.add(btn_yes, btn_no)
        msg = bot.send_message(chat_id, "Хочешь добавить фото к напоминанию?", reply_markup=markup)
        bot.register_next_step_handler(msg, process_photo_choice_step)
    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка: {e}. Попробуйте начать сначала.", reply_markup=get_main_keyboard())
        if user_id in user_data: del user_data[user_id]

def process_photo_choice_step(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        choice = message.text.lower()
        if "да" in choice:
            msg = bot.send_message(chat_id, "Отлично! Отправь мне фото.", reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, process_photo_step)
        elif "нет" in choice:
            user_data[user_id]['photo_id'] = None
            ask_target_type(message) # Переход к следующему шагу
        else:
            markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
            btn_yes = types.KeyboardButton("Да, с фото")
            btn_no = types.KeyboardButton("Нет, без фото")
            markup.add(btn_yes, btn_no)
            msg = bot.send_message(chat_id, "Пожалуйста, выбери 'Да, с фото' или 'Нет, без фото'.", reply_markup=markup)
            bot.register_next_step_handler(msg, process_photo_choice_step)
    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка: {e}. Попробуйте начать сначала.", reply_markup=get_main_keyboard())
        if user_id in user_data: del user_data[user_id]

def process_photo_step(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        if message.content_type == 'photo':
            photo_id = message.photo[-1].file_id
            user_data[user_id]['photo_id'] = photo_id
            ask_target_type(message) # Переход к следующему шагу
        else:
            msg = bot.send_message(chat_id, "Это не фото. Пожалуйста, отправь фото или напиши /skip_photo, если передумал (напоминание будет без фото).")
            bot.register_next_step_handler(msg, process_photo_step_skip_handler) # Нужен новый обработчик для /skip_photo
    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка при обработке фото: {e}. Напоминание будет создано без фото.", reply_markup=get_main_keyboard())
        user_data[user_id]['photo_id'] = None
        ask_target_type(message) # Все равно переходим к следующему шагу

def process_photo_step_skip_handler(message): # Обработчик для /skip_photo или нового фото
    if message.text and message.text.lower() == '/skip_photo':
        user_data[message.from_user.id]['photo_id'] = None
        ask_target_type(message)
    elif message.content_type == 'photo':
        process_photo_step(message) # Обрабатываем как фото
    else:
        msg = bot.send_message(message.chat.id, "Пожалуйста, отправь фото или напиши /skip_photo.")
        bot.register_next_step_handler(msg, process_photo_step_skip_handler)

def ask_target_type(message):
    """Спрашивает, куда отправить напоминание."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    btn_personal = types.KeyboardButton("Лично мне")
    btn_channel = types.KeyboardButton("В канал")
    markup.add(btn_personal, btn_channel)
    msg = bot.send_message(chat_id, "Куда отправить это напоминание?", reply_markup=markup)
    bot.register_next_step_handler(msg, process_target_type_choice)

def process_target_type_choice(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        choice = message.text
        if choice == "Лично мне":
            user_data[user_id]['target_type'] = 'user'
            user_data[user_id]['target_chat_id'] = user_id # Отправляем создателю в личку
            save_reminder(user_id, chat_id)
        elif choice == "В канал":
            user_data[user_id]['target_type'] = 'channel'
            msg = bot.send_message(chat_id,
                                   "Хорошо. Теперь отправь мне ID канала (например, `@my_channel` или `-1001234567890`).\n"
                                   "Убедись, что я добавлен в этот канал и ты являешься его администратором.",
                                   reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, process_channel_id_step)
        else:
            markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
            btn_personal = types.KeyboardButton("Лично мне")
            btn_channel = types.KeyboardButton("В канал")
            markup.add(btn_personal, btn_channel)
            msg = bot.send_message(chat_id, "Пожалуйста, выбери 'Лично мне' или 'В канал'.", reply_markup=markup)
            bot.register_next_step_handler(msg, process_target_type_choice)
    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка: {e}. Попробуйте начать сначала.", reply_markup=get_main_keyboard())
        if user_id in user_data: del user_data[user_id]

def process_channel_id_step(message):
    user_id = message.from_user.id # Это creator_id
    chat_id = message.chat.id # Это личный чат с ботом
    channel_input = message.text

    try:
        # Пытаемся получить информацию о канале, чтобы проверить его существование и права бота
        # channel_input может быть @username или числовым ID
        target_channel_info = bot.get_chat(channel_input)
        target_channel_id = target_channel_info.id
        user_data[user_id]['target_chat_id'] = target_channel_id

        # Проверка, является ли создатель напоминания администратором канала
        member = bot.get_chat_member(target_channel_id, user_id)
        if member.status not in ['administrator', 'creator']:
            bot.send_message(chat_id,
                             "Ошибка: Ты не являешься администратором в указанном канале. "
                             "Напоминание не может быть создано для этого канала. Попробуй снова или выбери другой канал.",
                             reply_markup=get_main_keyboard())
            if user_id in user_data: del user_data[user_id]
            return

        # Проверка, есть ли бот в канале (get_chat_member для бота)
        bot_member = bot.get_chat_member(target_channel_id, bot.get_me().id)
        if not bot_member or bot_member.status == 'left' or bot_member.status == 'kicked':
             bot.send_message(chat_id,
                             f"Ошибка: Меня нет в канале {channel_input} или у меня нет прав. "
                             "Пожалуйста, добавь меня в канал. Напоминание не создано.",
                             reply_markup=get_main_keyboard())
             if user_id in user_data: del user_data[user_id]
             return


        save_reminder(user_id, chat_id) # chat_id здесь - это личный чат пользователя, где он создает напоминание

    except telebot.apihelper.ApiTelegramException as e:
        if "chat not found" in str(e).lower():
            msg = bot.send_message(chat_id,
                                   f"Канал '{channel_input}' не найден или недоступен. "
                                   "Убедись, что ID или username верны и я добавлен в канал. Попробуй еще раз:")
            bot.register_next_step_handler(msg, process_channel_id_step)
        else:
            bot.send_message(chat_id, f"Ошибка при проверке канала: {e}. Попробуйте снова.", reply_markup=get_main_keyboard())
            if user_id in user_data: del user_data[user_id]
    except Exception as e:
        bot.send_message(chat_id, f"Произошла непредвиденная ошибка: {e}. Попробуйте начать сначала.", reply_markup=get_main_keyboard())
        if user_id in user_data: del user_data[user_id]


def save_reminder(user_id, original_chat_id): # original_chat_id - это ID личного чата с ботом
    """Сохраняет напоминание в БД и оповещает пользователя."""
    try:
        data = user_data.get(user_id)
        if not data or not all(k in data for k in ['creator_id', 'date', 'time', 'text', 'target_type', 'target_chat_id']):
            bot.send_message(original_chat_id, "Что-то пошло не так при сборе данных. Попробуйте создать напоминание заново.", reply_markup=get_main_keyboard())
            if user_id in user_data: del user_data[user_id]
            return

        reminder_datetime_str = f"{data['date']} {data['time']}"
        reminder_datetime_obj = datetime.datetime.strptime(reminder_datetime_str, '%Y-%m-%d %H:%M')

        add_reminder_to_db(
            data['creator_id'],
            data['target_chat_id'],
            data['target_type'],
            reminder_datetime_obj,
            data['text'],
            data.get('photo_id')
        )

        target_description = "лично тебе" if data['target_type'] == 'user' else f"в канал {data['target_chat_id']}"
        if data['target_type'] == 'channel':
            try:
                # Попробуем получить имя канала для более дружелюбного сообщения
                channel_info = bot.get_chat(data['target_chat_id'])
                target_description = f"в канал '{channel_info.title or channel_info.username}' ({data['target_chat_id']})"
            except:
                pass # Если не получилось, оставим ID

        bot.send_message(original_chat_id, # Отправляем подтверждение в личный чат
                         f"Напоминание создано!\n"
                         f"Будет отправлено: {target_description}\n"
                         f"Дата: {data['date']}\n"
                         f"Время: {data['time']}\n"
                         f"Текст: {data['text']}\n"
                         f"{'Фото добавлено.' if data.get('photo_id') else 'Без фото.'}",
                         reply_markup=get_main_keyboard())
    except ValueError:
        bot.send_message(original_chat_id, "Ошибка в дате или времени. Пожалуйста, начните создание напоминания заново.", reply_markup=get_main_keyboard())
    except Exception as e:
        bot.send_message(original_chat_id, f"Произошла критическая ошибка при сохранении: {e}. Попробуйте снова.", reply_markup=get_main_keyboard())
    finally:
        if user_id in user_data:
            del user_data[user_id]


@bot.message_handler(func=lambda message: message.chat.type == "private" and message.text == "📋 Все напоминалки")
def show_all_reminders(message):
    user_id = message.from_user.id
    reminders = get_user_reminders(user_id, include_sent=False)

    if not reminders:
        bot.send_message(message.chat.id, "У тебя пока нет активных напоминаний.", reply_markup=get_main_keyboard())
        return

    response_text = "Твои активные напоминания:\n\n"
    for i, reminder in enumerate(reminders):
        r_id, r_target_chat_id, r_target_type, r_dt_str, r_text, r_photo_id, r_is_sent = reminder
        try:
            r_dt_obj = datetime.datetime.strptime(r_dt_str, '%Y-%m-%d %H:%M:%S')
            formatted_dt = r_dt_obj.strftime('%d.%m.%Y в %H:%M')
        except ValueError:
            formatted_dt = r_dt_str

        target_desc = "Тебе" if r_target_type == 'user' else f"В канал ({r_target_chat_id})"
        if r_target_type == 'channel':
             try:
                channel_info = bot.get_chat(r_target_chat_id)
                target_desc = f"В канал '{channel_info.title or channel_info.username}'"
             except:
                pass


        response_text += (
            f"{i+1}. Куда: {target_desc}\n"
            f"   Дата: {formatted_dt}\n"
            f"   Текст: {r_text}\n"
            f"{'   (с фото)' if r_photo_id else ''}\n\n"
        )
        if len(response_text) > 3500:
            bot.send_message(message.chat.id, response_text, reply_markup=get_main_keyboard())
            response_text = ""

    if response_text:
        bot.send_message(message.chat.id, response_text, reply_markup=get_main_keyboard())


@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_mention(message):
    if message.chat.type in ["group", "supergroup"]:
        bot_username = bot.get_me().username
        mentioned = False
        if message.text and f"@{bot_username}" in message.text:
            mentioned = True
        if not mentioned and message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    mention_text = message.text[entity.offset : entity.offset + entity.length]
                    if mention_text == f"@{bot_username}":
                        mentioned = True
                        break
        
        if mentioned:
            user_id = message.from_user.id # ID того, кто упомянул
            # Показываем только ближайшее ЛИЧНОЕ напоминание
            reminder_tuple = get_nearest_personal_reminder(user_id)
            if reminder_tuple:
                r_id, r_dt_str, r_text, r_photo_id = reminder_tuple
                try:
                    r_dt_obj = datetime.datetime.strptime(r_dt_str, '%Y-%m-%d %H:%M:%S')
                    formatted_dt = r_dt_obj.strftime('%d.%m.%Y в %H:%M')
                except ValueError:
                    formatted_dt = r_dt_str

                reply_text = (
                    f"@{message.from_user.username}, твое ближайшее личное напоминание:\n"
                    f"📅 {formatted_dt}\n"
                    f"📝 {r_text}"
                )
                if r_photo_id:
                    try:
                        bot.send_photo(message.chat.id, r_photo_id, caption=reply_text, reply_to_message_id=message.message_id)
                    except Exception as e:
                        print(f"Ошибка отправки фото в группе (упоминание): {e}")
                        bot.reply_to(message, reply_text + "\n(Не удалось отправить фото)")
                else:
                    bot.reply_to(message, reply_text)
            else:
                bot.reply_to(message, f"@{message.from_user.username}, у тебя нет предстоящих личных напоминаний.")


# --- ФОНОВЫЙ ПРОЦЕСС ПРОВЕРКИ НАПОМИНАНИЙ ---
def reminder_checker():
    print("Проверка напоминаний запущена...")
    while True:
        conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
        cursor = conn.cursor()
        now = datetime.datetime.now()
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')

        try:
            cursor.execute('''
                SELECT id, creator_id, target_chat_id, target_type, reminder_datetime, text, photo_id FROM reminders
                WHERE reminder_datetime <= ? AND is_sent = 0
            ''', (now_str,))
            due_reminders = cursor.fetchall()

            for reminder_data in due_reminders:
                r_id, creator_id, target_chat_id, target_type, r_dt_str, text, photo_id = reminder_data
                
                reminder_dt_obj = datetime.datetime.strptime(r_dt_str, '%Y-%m-%d %H:%M:%S')
                if now - reminder_dt_obj > datetime.timedelta(days=1):
                    print(f"Пропущено старое напоминание ID {r_id} для {target_type} {target_chat_id}")
                    mark_reminder_as_sent(r_id)
                    continue

                message_text = text # По умолчанию текст без префикса "НАПОМИНАНИЕ"
                if target_type == 'user':
                    message_text = f"🔔 НАПОМИНАНИЕ 🔔\n\n{text}" # Для личных оставляем префикс

                try:
                    if photo_id:
                        bot.send_photo(target_chat_id, photo_id, caption=message_text)
                    else:
                        bot.send_message(target_chat_id, message_text)
                    
                    mark_reminder_as_sent(r_id)
                    print(f"Отправлено напоминание ID {r_id} в {target_type} {target_chat_id}")
                except telebot.apihelper.ApiTelegramException as e:
                    print(f"Ошибка API Telegram при отправке напоминания ID {r_id} в {target_chat_id}: {e}")
                    error_str = str(e).lower()
                    if "bot was blocked by the user" in error_str or \
                       "chat not found" in error_str or \
                       "user is deactivated" in error_str or \
                       "bot is not a member of the channel" in error_str or \
                       "bot can't initiate conversation with a user" in error_str or \
                       "need administrator rights in the channel" in error_str or \
                       "group chat was deactivated" in error_str or \
                       "bot was kicked from the channel" in error_str or \
                       "bot was kicked from the supergroup" in error_str or \
                       "chat_admin_required" in error_str: # Общее право
                        mark_reminder_as_sent(r_id)
                        print(f"Напоминание ID {r_id} помечено как отправленное из-за ошибки доступа к чату/каналу: {target_chat_id}")
                except Exception as e:
                    print(f"Не удалось отправить напоминание ID {r_id} в {target_chat_id}: {e}")
        except sqlite3.Error as e:
            print(f"Ошибка БД в reminder_checker: {e}")
        finally:
            conn.close()
        
        time.sleep(20) # Уменьшил интервал для более быстрого срабатывания, можно вернуть на 30

# --- ЗАПУСК БОТА ---
if __name__ == '__main__':
    print("Инициализация базы данных...")
    init_db() # Убедитесь, что эта функция вызвана ДО первого обращения к БД
    print("База данных инициализирована.")

    checker_thread = threading.Thread(target=reminder_checker, daemon=True)
    checker_thread.start()

    print("Бот запускается...")
    try:
        bot.polling(none_stop=True, interval=0)
    except Exception as e:
        print(f"Критическая ошибка бота: {e}")
    finally:
        print("Бот остановлен.")
