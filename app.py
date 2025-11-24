import os
import logging
import tempfile
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import asyncio
from threading import Thread

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

# Создание Telegram Application
telegram_app = Application.builder().token(TLEGRAM_BOT_TOKEN).build()

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
🤖 **YouTube Video Downloader Bot**

Отправьте мне ссылку на YouTube видео, и я скачаю его в максимальном качестве!

📹 Поддерживаемые форматы:
• MP4 (видео)
• MP3 (аудио)

⚡ Просто отправьте ссылку и выберите формат!
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

# Функция для скачивания видео
def download_video(url, quality='best'):
    ydl_opts = {
        'outtmpl': 'temp/%(title)s.%(ext)s',
        'format': 'best' if quality == 'best' else 'worst',
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info

# Обработчик текстовых сообщений (ссылок)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    # Проверка на YouTube ссылку
    if 'youtube.com' not in url and 'youtu.be' not in url:
        await update.message.reply_text("❌ Пожалуйста, отправьте действительную ссылку на YouTube видео.")
        return
    
    try:
        # Отправляем сообщение о начале загрузки
        status_msg = await update.message.reply_text("⏬ Начинаю загрузку видео...")
        
        # Скачиваем видео в максимальном качестве
        filename, video_info = await asyncio.to_thread(download_video, url, 'best')
        
        # Отправляем видео
        await update.message.reply_video(
            video=open(filename, 'rb'),
            caption=f"🎬 **{video_info.get('title', 'Video')}**\n"
                   f"⏱ Длительность: {video_info.get('duration', 0)} сек.\n"
                   f"📊 Качество: максимальное",
            parse_mode='Markdown'
        )
        
        # Удаляем временный файл
        os.remove(filename)
        await status_msg.delete()
        
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        await update.message.reply_text("❌ Произошла ошибка при загрузке видео. Попробуйте еще раз.")

# Настройка хендлеров
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Webhook маршруты для Render
@app.route('/')
def home():
    return "YouTube Downloader Bot is running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint для вебхука Telegram"""
    try:
        json_str = request.get_data().decode('UTF-8')
        update = Update.de_json(json_str, telegram_app.bot)
        
        # Запускаем обработку обновления в отдельном потоке
        thread = Thread(target=asyncio.run, args=(telegram_app.process_update(update),))
        thread.start()
        
        return 'OK'
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return 'ERROR'

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Установка вебхука (вызывается один раз после деплоя)"""
    webhook_url = f"https://{request.host}/webhook"
    result = telegram_app.bot.set_webhook(webhook_url)
    return f"Webhook set to {webhook_url}: {result}"

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint для проверки работоспособности (для cron-job.org)"""
    return {'status': 'healthy', 'bot': 'running'}

# Запуск приложения
if __name__ == '__main__':
    # Создаем временную директорию
    os.makedirs('temp', exist_ok=True)
    
    # Устанавливаем вебхук при запуске
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
