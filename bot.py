import asyncio
import glob as globmod
import os
import re
import subprocess
import tempfile
import logging

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
INSTAGRAM_SESSION_ID = os.getenv("INSTAGRAM_SESSION_ID", "")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB (Telegram limit)

COOKIES_FILE = None
if INSTAGRAM_SESSION_ID:
    COOKIES_FILE = os.path.join(tempfile.gettempdir(), "ig_cookies.txt")
    with open(COOKIES_FILE, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(f".instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{INSTAGRAM_SESSION_ID}\n")
        f.write(f".instagram.com\tTRUE\t/\tTRUE\t0\tds_user_id\t0\n")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(
    r"(https?://(?:www\.|m\.)?(?:"
    r"youtube\.com/watch\S*|youtu\.be/\S+|youtube\.com/shorts/\S+"  # YouTube
    r"|instagram\.com/(?:reel|p|tv)/\S+"                           # Instagram
    r"))"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🎼 Витесс, маэстро, этот бот создан специально для тебя! 🎹\n"
        "Получилось как подарок на 8 Марта, ахах 😂🎁\n\n"
        "Тут всё просто — кидаешь ссылку из YouTube или Instagram, "
        "получаешь видео 🎬\n"
        "Никаких нот читать не надо, и даже дирижировать! 🎶✌️\n\n"
        "По всем вопросам: @shebalin000"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    match = URL_PATTERN.search(text)

    if not match:
        await update.message.reply_text(
            "Отправь мне ссылку на видео из YouTube или Instagram."
        )
        return

    url = match.group(1)
    status_msg = await update.message.reply_text("Скачиваю видео...")

    try:
        video_path = await download_video(url)
    except Exception as e:
        logger.error("Download error: %s", e)
        await status_msg.edit_text(f"Ошибка при скачивании: {e}")
        return

    try:
        file_size = os.path.getsize(video_path)
        if file_size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                "Видео слишком большое (больше 50 МБ) для отправки через Telegram."
            )
            return

        await status_msg.edit_text("Отправляю видео...")
        with open(video_path, "rb") as video_file:
            await update.message.reply_video(
                video=video_file,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120,
            )
        await status_msg.delete()
    except Exception as e:
        logger.error("Send error: %s", e)
        await status_msg.edit_text(f"Ошибка при отправке: {e}")
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)


async def download_video(url: str) -> str:
    tmp_dir = tempfile.mkdtemp()
    output_path = os.path.join(tmp_dir, "video.%(ext)s")

    ydl_opts = {
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "outtmpl": output_path,
        "merge_output_format": "mkv",
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
    }
    if COOKIES_FILE:
        ydl_opts["cookiefile"] = COOKIES_FILE

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)

    # Find the downloaded file (skip .part files)
    files = [f for f in globmod.glob(os.path.join(tmp_dir, "video.*")) if not f.endswith(".part")]
    if not files:
        raise FileNotFoundError("Не удалось найти скачанный файл")
    downloaded = files[0]

    # Re-encode to H.264 mp4 with ffmpeg
    final_path = os.path.join(tmp_dir, "output.mp4")
    cmd = [
        "ffmpeg", "-i", downloaded,
        "-c:v", "libx264", "-preset", "fast", "-crf", "28",
        "-c:a", "aac", "-b:a", "128k",
        "-maxrate", "2M", "-bufsize", "4M",
        "-movflags", "+faststart",
        "-y", final_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    await proc.wait()

    if proc.returncode != 0 or not os.path.exists(final_path):
        raise RuntimeError("Ошибка при конвертации видео")

    os.remove(downloaded)
    return final_path


def main() -> None:
    if not BOT_TOKEN:
        print("Ошибка: установите BOT_TOKEN в файле .env")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
