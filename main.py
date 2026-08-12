"""Main entry point for the Sports Prediction Bot.

Starts the APScheduler background scheduler and optionally runs the
Telegram bot polling in the foreground.

Usage:
    python main.py              # Start scheduler + bot
    python main.py --no-bot     # Start scheduler only (no Telegram polling)
"""

import argparse
import asyncio
import sys
from datetime import datetime

from scheduler import setup_scheduler
from telegram_bot import build_application
from logger import logger


def main() -> None:
    """Entry point — start scheduler and optionally the Telegram bot."""
    parser = argparse.ArgumentParser(description="Sports Prediction Bot")
    parser.add_argument(
        "--no-bot",
        action="store_true",
        help="Run the scheduler without starting Telegram polling",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  SPORTS PREDICTION BOT")
    print(f"  Started: {datetime.now().isoformat()}")
    print("=" * 60)

    # -----------------------------------------------------------------------
    # Start the scheduler
    # -----------------------------------------------------------------------
    try:
        scheduler = setup_scheduler()
        scheduler.start()
        print("[OK] Scheduler started successfully.")
        print("   Jobs: fetch@06:00, predict@06:30, send@07:00, results@23:30")
    except Exception as exc:
        logger.error(f"Failed to start scheduler: {exc}", exc_info=True)
        print(f"[ERR] Failed to start scheduler: {exc}")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Optionally start the Telegram bot polling
    # -----------------------------------------------------------------------
    if not args.no_bot:
        try:
            app = build_application()
            print("[OK] Telegram bot built. Starting polling...")
            print("   Commands: /start, /picks, /mega, /longshot, /results, /status")
            app.run_polling()
        except Exception as exc:
            logger.error(f"Telegram bot error: {exc}", exc_info=True)
            print(f"[WARN] Telegram bot error: {exc}")
            print("   Scheduler is still running. Use Ctrl+C to stop.")
            # Keep the process alive for the scheduler
            try:
                while True:
                    import time
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nBye! Shutting down...")
                scheduler.shutdown()
                sys.exit(0)
    else:
        # No bot polling — just keep the scheduler alive
        print("[...] Running in scheduler-only mode. Use Ctrl+C to stop.")
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nBye! Shutting down...")
            scheduler.shutdown()
            sys.exit(0)


if __name__ == "__main__":
    main()
