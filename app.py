import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
import yt_dlp
from flask import Flask, request

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создаем Flask app
flask_app = Flask(__name__)

# Глобальная переменная для бота
bot_application = None
temp_dir = "temp"

def create_bot():
    """Создает и настраивает бота"""
    global bot_application
    
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не найден")
    
    # Создаем приложение бота
    bot_application = (
        Application.builder()
        .token(token)
        .build()
    )
    
    # Настраиваем обработчики
    setup_handlers(bot_application)
    
    return bot_application

def setup_handlers(application):
    """Настраивает обработчики команд"""
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("download", download_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    keyboard = [
        [InlineKeyboardButton("📥 Скачать видео", callback_data="download_info")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
        [InlineKeyboardButton("🌐 Поддерживаемые платформы", callback_data="platforms")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🤖 **Добро пожаловать в Video Downloader Pro!**

Я могу скачать видео с:
🎬 YouTube | 📱 TikTok | 📸 Instagram | 👥 VK

Просто отправьте мне ссылку на видео!
    """
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await send_help_message(update.message)

async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /download"""
    await send_download_info(update.message)

async def send_help_message(message):
    help_text = """
📖 **Как использовать бота:**
1. Отправьте ссылку на видео
2. Получите видео в лучшем качестве!

🔗 **Поддерживаемые платформы:**
- YouTube
- TikTok  
- Instagram
- VK
    """
    await message.reply_text(help_text, parse_mode='Markdown')

async def send_download_info(message):
    info_text = """
📥 **Чтобы скачать видео:**
Отправьте ссылку на видео из:
YouTube, TikTok, Instagram или VK
    """
    await message.reply_text(info_text, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на инлайн кнопки"""
    query = update.callback_query
    await query.answer()

    if query.data == "download_info":
        await send_download_info(query.message)
    elif query.data == "help":
        await send_help_message(query.message)
    elif query.data == "platforms":
        platforms_text = "🌐 **Поддерживаемые платформы:**\n✅ YouTube, TikTok, Instagram, VK"
        await query.message.reply_text(platforms_text, parse_mode='Markdown')

def is_supported_url(url: str) -> bool:
    """Проверяет поддержку URL"""
    supported_domains = [
        'youtube.com', 'youtu.be', 
        'tiktok.com', 'vm.tiktok.com',
        'instagram.com',
        'vk.com'
    ]
    return any(domain in url.lower() for domain in supported_domains)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_message = update.message.text.strip()
    
    if not user_message.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Пожалуйста, отправьте валидную ссылку на видео.")
        return

    if not is_supported_url(user_message):
        await update.message.reply_text("❌ Этот тип ссылки не поддерживается.")
        return

    status_message = await update.message.reply_text("⏳ Скачиваю видео...")

    try:
        # Скачиваем видео
        file_path = await download_video(user_message)
        
        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # в MB
            caption = f"✅ **Видео скачано!**\n💾 Размер: {file_size:.1f}MB"
            
            await update.message.reply_video(
                video=open(file_path, 'rb'),
                caption=caption,
                supports_streaming=True,
                parse_mode='Markdown'
            )
            await status_message.delete()
            
            # Удаляем временный файл
            os.remove(file_path)
        else:
            await status_message.edit_text("❌ Не удалось скачать видео.")
            
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        await status_message.edit_text("❌ Произошла ошибка. Попробуйте другую ссылку.")

async def download_video(url: str) -> str:
    """Скачивает видео используя yt-dlp"""
    os.makedirs(temp_dir, exist_ok=True)
    
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': os.path.join(temp_dir, '%(title).100s.%(ext)s'),
        'quiet': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename
    except Exception as e:
        logger.error(f"Ошибка скачивания: {str(e)}")
        return None

@flask_app.route('/')
def home():
    return "Bot is running!", 200

@flask_app.route('/health')
def health():
    return "OK", 200

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint для webhook"""
    global bot_application
    try:
        if bot_application:
            update = Update.de_json(request.get_json(), bot_application.bot)
            asyncio.run_coroutine_threadsafe(
                bot_application.process_update(update),
                bot_application._get_running_loop()
            )
        return 'ok', 200
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
        return 'error', 500

async def setup_webhook():
    """Настройка webhook"""
    global bot_application
    try:
        # Получаем URL автоматически от Render
        render_url = os.getenv('RENDER_EXTERNAL_URL')
        if not render_url:
            logger.error("RENDER_EXTERNAL_URL не найден")
            return
        
        webhook_url = f"{render_url}/webhook"
        await bot_application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"]
        )
        logger.info(f"Webhook установлен: {webhook_url}")
    except Exception as e:
        logger.error(f"Ошибка установки webhook: {e}")

def run_bot():
    """Запуск бота"""
    global bot_application
    
    # Создаем бота
    bot_application = create_bot()
    
    # Настраиваем webhook
    asyncio.run(setup_webhook())
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    run_bot()
