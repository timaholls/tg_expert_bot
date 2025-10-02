import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Конфигурация бота
BOT_TOKEN = os.getenv('BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Проверяем наличие токенов
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")
    
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не найден в переменных окружения!")
