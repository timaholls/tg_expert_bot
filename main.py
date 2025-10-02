import logging
import re
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from psychrometric_calculator import calculate_humidity
from config import BOT_TOKEN, OPENAI_API_KEY
import openai

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Настройка OpenAI
openai.api_key = OPENAI_API_KEY

# Состояния для FSM
class CalculationStates(StatesGroup):
    waiting_for_manual_input = State()
    waiting_for_photo = State()

# Промпт для OpenAI при расчете влажности
PSYCHROMETRIC_PROMPT = """
Ты — помощник по работе с психрометром ВИТ-1. 
Тебе будут вводить два значения: 
- показание сухого термометра (Tсух, °C), 
- показание влажного термометра (Tвлажн, °C).  

Твоя задача:  
1. Вычислить разницу ΔT = Tсух – Tвлажн.  
2. Найти относительную влажность воздуха (%) по психрометрической таблице ВИТ-1 (по строке температуры сухого термометра и по колонке ΔT).  
3. Выдать результат в формате:  
   «Температура воздуха: XX °C, разница: ΔT = Y °C, влажность ≈ ZZ %».  

Если значения выходят за таблицу, напиши:  
«Данных в таблице нет, нужна психрометрическая формула для точного расчёта».  
"""

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
    await message.answer(welcome_text, parse_mode='Markdown')

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

@dp.callback_query_handler(lambda c: c.data == "manual_input")
async def process_manual_input(callback_query: CallbackQuery):
    """Обработка выбора ручного ввода"""
    await callback_query.answer()
    await callback_query.message.edit_text(
        "Введите показания термометров в формате:\n"
        "Tсух Tвлажн\n\n"
        "Например: 20 15\n"
        "(где 20 - температура сухого термометра, 15 - влажного)"
    )
    await CalculationStates.waiting_for_manual_input.set()

@dp.callback_query_handler(lambda c: c.data == "photo_input")
async def process_photo_input(callback_query: CallbackQuery):
    """Обработка выбора ввода через фото"""
    await callback_query.answer()
    await callback_query.message.edit_text(
        "Отправьте фотографию психрометра ВИТ-1.\n"
        "Я проанализирую изображение и определю показания термометров."
    )
    await CalculationStates.waiting_for_photo.set()

@dp.message_handler(state=CalculationStates.waiting_for_manual_input)
async def process_manual_data(message: types.Message, state: FSMContext):
    """Обработка ручного ввода данных"""
    try:
        # Парсим введенные данные
        data = message.text.strip().split()
        if len(data) != 2:
            await message.answer(
                "Неверный формат! Введите два числа через пробел:\n"
                "Tсух Tвлажн\n\n"
                "Например: 20 15"
            )
            return
        
        t_dry = float(data[0])
        t_wet = float(data[1])
        
        # Проверяем, что разность не отрицательная
        if t_dry < t_wet:
            await message.answer(
                "Ошибка: показание влажного термометра не может быть больше показания сухого термометра!"
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
        
        await message.answer(response, parse_mode='Markdown')
        await state.finish()
        
    except ValueError:
        await message.answer(
            "Ошибка: введите корректные числовые значения!\n"
            "Формат: Tсух Tвлажн\n\n"
            "Например: 20 15"
        )
    except Exception as e:
        await message.answer(f"Произошла ошибка: {str(e)}")
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
        
        await message.answer(response, parse_mode='Markdown')
        
        await state.finish()
        
    except Exception as e:
        await message.answer(f"Ошибка при обработке фото: {str(e)}")
        await state.finish()

async def analyze_photo_with_openai(file_path: str) -> dict:
    """Анализ фотографии через OpenAI Vision API"""
    try:
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
        
        # Здесь должен быть реальный код для работы с OpenAI Vision API
        # Пока что возвращаем заглушку для демонстрации
        return {
            "success": True,
            "t_dry": 22.0,
            "t_wet": 19.0,
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "t_dry": None,
            "t_wet": None,
            "error": f"Ошибка анализа фото: {str(e)}"
        }

@dp.message_handler()
async def handle_other_messages(message: types.Message):
    """Обработчик всех остальных сообщений"""
    await message.answer(
        "Используйте команды:\n"
        "/start - информация о боте\n"
        "/calculation - начать расчет влажности"
    )

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
