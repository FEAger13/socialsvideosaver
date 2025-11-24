import os
import logging
import json
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import asyncio
from threading import Thread
import tempfile
import shutil

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получение токена из переменных окружения Render
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

# Создание Flask приложения
app = Flask(__name__)

# Инициализация Telegram бота
telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Создаем временную директорию
TEMP_DIR = "temp_videos"
os.makedirs(TEMP_DIR, exist_ok=True)

def cleanup_temp_files():
    """Очистка временных файлов"""
    try:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            os.makedirs(TEMP_DIR, exist_ok=True)
    except Exception as e:
        logger.error(f"Error cleaning temp files: {e}")

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
🤖 **YouTube Video Downloader Bot**

Отправьте мне ссылку на YouTube видео, и я скачаю его в максимальном качестве!

⚡ Просто отправьте ссылку на YouTube!
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

# Функция для скачивания видео
def download_video(url):
    try:
        # Очищаем временные файлы перед загрузкой
        cleanup_temp_files()
        
        ydl_opts = {
            'outtmpl': os.path.join(TEMP_DIR, '%(title).100s.%(ext)s'),
            'format': 'best[height<=1080]',  # Максимальное качество до 1080p
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename, info
            
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    # Проверка на YouTube ссылку
    if 'youtube.com' not in url and 'youtu.be' not in url:
        await update.message.reply_text("❌ Пожалуйста, отправьте действительную ссылку на YouTube видео.")
        return
    
    try:
        # Отправляем сообщение о начале загрузки
        status_msg = await update.message.reply_text("⏬ Начинаю загрузку видео...")
        
        # Скачиваем видео
        filename, video_info = await asyncio.to_thread(download_video, url)
        
        # Проверяем размер файла (Telegram ограничение 50MB)
        file_size = os.path.getsize(filename) / (1024 * 1024)  # в MB
        if file_size > 50:
            await update.message.reply_text(f"❌ Файл слишком большой ({file_size:.1f}MB). Максимальный размер 50MB.")
            os.remove(filename)
            return
        
        # Отправляем видео
        with open(filename, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=f"🎬 **{video_info.get('title', 'Video')}**\n"
                       f"⏱ Длительность: {video_info.get('duration', 0)} сек.\n"
                       f"📊 Качество: {video_info.get('resolution', 'max')}",
                parse_mode='Markdown'
            )
        
        # Удаляем временный файл
        os.remove(filename)
        await status_msg.delete()
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await update.message.reply_text("❌ Произошла ошибка при загрузке видео. Попробуйте другую ссылку.")

# Настройка хендлеров
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Webhook маршруты
@app.route('/')
def home():
    return "🤖 YouTube Downloader Bot is running! Use /start in Telegram."

@app.route('/webhook', methods=['POST'])
def webhook():
    """Правильная обработка вебхука"""
    try:
        # Получаем JSON данные
        json_data = request.get_json()
        logger.info(f"Received webhook: {json_data}")
        
        if json_data:
            # Создаем Update объект
            update = Update.de_json(json_data, telegram_app.bot)
            
            # Обрабатываем обновление в отдельном потоке
            def process_update():
                try:
                    asyncio.run(telegram_app.process_update(update))
                except Exception as e:
                    logger.error(f"Error processing update: {e}")
            
            thread = Thread(target=process_update)
            thread.start()
            
            return 'OK'
        else:
            logger.error("Empty webhook data")
            return 'ERROR: Empty data'
            
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return 'ERROR'

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Установка вебхука"""
    try:
        webhook_url = f"https://{request.host}/webhook"
        result = telegram_app.bot.set_webhook(webhook_url)
        logger.info(f"Webhook set to {webhook_url}: {result}")
        return jsonify({
            "status": "success",
            "webhook_url": webhook_url,
            "result": result
        })
    except Exception as e:
        logger.error(f"Set webhook error: {e}")
        return jsonify({"status": "error", "error": str(e)})

@app.route('/delete_webhook', methods=['GET'])
def delete_webhook():
    """Удаление вебхука"""
    try:
        result = telegram_app.bot.delete_webhook()
        return jsonify({"status": "success", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка здоровья"""
    return jsonify({
        "status": "healthy", 
        "service": "YouTube Downloader Bot",
        "bot_initialized": True
    })

# Инициализация при запуске
def initialize_bot():
    """Инициализация бота при запуске"""
    try:
        # Устанавливаем вебхук автоматически
        with app.app_context():
            webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')}/webhook"
            if webhook_url.startswith("https://"):
                telegram_app.bot.set_webhook(webhook_url)
                logger.info(f"Auto-set webhook to: {webhook_url}")
    except Exception as e:
        logger.error(f"Auto-webhook setup failed: {e}")

# Запуск инициализации
initialize_bot()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
