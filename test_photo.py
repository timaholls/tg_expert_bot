#!/usr/bin/env python3
"""
Тестовый скрипт для анализа фото психрометра через OpenAI Vision API
"""

import logging
import base64
import requests
from openai import OpenAI
from config import OPENAI_API_KEY

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Инициализация OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

def analyze_photo_test(image_path: str) -> dict:
    """Тестовая функция анализа фотографии"""
    try:
        logging.info(f"🔍 Начинаю тестовый анализ фото: {image_path}")
        
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

        # Читаем изображение из файла
        logging.info(f"📥 Читаю файл: {image_path}")
        with open(image_path, 'rb') as image_file:
            image_data = image_file.read()
        
        logging.info(f"📊 Размер файла: {len(image_data)} байт")
        
        # Кодируем изображение в base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        logging.info(f"🔄 Изображение закодировано в base64, размер: {len(image_base64)} символов")
        
        # Отправляем запрос в OpenAI Vision API
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
                    "error": "OpenAI не смог определить показания термометров",
                    "raw_response": ai_response
                }
        
        # Проверяем, что получили оба значения
        logging.info(f"📊 Результат парсинга - Сухой: {t_dry}, Влажный: {t_wet}")
        
        if t_dry is None or t_wet is None:
            logging.error(f"❌ Не удалось извлечь данные из ответа: {ai_response}")
            return {
                "success": False,
                "t_dry": None,
                "t_wet": None,
                "error": f"Не удалось извлечь данные из ответа OpenAI: {ai_response}",
                "raw_response": ai_response
            }
        
        # Проверяем корректность значений
        if t_dry < t_wet:
            logging.error(f"❌ Логическая ошибка: сухой ({t_dry}) < влажный ({t_wet})")
            return {
                "success": False,
                "t_dry": None,
                "t_wet": None,
                "error": "Показание влажного термометра не может быть больше показания сухого термометра",
                "raw_response": ai_response
            }
        
        logging.info(f"✅ Успешный анализ: Сухой {t_dry}°C, Влажный {t_wet}°C")
        return {
            "success": True,
            "t_dry": t_dry,
            "t_wet": t_wet,
            "error": None,
            "raw_response": ai_response
        }

    except FileNotFoundError:
        logging.error(f"❌ Файл не найден: {image_path}")
        return {
            "success": False,
            "t_dry": None,
            "t_wet": None,
            "error": f"Файл не найден: {image_path}",
            "raw_response": None
        }
    except Exception as e:
        logging.error(f"💥 Критическая ошибка анализа фото: {str(e)}")
        return {
            "success": False,
            "t_dry": None,
            "t_wet": None,
            "error": f"Ошибка анализа фото: {str(e)}",
            "raw_response": None
        }

def main():
    """Основная функция тестирования"""
    print("🧪 Тестовый скрипт анализа фото психрометра")
    print("=" * 50)
    
    # Путь к тестовому изображению
    image_path = "img.png"
    
    # Проверяем наличие файла
    import os
    if not os.path.exists(image_path):
        print(f"❌ Файл {image_path} не найден!")
        print("📁 Создайте файл img.png в текущей директории")
        return
    
    # Запускаем анализ
    result = analyze_photo_test(image_path)
    
    print("\n📊 РЕЗУЛЬТАТЫ АНАЛИЗА:")
    print("=" * 30)
    
    if result["success"]:
        print(f"✅ Успешно!")
        print(f"🌡️ Сухой термометр: {result['t_dry']}°C")
        print(f"💧 Влажный термометр: {result['t_wet']}°C")
        print(f"📏 Разность: {result['t_dry'] - result['t_wet']}°C")
        
        # Рассчитываем влажность
        from psychrometric_calculator import calculate_humidity
        humidity_result = calculate_humidity(result['t_dry'], result['t_wet'])
        
        if humidity_result["success"]:
            print(f"💨 Влажность воздуха: {humidity_result['humidity']}%")
        else:
            print(f"❌ Ошибка расчета влажности: {humidity_result['error']}")
    else:
        print(f"❌ Ошибка: {result['error']}")
        if result.get('raw_response'):
            print(f"🤖 Ответ OpenAI: {result['raw_response']}")
    
    print("\n📝 Логи сохранены выше")

if __name__ == "__main__":
    main()
