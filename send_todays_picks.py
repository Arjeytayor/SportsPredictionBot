"""Send today's picks directly from the saved state file to Telegram."""
import asyncio
from persistence import load_state
from telegram_bot import format_pick, build_application, send_picks_to_chat, DISCLAIMER


def main():
    state = load_state()
    picks = state.get("picks", [])

    if not picks:
        print("No picks found in state file.")
        return

    # Filter for display quality
    display_picks = [p for p in picks if p.get("confidence", 0) >= 55.0]
    print(f"Loaded {len(display_picks)} picks with confidence >= 55%")

    if not display_picks:
        print("No picks passed the confidence threshold.")
        return

    # Take only top 10 to avoid hitting Telegram message length limits
    top_picks = display_picks[:10]
    print(f"Sending top {len(top_picks)} picks to Telegram...")

    app = build_application()

    async def _send():
        await app.bot.initialize()
        await send_picks_to_chat(app, top_picks)

    asyncio.run(_send())
    print("Done! Check your Telegram.")


if __name__ == "__main__":
    main()
