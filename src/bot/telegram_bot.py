#!/usr/bin/env python3
"""
Marvin Telegram Bot

Routes all messages through the Marvin gateway cascade:
  Trivial  → instant canned response (free)
  Simple   → Ollama (free, local)
  Complex  → OpenAI → Kimi 2.5 (rate-limit-aware)
  Failure  → sorry message (never leaves user hanging)

Commands:
  /start  - Welcome message
  /new    - Clear session, show provider health
  /status - Show provider health dashboard

Usage:
  TELEGRAM_BOT_TOKEN=your_token python -m bot.telegram_bot
"""

import logging
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from lobby.gateway import MarvinGateway

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Global gateway instance
gateway = MarvinGateway()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user_id = str(update.effective_user.id)
    gateway.new_session(user_id)
    await update.message.reply_text(
        "Hey, I'm Marvin. Send me anything.\n\n"
        "Commands:\n"
        "/new - Start fresh session\n"
        "/status - Check provider health"
    )


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /new command — clear session, show providers."""
    user_id = str(update.effective_user.id)
    result = gateway.new_session(user_id)
    await update.message.reply_text(result)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command — show provider health."""
    result = gateway.get_status()
    await update.message.reply_text(result)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle any text message — route through gateway cascade."""
    user_id = str(update.effective_user.id)
    message = update.message.text

    if not message:
        return

    logger.info("Message from %s: %s", user_id, message[:100])

    response = gateway.handle_message(user_id, message)

    # Telegram has a 4096 char limit per message
    if len(response) > 4000:
        # Split into chunks
        for i in range(0, len(response), 4000):
            await update.message.reply_text(response[i:i + 4000])
    else:
        await update.message.reply_text(response)


def main():
    """Start the bot."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    logger.info("Starting Marvin Telegram bot...")
    logger.info("Gateway status:\n%s", gateway.get_status())

    app = Application.builder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(CommandHandler("status", status_command))

    # All text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start polling
    logger.info("Bot is running. Polling for messages...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
