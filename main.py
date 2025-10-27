import logging
import re
import requests
import base64
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from psychrometric_calculator import calculate_humidity
from config import BOT_TOKEN, OPENAI_API_KEY
from openai import OpenAI

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Настройка OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)


# Состояния для FSM
class CalculationStates(StatesGroup):
    waiting_for_manual_input = State()
    waiting_for_photo = State()


@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    """Обработчик команды /start"""
    welcome_text = """
🌡️ *Добро пожаловать в бот-помощник по психрометру ВИТ-1!*

Я специализированный бот для определения влажности воздуха с помощью психрометра ВИТ-1.

*Что я умею:*
• Рассчитывать относительную влажность воздуха по показаниям сухого и влажного термометров
• Анализировать фотографии психрометра и определять параметры
• Работать как с ручным вводом данных, так и с фотографиями

*Доступные команды:*
/calculation - начать расчет влажности
/start - показать это сообщение

Для начала работы используйте команду /calculation
    """

    # Создаем инлайн кнопку для быстрого старта
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🚀 Начать расчет влажности", callback_data="start_calculation")
    )

    await message.answer(welcome_text, parse_mode='Markdown', reply_markup=keyboard)


@dp.message_handler(commands=['calculation'])
async def calculation_command(message: types.Message):
    """Обработчик команды /calculation"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📝 Вручную", callback_data="manual_input"),
        InlineKeyboardButton("📷 Фото", callback_data="photo_input")
    )

    await message.answer(
        "Выберите тип ввода данных:",
        reply_markup=keyboard
    )


@dp.callback_query_handler(lambda c: c.data == "start_calculation")
async def process_start_calculation(callback_query: CallbackQuery):
    """Обработка кнопки 'Начать расчет влажности'"""
    await callback_query.answer()

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📝 Вручную", callback_data="manual_input"),
        InlineKeyboardButton("📷 Фото", callback_data="photo_input")
    )

    await callback_query.message.edit_text(
        "Выберите тип ввода данных:",
        reply_markup=keyboard
    )


@dp.callback_query_handler(lambda c: c.data == "manual_input")
async def process_manual_input(callback_query: CallbackQuery):
    """Обработка выбора ручного ввода"""
    await callback_query.answer()

    # Создаем кнопку "Назад"
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
    )

    await callback_query.message.edit_text(
        "Введите показания термометров в формате:\n"
        "Tсух Tвлажн\n\n"
        "Например: 20 15\n"
        "(где 20 - температура сухого термометра, 15 - влажного)",
        reply_markup=keyboard
    )
    await CalculationStates.waiting_for_manual_input.set()


@dp.callback_query_handler(lambda c: c.data == "photo_input")
async def process_photo_input(callback_query: CallbackQuery):
    """Обработка выбора ввода через фото"""
    await callback_query.answer()

    # Создаем кнопку "Назад"
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
    )

    await callback_query.message.edit_text(
        "Отправьте фотографию психрометра ВИТ-1.\n"
        "Я проанализирую изображение и определю показания термометров.",
        reply_markup=keyboard
    )
    await CalculationStates.waiting_for_photo.set()


@dp.callback_query_handler(lambda c: c.data == "back_to_menu")
async def process_back_to_menu(callback_query: CallbackQuery):
    """Обработка кнопки 'Назад'"""
    await callback_query.answer()

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📝 Вручную", callback_data="manual_input"),
        InlineKeyboardButton("📷 Фото", callback_data="photo_input")
    )

    await callback_query.message.edit_text(
        "Выберите тип ввода данных:",
        reply_markup=keyboard
    )


@dp.message_handler(state=CalculationStates.waiting_for_manual_input)
async def process_manual_data(message: types.Message, state: FSMContext):
    """Обработка ручного ввода данных"""
    try:
        # Парсим введенные данные
        data = message.text.strip().split()
        if len(data) != 2:
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
            )

            await message.answer(
                "Неверный формат! Введите два числа через пробел:\n"
                "Tсух Tвлажн\n\n"
                "Например: 20 15",
                reply_markup=keyboard
            )
            return

        t_dry = float(data[0])
        t_wet = float(data[1])

        # Проверяем, что разность не отрицательная
        if t_dry < t_wet:
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
            )

            await message.answer(
                "Ошибка: показание влажного термометра не может быть больше показания сухого термометра!",
                reply_markup=keyboard
            )
            await state.finish()
            return

        # Рассчитываем влажность локально
        await message.answer("🔍 Рассчитываю влажность...")

        result = calculate_humidity(t_dry, t_wet)

        if result["success"]:
            response = f"🌡️ *Результат расчета:*\n\n"
            response += f"Температура воздуха: {result['t_dry']} °C\n"
            response += f"Разница: ΔT = {result['delta_t']} °C\n"
            response += f"Влажность ≈ {result['humidity']}%"
        else:
            response = f"❌ {result['error']}"

        # Создаем кнопки для дальнейших действий
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🔄 Новый расчет", callback_data="start_calculation"),
            InlineKeyboardButton("📝 Вручную", callback_data="manual_input")
        )

        await message.answer(response, parse_mode='Markdown', reply_markup=keyboard)
        await state.finish()

    except ValueError:
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
        )

        await message.answer(
            "Ошибка: введите корректные числовые значения!\n"
            "Формат: Tсух Tвлажн\n\n"
            "Например: 20 15",
            reply_markup=keyboard
        )
    except Exception as e:
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
        )

        await message.answer(f"Произошла ошибка: {str(e)}", reply_markup=keyboard)
        await state.finish()


@dp.message_handler(state=CalculationStates.waiting_for_photo, content_types=['photo'])
async def process_photo(message: types.Message, state: FSMContext):
    """Обработка фотографии психрометра"""
    try:
        # Получаем файл фотографии
        photo = message.photo[-1]  # Берем фото наибольшего размера
        file_info = await bot.get_file(photo.file_id)

        # Анализируем фото через OpenAI
        await message.answer("🔍 Анализирую фотографию через OpenAI...")

        # Получаем данные с фото через OpenAI
        photo_data = await analyze_photo_with_openai(file_info.file_path)

        if photo_data["success"]:
            await message.answer(
                f"📷 *Анализ фотографии:*\n\n"
                f"Показание сухого термометра: {photo_data['t_dry']}°C\n"
                f"Показание влажного термометра: {photo_data['t_wet']}°C\n\n"
                f"🔍 Рассчитываю влажность по таблице..."
            )

            # Рассчитываем влажность по локальной таблице
            result = calculate_humidity(photo_data['t_dry'], photo_data['t_wet'])

            if result["success"]:
                response = f"🌡️ *Результат расчета:*\n\n"
                response += f"Температура воздуха: {result['t_dry']} °C\n"
                response += f"Разница: ΔT = {result['delta_t']} °C\n"
                response += f"Влажность ≈ {result['humidity']}%"
            else:
                response = f"❌ {result['error']}"
        else:
            response = f"❌ Ошибка анализа фото: {photo_data['error']}"

        # Создаем кнопки для дальнейших действий
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🔄 Новый расчет", callback_data="start_calculation"),
            InlineKeyboardButton("📷 Фото", callback_data="photo_input")
        )

        await message.answer(response, parse_mode='Markdown', reply_markup=keyboard)

        await state.finish()

    except Exception as e:
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
        )

        await message.answer(f"Ошибка при обработке фото: {str(e)}", reply_markup=keyboard)
        await state.finish()


async def analyze_photo_with_openai(file_path: str) -> dict:
    """Анализ фотографии через OpenAI Vision API"""
    try:
        logging.info(f"🔍 Начинаю анализ фото: {file_path}")
        
        # Промпт для анализа фото психрометра
        photo_prompt = """
        Проанализируй фотографию психрометра ВИТ-1 и определи показания термометров.

        ВАЖНО: Ответь СТРОГО в формате:
        СУХОЙ: XX.X
        ВЛАЖНЫЙ: XX.X

        Где XX.X - это температура в градусах Цельсия с точностью до 0.5°C.

        Если не можешь определить показания, ответь:
        ОШИБКА: Не удалось определить показания термометров
        """

        # Получаем URL файла
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        logging.info(f"📥 Скачиваю фото с URL: {file_url}")
        
        # Скачиваем изображение
        response = requests.get(file_url)
        logging.info(f"📊 Статус скачивания: {response.status_code}")
        
        if response.status_code != 200:
            logging.error(f"❌ Ошибка скачивания фото: {response.status_code}")
            return {
                "success": False,
                "t_dry": None,
                "t_wet": None,
                "error": "Не удалось скачать изображение"
            }
        
        # Кодируем изображение в base64
        image_base64 = base64.b64encode(response.content).decode('utf-8')
        logging.info(f"🔄 Изображение закодировано в base64, размер: {len(image_base64)} символов")
        
        # Отправляем запрос в OpenAI Vision API с новым синтаксисом
        logging.info("🧠 Отправляю запрос в OpenAI Vision API...")
        openai_response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": photo_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=100
        )
        
        # Парсим ответ от OpenAI
        ai_response = openai_response.choices[0].message.content.strip()
        logging.info(f"🤖 Ответ от OpenAI: {ai_response}")
        
        # Извлекаем данные из ответа
        lines = ai_response.split('\n')
        t_dry = None
        t_wet = None
        
        logging.info(f"📝 Парсинг ответа, строк: {len(lines)}")
        
        for line in lines:
            line = line.strip()
            logging.info(f"🔍 Обрабатываю строку: '{line}'")
            
            if line.startswith('СУХОЙ:'):
                try:
                    t_dry = float(line.split(':')[1].strip())
                    logging.info(f"✅ Найден сухой термометр: {t_dry}°C")
                except (ValueError, IndexError) as e:
                    logging.error(f"❌ Ошибка парсинга сухого термометра: {e}")
                    pass
            elif line.startswith('ВЛАЖНЫЙ:'):
                try:
                    t_wet = float(line.split(':')[1].strip())
                    logging.info(f"✅ Найден влажный термометр: {t_wet}°C")
                except (ValueError, IndexError) as e:
                    logging.error(f"❌ Ошибка парсинга влажного термометра: {e}")
                    pass
            elif line.startswith('ОШИБКА:'):
                logging.error("❌ OpenAI сообщил об ошибке распознавания")
                return {
                    "success": False,
                    "t_dry": None,
                    "t_wet": None,
                    "error": "OpenAI не смог определить показания термометров"
                }
        
        # Проверяем, что получили оба значения
        logging.info(f"📊 Результат парсинга - Сухой: {t_dry}, Влажный: {t_wet}")
        
        if t_dry is None or t_wet is None:
            logging.error(f"❌ Не удалось извлечь данные из ответа: {ai_response}")
            return {
                "success": False,
                "t_dry": None,
                "t_wet": None,
                "error": f"Не удалось извлечь данные из ответа OpenAI: {ai_response}"
            }
        
        # Проверяем корректность значений
        if t_dry < t_wet:
            logging.error(f"❌ Логическая ошибка: сухой ({t_dry}) < влажный ({t_wet})")
            return {
                "success": False,
                "t_dry": None,
                "t_wet": None,
                "error": "Показание влажного термометра не может быть больше показания сухого термометра"
            }
        
        logging.info(f"✅ Успешный анализ: Сухой {t_dry}°C, Влажный {t_wet}°C")
        return {
            "success": True,
            "t_dry": t_dry,
            "t_wet": t_wet,
            "error": None
        }

    except Exception as e:
        logging.error(f"💥 Критическая ошибка анализа фото: {str(e)}")
        return {
            "success": False,
            "t_dry": None,
            "t_wet": None,
            "error": f"Ошибка анализа фото: {str(e)}"
        }


@dp.message_handler()
async def handle_other_messages(message: types.Message):
    """Обработчик всех остальных сообщений"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🚀 Начать расчет влажности", callback_data="start_calculation")
    )

    await message.answer(
        "Используйте команды:\n"
        "/start - информация о боте\n"
        "/calculation - начать расчет влажности",
        reply_markup=keyboard
    )


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
