import asyncio
import contextlib
import glob as globmod
import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
INSTAGRAM_SESSION_ID = os.getenv("INSTAGRAM_SESSION_ID", "")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB (Telegram limit)
HOST = os.getenv("HOST", "0.0.0.0")
PORT = os.getenv("PORT")

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

MediaKind = Literal["video", "audio"]
PENDING_URLS_KEY = "pending_urls"
PENDING_URL_TTL_SECONDS = 60 * 60 * 6

URL_PATTERN = re.compile(
    r"(https?://(?:www\.|m\.)?(?:"
    r"youtube\.com/watch\S*|youtu\.be/\S+|youtube\.com/shorts/\S+"  # YouTube
    r"|instagram\.com/(?:reel|p|tv)/\S+"                           # Instagram
    r"))"
)


def ensure_runtime_dependencies() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is not available in PATH")


def cleanup_pending_urls(bot_data: dict) -> None:
    pending_urls = bot_data.setdefault(PENDING_URLS_KEY, {})
    now = time.time()
    expired_tokens = [
        token for token, payload in pending_urls.items()
        if now - payload.get("created_at", now) > PENDING_URL_TTL_SECONDS
    ]
    for token in expired_tokens:
        pending_urls.pop(token, None)


def store_pending_url(context: ContextTypes.DEFAULT_TYPE, url: str) -> str:
    cleanup_pending_urls(context.bot_data)
    pending_urls = context.bot_data.setdefault(PENDING_URLS_KEY, {})
    token = uuid4().hex[:12]
    pending_urls[token] = {"url": url, "created_at": time.time()}
    return token


def get_pending_url(context: ContextTypes.DEFAULT_TYPE, token: str) -> str | None:
    cleanup_pending_urls(context.bot_data)
    pending_urls = context.bot_data.setdefault(PENDING_URLS_KEY, {})
    payload = pending_urls.get(token)
    if not payload:
        return None
    return payload.get("url")


def build_download_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Видео", callback_data=f"download:video:{token}"),
            InlineKeyboardButton("Аудио", callback_data=f"download:audio:{token}"),
        ]]
    )


def extract_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    return match.group(1) if match else None


def get_request_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    command_text = " ".join(context.args).strip()
    if command_text:
        return extract_url(command_text)

    replied_message = update.message.reply_to_message if update.message else None
    if replied_message and replied_message.text:
        return extract_url(replied_message.text)

    current_text = update.message.text if update.message and update.message.text else ""
    return extract_url(current_text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🎼 Витесс, маэстро, этот бот создан специально для тебя! 🎹\n"
        "Получилось как подарок на 8 Марта 😂🎁\n\n"
        "Тут всё просто:\n"
        "• кидаешь ссылку и выбираешь кнопкой: видео 🎬 или аудио 🎧\n"
        "Никаких нот читать не надо, и даже дирижировать! 🎶✌️\n\n"
        "По всем вопросам: @shebalin000",
        parse_mode="Markdown",
    )


async def send_video(message: Message, url: str) -> None:
    status_msg = await message.reply_text("Скачиваю видео...")
    file_path = None
    temp_dir = None

    try:
        file_path, temp_dir, _ = await download_media(url, media_kind="video")
    except Exception as e:
        logger.error("Video download error: %s", e)
        await status_msg.edit_text(f"Ошибка при скачивании видео: {e}")
        return

    try:
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                "Видео слишком большое (больше 50 МБ) для отправки через Telegram."
            )
            return

        await status_msg.edit_text("Отправляю видео...")
        with open(file_path, "rb") as media_file:
            await message.reply_video(
                video=media_file,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120,
            )
        await status_msg.delete()
    except Exception as e:
        logger.error("Video send error: %s", e)
        await status_msg.edit_text(f"Ошибка при отправке видео: {e}")
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


async def send_audio(message: Message, url: str) -> None:
    status_msg = await message.reply_text("Скачиваю аудио...")
    file_path = None
    temp_dir = None
    title = None

    try:
        file_path, temp_dir, title = await download_media(url, media_kind="audio")
    except Exception as e:
        logger.error("Audio download error: %s", e)
        await status_msg.edit_text(f"Ошибка при скачивании аудио: {e}")
        return

    try:
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                "Аудио слишком большое (больше 50 МБ) для отправки через Telegram."
            )
            return

        await status_msg.edit_text("Отправляю аудио...")
        with open(file_path, "rb") as media_file:
            await message.reply_audio(
                audio=media_file,
                title=title[:64] if title else None,
                read_timeout=120,
                write_timeout=120,
            )
        await status_msg.delete()
    except Exception as e:
        logger.error("Audio send error: %s", e)
        await status_msg.edit_text(f"Ошибка при отправке аудио: {e}")
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    url = extract_url(text)

    if not url:
        await update.message.reply_text(
            "Отправь мне ссылку на видео из YouTube или Instagram."
        )
        return

    token = store_pending_url(context, url)
    await update.message.reply_text(
        "Выбери, что скачать:",
        reply_markup=build_download_keyboard(token),
    )


