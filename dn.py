import os
import re
import asyncio
import logging
import shutil
from pathlib import Path

from aiohttp import web

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters
)

from telegram.request import HTTPXRequest

import yt_dlp


# ==========================
# Logging
# ==========================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# ==========================
# Config
# ==========================

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "8794175319:AAHzp7Ntp-gK7x6b2E4YJOOJLTUwU3QMDyI"
)


# پوشه ذخیره موقت فایل‌ها
DOWNLOAD_DIR = Path("downloads")

if not DOWNLOAD_DIR.exists():
    DOWNLOAD_DIR.mkdir()


# حداکثر حجم فایل (تلگرام محدودیت دارد)
MAX_FILE_SIZE = 50 * 1024 * 1024


# تعداد دانلود همزمان
DOWNLOAD_LIMIT = asyncio.Semaphore(3)


# ==========================
# Supported Platforms
# ==========================

INSTAGRAM_REGEX = re.compile(
    r"https?://(?:www\.)?instagram\.com/"
    r"(?:p|reel|reels|stories)/[A-Za-z0-9_-]+",
    re.IGNORECASE
)


YOUTUBE_REGEX = re.compile(
    r"https?://(?:www\.)?"
    r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)"
    r"[A-Za-z0-9_-]+",
    re.IGNORECASE
)


TIKTOK_REGEX = re.compile(
    r"https?://(?:www\.)?"
    r"(?:tiktok\.com/@[\w.-]+/video/\d+|vm\.tiktok\.com/\w+)",
    re.IGNORECASE
)

# ==========================
# yt-dlp Settings
# ==========================

