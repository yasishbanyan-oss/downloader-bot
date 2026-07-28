import os
import re
import logging
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    ContextTypes
)
from telegram.request import HTTPXRequest
import yt_dlp

# تنظیم سیستم لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# دریافت توکن جدید از متغیرهای محیطی یا مقدار مستقیم
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8794175319:AAGAEB2MvL1FKYHTLG43FVFQMtsIZBwlSIE")

# الگوهای هوشمند شناسایی لینک‌ها
INSTAGRAM_REGEX = r'(https?://(?:www\.)?instagram\.com/(?:p|reel|reels|stories)/[A-Za-z0-9_.-]+)'
YOUTUBE_REGEX = r'(https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)[A-Za-z0-9_-]+)'
TIKTOK_REGEX = r'(https?://(?:www\.|vt\.|vm\.)?tiktok\.com/[A-Za-z0-9_.-]+)'

def download_media(url: str) -> str:
    ydl_opts = {
        # انتخاب تک‌فایل یا ترکیب صدا و ویدیو حداکثر تا کیفیت 720p
        'format': 'best[height<=720][ext=mp4]/bestvideo[height<=720]+bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 60,
        # دور زدن محدودیت IP دیتاسنترها در یوتیوب
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    # اگر فایل کوکی قرار دادید برای استوری‌ها
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        return

    message_text = update.message.text or update.message.caption
    if not message_text:
        return

    insta_match = re.search(INSTAGRAM_REGEX, message_text)
    yt_match = re.search(YOUTUBE_REGEX, message_text)
    tiktok_match = re.search(TIKTOK_REGEX, message_text)

    target_url = None
    source_type = ""

    if insta_match:
        target_url = insta_match.group(0)
        source_type = "اینستاگرام"
    elif yt_match:
        target_url = yt_match.group(0)
        source_type = "یوتیوب"
    elif tiktok_match:
        target_url = tiktok_match.group(0)
        source_type = "تیک‌تاک"

    if not target_url:
        return

    status_msg = await update.message.reply_text(f"⏳ در حال دانلود از {source_type}...")
    file_path = None

    try:
        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(None, download_media, target_url)

        if file_path and os.path.exists(file_path):
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > 50:
                await status_msg.edit_text("⚠️ حجم ویدیو بیشتر از ۵۰ مگابایت است و تلگرام اجازه آپلود آن را نمی‌دهد.")
                return

            await status_msg.edit_text("📤 در حال آپلود ویدیو...")

            with open(file_path, 'rb') as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption=f"📥 دانلود شده از {source_type} | سارا چرخشی",
                    reply_to_message_id=update.message.message_id,
                    write_timeout=300,
                    read_timeout=300
                )
            
            await status_msg.delete()

    except yt_dlp.utils.DownloadError as e:
        logging.error(f"DownloadError: {e}")
        await status_msg.edit_text("❌ دانلود ناموفق بود! ممکن است لینک اشتباه باشد یا ویدیو خصوصی باشد.")
    except Exception as e:
        logging.error(f"Error downloading: {e}")
        await status_msg.edit_text("❌ خطایی در پردازش ویدیو رخ داد.")
    finally:
        # پاک‌سازی قطعی فایل برای پر نشدن دیسک
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as cleanup_error:
                logging.error(f"Error removing file: {cleanup_error}")

# --- وب‌سرور داخلی (برای زنده نگه داشتن روی Render) ---
async def handle_ping(request):
    return web.Response(text="Downloader Bot is Alive!")

async def main():
    if not os.path.exists('downloads'):
        os.makedirs('downloads')

    request = HTTPXRequest(connect_timeout=30.0, read_timeout=300.0, write_timeout=300.0)
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()

    group_filter = filters.ChatType.GROUPS & (filters.TEXT | filters.CAPTION) & ~filters.COMMAND
    app.add_handler(MessageHandler(group_filter, handle_group_message))

    web_app = web.Application()
    web_app.router.add_get('/', handle_ping)
    runner = web.AppRunner(web_app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    print("ربات دانلودر آنلاین شد...")

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()
        
if __name__ == "__main__":
    asyncio.run(main())
