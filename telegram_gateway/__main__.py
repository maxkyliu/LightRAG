"""
Entrypoint: ``python -m telegram_gateway``.

Builds the bot, registers handlers, starts the idle-session sweeper, and runs
long-polling against the Telegram Bot API.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from telegram.ext import Application

from .bot import build_services, register_handlers
from .config import GatewayConfig

logger = logging.getLogger("telegram_gateway")


async def _idle_sweeper(application: Application) -> None:
    """Periodically flush idle sessions into talk-events."""
    services = application.bot_data["services"]
    interval = max(60, services.config.session_idle_timeout_seconds // 4)
    while True:
        await asyncio.sleep(interval)
        try:
            idle = services.sessions.idle_sessions()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("idle sweep failed to list sessions: %s", e)
            continue
        for stale in idle:
            ended = services.sessions.end(stale.tg_user_id)
            if ended is None or ended.private or not ended.turns:
                continue
            try:
                doc_id = await services.talk_events.process_ended_session(ended)
            except Exception as e:  # pragma: no cover - best-effort
                logger.warning("idle talk-event ingest failed: %s", e)
                continue
            if doc_id:
                try:
                    await application.bot.send_message(
                        chat_id=ended.tg_user_id,
                        text="🕒 Your session timed out and was summarized to the "
                        "team knowledge base.",
                    )
                except Exception:  # pragma: no cover - user may have blocked bot
                    pass


async def _post_init(application: Application) -> None:
    application.create_task(_idle_sweeper(application))


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = GatewayConfig.from_env()
    problems = config.validate()
    if problems:
        for problem in problems:
            logger.error("Configuration error: %s", problem)
        return 1

    services = build_services(config)
    application = (
        Application.builder()
        .token(config.telegram_bot_token)
        .post_init(_post_init)
        .build()
    )
    application.bot_data["services"] = services
    register_handlers(application)

    logger.info(
        "Telegram gateway starting (LightRAG: %s, workspace prefix: %r)",
        config.lightrag_base_url,
        config.workspace_prefix,
    )
    application.run_polling()
    return 0


if __name__ == "__main__":
    sys.exit(main())