def get_ydl_options(quality="720"):
    
    format_selector = (
        f"bestvideo[height<={quality}]"
        "+bestaudio/"
        f"best[height<={quality}]/"
        "best"
    )

    return {
        "format": format_selector,

        "outtmpl": str(
            DOWNLOAD_DIR / "%(id)s.%(ext)s"
        ),

        # ترکیب صدا و تصویر
        "merge_output_format": "mp4",

        # استفاده از ffmpeg در Render
        "ffmpeg_location": "/usr/bin/ffmpeg",

        "quiet": True,
        "no_warnings": True,

        "socket_timeout": 60,

        "retries": 5,

        "continuedl": True,

        # جلوگیری از خراب شدن فایل
        "noplaylist": False,

        "http_headers": {
            "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        },

        # برای بعضی سایت‌ها
        "extractor_args": {
            "youtube": {
                "player_client": [
                    "android"
                ]
            }
        }
    }


# ==========================
# Quality Options
# ==========================

QUALITY_MAP = {
    "360": "360",
    "480": "480",
    "720": "720",
    "1080": "1080"
}

# ==========================
# Download Function
# ==========================

def download_media(url: str, quality="720") -> str:

    options = get_ydl_options(quality)

    try:
        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            file_path = ydl.prepare_filename(info)

            # اگر خروجی نهایی mp4 ساخته شده باشد
            possible_mp4 = str(
                Path(file_path).with_suffix(".mp4")
            )

            if os.path.exists(possible_mp4):
                return possible_mp4

            return file_path


    except yt_dlp.utils.DownloadError as error:

        logger.error(
            f"YT-DLP ERROR: {error}"
        )

        raise Exception(
            "DOWNLOAD_FAILED"
        )


    except Exception as error:

        logger.error(
            f"DOWNLOAD ERROR: {error}"
        )

        raise

# ==========================
# URL Detector
# ==========================

def detect_platform(text: str):

    if not text:
        return None, None


    insta = INSTAGRAM_REGEX.search(text)

    if insta:
        return (
            "instagram",
            insta.group(0)
        )


    youtube = YOUTUBE_REGEX.search(text)

    if youtube:
        return (
            "youtube",
            youtube.group(0)
        )


    tiktok = TIKTOK_REGEX.search(text)

    if tiktok:
        return (
            "tiktok",
            tiktok.group(0)
        )


    return None, None

# ==========================
# Group Message Handler
# ==========================

async def handle_group_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return


    # فقط گروه‌ها
    if update.effective_chat.type not in [
        "group",
        "supergroup"
    ]:
        return


    text = (
        update.message.text
        or update.message.caption
    )


    if not text:
        return


    platform, url = detect_platform(text)


    if not url:
        return


    platform_name = {
        "instagram": "اینستاگرام",
        "youtube": "یوتیوب",
        "tiktok": "تیک‌تاک"
    }.get(
        platform,
        "ناشناخته"
    )


    status = await update.message.reply_text(
    f"🖕 لینکتو دریافت کردم جقی\n"
    f"📌 این کصشعر ارسالیت مال: {platform_name}\n\n"
    "⏳ درحال دانلود ویدیوی کوصاشعر شما هستم...\n"
    "⬇️ کیفیت: 720p\n"
    "یه ذره صبر کن شاشو 😂"
)


    async with DOWNLOAD_LIMIT:

        try:

            loop = asyncio.get_running_loop()


            file_path = await loop.run_in_executor(
                None,
                download_media,
                url,
                "720"
            )


            if not os.path.exists(file_path):
                raise Exception(
                    "FILE_NOT_FOUND"
                )


            file_size = os.path.getsize(
                file_path
            )


            if file_size > MAX_FILE_SIZE:

                await status.edit_text(
    "❌ این دیگه ویدیو نیست کیرم دهنت 😂\n\n"
    "حجمش زیاده، تلگرام نمی‌ذاره بفرستم."
)

                os.remove(file_path)
                return


            await status.edit_text(
    "😂 بالاخره این کصشر دانلود شد\n\n"
    "📤 دارم می‌فرستمش تو گروه\n"
    "اگه اینترنتت زغالیه تقصیر من نیست 🗿"
)


            with open(
                file_path,
                "rb"
            ) as video:

                await update.message.reply_video(
                    video=video,
                    caption=(
    "✅ اینم ویدیوی کصشعرت 😂\n\n"
    f"📌 منبع این کصشر: {platform_name}\n"
    "🤖 من میخوام بوست کنم آبمو میاری"
),
                    reply_to_message_id=(
                        update.message.message_id
                    ),
                    write_timeout=300,
                    read_timeout=300
                )


            os.remove(file_path)


            await status.delete()


        except Exception as error:

            logger.error(
                f"HANDLER ERROR: {error}"
            )


            await status.edit_text(
    "💀 خراب شد رفیق\n\n"
    "یا لینک کصشر دادی\n"
    "یا پیج طرف قفله\n"
    "یا سایت داره فیلم بازی درمیاره 😂"
)

# ==========================
# Render Web Server
# ==========================

async def handle_ping(request):
    return web.Response(
        text="Downloader Bot is Alive!"
    )


async def start_web_server():

    app = web.Application()

    app.router.add_get(
        "/",
        handle_ping
    )

    runner = web.AppRunner(app)

    await runner.setup()

    port = int(
        os.environ.get(
            "PORT",
            8080
        )
    )

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    logger.info(
        f"Web server running on port {port}"
    )


# ==========================
# Main Bot Runner
# ==========================

async def main():

    request = HTTPXRequest(
        connect_timeout=30,
        read_timeout=300,
        write_timeout=300
    )


    bot = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .build()
    )


    group_filter = (
        filters.ChatType.GROUPS
        &
        (
            filters.TEXT
            |
            filters.CAPTION
        )
        &
        ~filters.COMMAND
    )


    bot.add_handler(
        MessageHandler(
            group_filter,
            handle_group_message
        )
    )


    await start_web_server()


    logger.info(
        "Bot Started Successfully"
    )


    async with bot:

        await bot.initialize()

        await bot.start()

        await bot.updater.start_polling(
            drop_pending_updates=True
        )


        await asyncio.Event().wait()



# ==========================
# Start
# ==========================

if __name__ == "__main__":

    asyncio.run(
        main()
    )                        