async def handle_audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = get_request_url(update, context)
    if not url:
        await update.message.reply_text(
            "Отправь команду в формате `/audio ссылка` или ответь `/audio` на сообщение со ссылкой.",
            parse_mode="Markdown",
        )
        return

    await send_audio(update.message, url)


async def handle_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = get_request_url(update, context)
    if not url:
        await update.message.reply_text(
            "Отправь команду в формате `/video ссылка` или просто пришли ссылку сообщением.",
            parse_mode="Markdown",
        )
        return

    await send_video(update.message, url)


async def handle_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.message is None or query.data is None:
        return

    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "download":
        await query.answer()
        return

    media_kind = parts[1]
    token = parts[2]
    url = get_pending_url(context, token)

    if media_kind not in {"video", "audio"}:
        await query.answer("Неизвестный формат", show_alert=True)
        return

    if not url:
        await query.answer("Кнопка устарела. Пришли ссылку еще раз.", show_alert=True)
        return

    await query.answer("Начинаю загрузку...")

    if media_kind == "audio":
        await send_audio(query.message, url)
    else:
        await send_video(query.message, url)


async def download_media(url: str, media_kind: MediaKind) -> tuple[str, str, str | None]:
    tmp_dir = tempfile.mkdtemp(prefix="telegram-video-bot-")
    prefix = "video" if media_kind == "video" else "audio"
    output_path = os.path.join(tmp_dir, f"{prefix}.%(ext)s")

    ydl_opts = {
        "outtmpl": output_path,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
    }

    if media_kind == "video":
        ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        ydl_opts["merge_output_format"] = "mkv"
    else:
        ydl_opts["format"] = "bestaudio/best"

    if COOKIES_FILE:
        ydl_opts["cookiefile"] = COOKIES_FILE

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    title = None
    if isinstance(info, dict):
        title = info.get("title")

    # Find the downloaded file (skip .part files)
    files = [f for f in globmod.glob(os.path.join(tmp_dir, f"{prefix}.*")) if not f.endswith(".part")]
    if not files:
        raise FileNotFoundError("Не удалось найти скачанный файл")
    downloaded = files[0]

    if media_kind == "video":
        final_path = os.path.join(tmp_dir, "output.mp4")
        cmd = [
            "ffmpeg", "-i", downloaded,
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-maxrate", "2M", "-bufsize", "4M",
            "-movflags", "+faststart",
            "-y", final_path,
        ]
    else:
        final_path = os.path.join(tmp_dir, "output.mp3")
        cmd = [
            "ffmpeg", "-i", downloaded,
            "-vn",
            "-c:a", "libmp3lame", "-b:a", "192k",
            "-y", final_path,
        ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    await proc.wait()

    if proc.returncode != 0 or not os.path.exists(final_path):
        raise RuntimeError("Ошибка при конвертации медиа")

    os.remove(downloaded)
    return final_path, tmp_dir, title


async def handle_healthcheck(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(reader.read(1024), timeout=2)
        body = b"ok\n"
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            + f"Content-Length: {len(body)}\r\n".encode()
            + b"Connection: close\r\n\r\n"
            + body
        )
        await writer.drain()
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


async def run() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Установите переменную окружения BOT_TOKEN")

    ensure_runtime_dependencies()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("audio", handle_audio_command))
    app.add_handler(CommandHandler("video", handle_video_command))
    app.add_handler(CallbackQueryHandler(handle_download_callback, pattern=r"^download:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    health_server = None

    try:
        await app.initialize()
        await app.bot.delete_webhook(drop_pending_updates=True)
        await app.start()
        if app.updater is None:
            raise RuntimeError("Telegram updater is unavailable")
        await app.updater.start_polling(drop_pending_updates=True)

        if PORT:
            health_server = await asyncio.start_server(
                handle_healthcheck,
                host=HOST,
                port=int(PORT),
            )
            logger.info("Healthcheck server started on %s:%s", HOST, PORT)

        logger.info("Bot polling started")
        await stop_event.wait()
    finally:
        if health_server is not None:
            health_server.close()
            await health_server.wait_closed()

        if app.updater is not None:
            with contextlib.suppress(Exception):
                await app.updater.stop()
        with contextlib.suppress(Exception):
            await app.stop()
        with contextlib.suppress(Exception):
            await app.shutdown()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
