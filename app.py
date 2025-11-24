import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.error import Conflict
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

# Flask app для мониторинга
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!", 200

@flask_app.route('/health')
def health():
    return "OK", 200

class VideoDownloaderBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.webhook_url = os.getenv('RENDER_EXTERNAL_URL', '') + '/webhook'
        
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN не найден в .env файле")
        
        self.application = (
            Application.builder()
            .token(self.token)
            .build()
        )
        
        self.setup_handlers()
        self.temp_dir = "temp"
        os.makedirs(self.temp_dir, exist_ok=True)

    def setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("download", self.download_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

Просто отправьте мне ссылку на видео или нажмите кнопку ниже для начала работы!
        """
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        await self.send_help_message(update.message)

    async def download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /download"""
        await self.send_download_info(update.message)

    async def send_help_message(self, message):
        help_text = """
📖 **Как использовать бота:**

1. Отправьте мне ссылку на видео из:
   • YouTube
   • TikTok  
   • Instagram
   • VK

2. Я автоматически определю платформу

3. Выберите качество (если доступно)

4. Получите видео в лучшем качестве!

🔗 **Примеры ссылок:**
- https://youtube.com/watch?v=...
- https://vm.tiktok.com/...
- https://instagram.com/p/...
- https://vk.com/video...

⚠️ **Важно:** Используйте только для личных целей.
        """
        keyboard = [[InlineKeyboardButton("🚀 Начать скачивание", callback_data="download_info")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def send_download_info(self, message):
        info_text = """
📥 **Чтобы скачать видео:**

Просто отправьте мне ссылку в одном из форматов:

**YouTube:**
`https://www.youtube.com/watch?v=...`
`https://youtu.be/...`

**TikTok:**
`https://vm.tiktok.com/...`
`https://www.tiktok.com/...`

**Instagram:**
`https://www.instagram.com/p/...`
`https://www.instagram.com/reel/...`

**VK:**
`https://vk.com/video...`
`https://vk.com/clip...`

Отправляйте ссылку прямо в чат!
        """
        keyboard = [[InlineKeyboardButton("❓ Нужна помощь?", callback_data="help")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(info_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на инлайн кнопки"""
        query = update.callback_query
        await query.answer()

        if query.data == "download_info":
            await self.send_download_info(query.message)
        elif query.data == "help":
            await self.send_help_message(query.message)
        elif query.data == "platforms":
            platforms_text = """
🌐 **Поддерживаемые платформы:**

✅ **YouTube** - видео, shorts
✅ **TikTok** - все виды видео
✅ **Instagram** - посты, рилы, истории
✅ **VK** - видео, клипы

Все видео скачиваются в максимальном доступном качестве!
            """
            keyboard = [[InlineKeyboardButton("📥 Начать скачивание", callback_data="download_info")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(platforms_text, reply_markup=reply_markup, parse_mode='Markdown')

    def is_supported_url(self, url: str) -> bool:
        """Проверяет поддержку URL"""
        supported_domains = [
            'youtube.com', 'youtu.be', 
            'tiktok.com', 'vm.tiktok.com',
            'instagram.com',
            'vk.com'
        ]
        return any(domain in url.lower() for domain in supported_domains)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        user_message = update.message.text.strip()
        
        if not user_message.startswith(('http://', 'https://')):
            keyboard = [[InlineKeyboardButton("❓ Как использовать?", callback_data="help")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте валидную ссылку на видео.", 
                reply_markup=reply_markup
            )
            return

        if not self.is_supported_url(user_message):
            keyboard = [[InlineKeyboardButton("🌐 Поддерживаемые платформы", callback_data="platforms")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ Этот тип ссылки не поддерживается.", 
                reply_markup=reply_markup
            )
            return

        # Отправляем сообщение о начале загрузки
        status_message = await update.message.reply_text("⏳ Анализирую ссылку...")

        try:
            await status_message.edit_text("📥 Скачиваю видео в максимальном качестве...")

            # Скачиваем видео
            file_path = await self.download_video(user_message)
            
            if file_path and os.path.exists(file_path):
                # Отправляем видео
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # в MB
                
                caption = f"""
✅ **Видео успешно скачано!**
💾 Размер: {file_size:.1f}MB
🎬 Платформа: {self.get_platform_name(user_message)}
                """
                
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

    def get_platform_name(self, url: str) -> str:
        """Определяет название платформы по URL"""
        if 'youtube.com' in url or 'youtu.be' in url:
            return "YouTube"
        elif 'tiktok.com' in url:
            return "TikTok"
        elif 'instagram.com' in url:
            return "Instagram"
        elif 'vk.com' in url:
            return "VK"
        return "Unknown"

    async def download_video(self, url: str) -> str:
        """Скачивает видео используя yt-dlp"""
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(self.temp_dir, '%(title).100s.%(ext)s'),
            'merge_output_format': 'mp4',
            'writesubtitles': False,
            'writeautomaticsub': False,
            'quiet': False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                return filename
        except Exception as e:
            logger.error(f"Ошибка скачивания: {str(e)}")
            return None

    async def setup_webhook(self):
        """Настройка webhook"""
        try:
            await self.application.bot.set_webhook(
                url=self.webhook_url,
                allowed_updates=["message", "callback_query"]
            )
            logger.info(f"Webhook установлен: {self.webhook_url}")
        except Exception as e:
            logger.error(f"Ошибка установки webhook: {e}")

    def run_webhook(self):
        """Запуск бота с webhook"""
        logger.info("Запуск бота с webhook...")
        
        # Настройка webhook при запуске
        asyncio.run(self.setup_webhook())
        
        # Запуск Flask
        port = int(os.environ.get('PORT', 5000))
        flask_app.run(host='0.0.0.0', port=port)

# Webhook endpoint для Flask
@flask_app.route('/webhook', methods=['POST'])
async def webhook():
    """Endpoint для webhook"""
    try:
        data = await request.get_json()
        update = Update.de_json(data, bot_instance.application.bot)
        await bot_instance.application.process_update(update)
        return 'ok', 200
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
        return 'error', 500

# Глобальный экземпляр бота
bot_instance = None

if __name__ == "__main__":
    bot_instance = VideoDownloaderBot()
    bot_instance.run_webhook()
