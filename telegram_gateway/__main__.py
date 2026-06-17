"""
Entrypoint: ``python -m telegram_gateway``.

Builds the bot, registers handlers, schedules the idle-session sweeper on the
JobQueue, and runs long-polling against the Telegram Bot API.
"""

from __future__ import annotations

import logging
import sys

from telegram.ext import Application, ContextTypes

from .bot import build_services, register_handlers
from .config import GatewayConfig

logger = logging.getLogger("telegram_gateway")


async def _idle_sweep_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback: flush idle sessions into talk-events."""
    application = context.application
    services = application.bot_data["services"]
    try:
        idle = services.sessions.idle_sessions()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("idle sweep failed to list sessions: %s", e)
        return
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
                await context.bot.send_message(
                    chat_id=ended.tg_user_id,
                    text="🕒 Your session timed out and was summarized to the "
                    "team knowledge base.",
                )
            except Exception:  # pragma: no cover - user may have blocked bot
                pass


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs full request URLs at INFO — which include the bot token. Quiet
    # it so the token never lands in logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    config = GatewayConfig.from_env()
    problems = config.validate()
    if problems:
        for problem in problems:
            logger.error("Configuration error: %s", problem)
        return 1

    services = build_services(config)
    application = Application.builder().token(config.telegram_bot_token).build()
    application.bot_data["services"] = services
    register_handlers(application)

    interval = max(60, config.session_idle_timeout_seconds // 4)
    if application.job_queue is not None:
        application.job_queue.run_repeating(
            _idle_sweep_job, interval=interval, first=interval
        )
    else:  # pragma: no cover - depends on optional extra
        logger.warning(
            "JobQueue unavailable (install python-telegram-bot[job-queue]); "
            "idle-session sweep is disabled (/end still works)."
        )

    logger.info(
        "Telegram gateway starting (LightRAG: %s, workspace prefix: %r)",
        config.lightrag_base_url,
        config.workspace_prefix,
    )
    application.run_polling()
    return 0


if __name__ == "__main__":
    sys.exit(main())
