import os
import re
import time
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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = "8794175319:AAHzp7Ntp-gK7x6b2E4YJOOJLTUwU3QMDyI"

INSTAGRAM_REGEX = r'(https?://(?:www\.)?instagram\.com/(?:p|reel|reels|stories)/[A-Za-z0-9_.-]+)'
YOUTUBE_REGEX = r'(https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[A-Za-z0-9_.-]+)'

def download_media(url: str) -> str:
    ydl_opts = {
        'format': 'best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 60,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename

# --- ساخت نوار پیشرفت گرافیکی ---
def make_progress_bar(percent: float) -> str:
    total_blocks = 10
    filled_blocks = int(percent / 10)
    empty_blocks = total_blocks - filled_blocks
    bar = "█" * filled_blocks + "░" * empty_blocks
    return f"[{bar}] {int(percent)}%"

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        return

    message_text = update.message.text or update.message.caption
    if not message_text:
        return

    insta_match = re.search(INSTAGRAM_REGEX, message_text)
    yt_match = re.search(YOUTUBE_REGEX, message_text)

    target_url = None
    source_type = ""

    if insta_match:
        target_url = insta_match.group(0)
        source_type = "اینستاگرام"
    elif yt_match:
        target_url = yt_match.group(0)
        source_type = "یوتیوب"

    if not target_url:
        return

    status_msg = await update.message.reply_text(f"⏳ در حال دانلود از {source_type}...")

    try:
        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(None, download_media, target_url)

        if os.path.exists(file_path):
            total_size = os.path.getsize(file_path)
            last_update_time = [0] # برای مدیریت زمان ویرایش پیام (جلوگیری از لیمیت تلگرام)

            # تابع پیشرفت آپلود
            async def progress(current, total):
                now = time.time()
                # ادیت پیام حداکثر هر ۲.۵ ثانیه یک‌بار انجام می‌شود تا تلگرام ربات را بن/محدود نکند
                if now - last_update_time[0] > 2.5 or current == total:
                    last_update_time[0] = now
                    percent = (current / total) * 100
                    bar_text = make_progress_bar(percent)
                    msg_text = (
                        f"در حال آپلود ویدیو در گروه | شکیبا باشید!\n\n"
                        f"{bar_text}"
                    )
                    try:
                        await status_msg.edit_text(msg_text)
                    except Exception:
                        pass

            with open(file_path, 'rb') as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption=f"📥 دانلود شده از {source_type} | سارا چرخشی",
                    reply_to_message_id=update.message.message_id,
                    write_timeout=300,
                    read_timeout=300,
                    progress=progress
                )  # <-- این پرانتز بسته شدن مهمه!
            
            os.remove(file_path)
            await status_msg.delete()

    except yt_dlp.utils.DownloadError as e:
        logging.error(f"DownloadError: {e}")
        await status_msg.edit_text("❌ کیرم تو طرز لینک دادنت کصخل این چیه دادی؟ یا لینک اشتباهه یا پیج طرف پرایوته")
    except Exception as e:
        logging.error(f"Error downloading: {e}")
        await status_msg.edit_text(f"❌ خطای دانلود: {str(e)}")

# --- وب‌سرور داخلی برای Render ---
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

    print("ربات دانلودر با وب‌سرور و نوار پیشرفت آنلاین شد...")

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.sleep(1)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())       
