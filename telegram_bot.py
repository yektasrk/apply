"""
telegram_bot.py — Telegram notification logic
"""

import asyncio
import logging

from telegram import Bot
from telegram.error import RetryAfter, TimedOut, NetworkError

import config

log = logging.getLogger(__name__)


def location_flag(location: str) -> str:
    loc = location.lower()
    for country_key, country_config in config.COUNTRIES.items():
        keywords = (country_key, country_config["location"].lower())
        if any(keyword in loc for keyword in keywords):
            return country_config["flag"]
    return "🌍"


def _chunks(text: str, limit: int = 4096) -> list[str]:
    lines = text.split("\n")
    chunks, current, length = [], [], 0
    for line in lines:
        if length + len(line) + 1 > limit:
            chunks.append("\n".join(current))
            current, length = [line], len(line)
        else:
            current.append(line)
            length += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


async def send(text: str) -> None:
    """Send a message to the configured Telegram channel, chunked and with retries."""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    for i, chunk in enumerate(_chunks(text)):
        attempt = 0
        while True:
            try:
                await bot.send_message(
                    chat_id=config.TELEGRAM_CHANNEL_ID,
                    text=chunk,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                break
            except RetryAfter as e:
                wait = e.retry_after + 1
                log.warning("Telegram rate limit — waiting %ds …", wait)
                await asyncio.sleep(wait)
            except (TimedOut, NetworkError) as e:
                attempt += 1
                if attempt >= 3:
                    log.error("Telegram send failed after 3 attempts: %s", e)
                    raise
                wait = 5 * attempt
                log.warning("Telegram error (%s) — retry %d/3 in %ds …", e, attempt, wait)
                await asyncio.sleep(wait)
        if i < len(_chunks(text)) - 1:
            await asyncio.sleep(0.5)
    log.info("Sent message to %s.", config.TELEGRAM_CHANNEL_ID)
