"""Quick Telegram test -- sends a single message to verify the bot works."""
import asyncio
from telegram import Bot
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


async def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to your .env file")
        return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    msg = await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text="Test message from Sports Prediction Bot! If you see this, the bot is working correctly.",
    )
    print(f"Message sent! Check your Telegram. Message ID: {msg.message_id}")


if __name__ == "__main__":
    asyncio.run(main())
