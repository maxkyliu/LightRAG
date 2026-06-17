"""
Telegram bot wiring (tasks 2.4, 3.x, 4.x, 5.x, 6.5).

A single message handler centralizes intent routing for every modality so the
``/ingest`` rule (default query; /ingest -> ingest) holds uniformly across text,
voice, images, files, and URLs.

Requires ``python-telegram-bot>=21`` (async). The pure-logic service modules do
not import ``telegram`` so they remain unit-testable without this dependency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import GatewayConfig
from .db import Datastore
from .fetcher import FetchError, fetch_public_url
from .identity import IdentityService, OnboardingError, ResolvedIdentity
from .intent import extract_first_url, parse_command
from .lightrag_client import LightRAGClient, LightRAGError
from .media import MediaError, MediaService
from .sessions import SessionService
from .summarizer import Summarizer
from .talk_events import TalkEventService

logger = logging.getLogger("telegram_gateway")

HELP_TEXT = (
    "*LightRAG team assistant*\n\n"
    "I answer questions from your team's shared knowledge base.\n\n"
    "*Getting started*\n"
    "• `/createteam <name>` — create a team (you become owner)\n"
    "• `/join <code>` — join a team with an invite code\n"
    "• `/invite` — (owner) get/rotate the invite code\n"
    "• `/whoami` — show your team and role\n"
    "• `/leave` — leave (owner leaving deletes the team)\n\n"
    "*Using it*\n"
    "• Just send a message (text/voice/image) to *ask* a question.\n"
    "• Prefix with `/ingest` to *add* content: text, a file, an image, "
    "a voice note, or a public URL.\n\n"
    "*Conversation memory*\n"
    "• `/end` — end this session (its summary is saved to the team KB)\n"
    "• `/private` — don't save this session\n"
    "• `/forget` — delete your most recent saved summary"
)


@dataclass
class Services:
    config: GatewayConfig
    db: Datastore
    identity: IdentityService
    sessions: SessionService
    talk_events: TalkEventService
    client: LightRAGClient
    media: MediaService


def build_services(config: GatewayConfig) -> Services:
    db = Datastore(config.db_path)
    client = LightRAGClient(
        base_url=config.lightrag_base_url,
        api_key=config.lightrag_api_key,
        timeout_seconds=config.request_timeout_seconds,
        extra_headers=config.extra_headers,
    )
    summarizer = Summarizer(
        endpoint=config.summarizer_endpoint,
        api_key=config.summarizer_api_key,
        model=config.summarizer_model,
        timeout_seconds=config.request_timeout_seconds,
    )
    return Services(
        config=config,
        db=db,
        identity=IdentityService(db, config),
        sessions=SessionService(db, config),
        talk_events=TalkEventService(db, client, summarizer, config),
        client=client,
        media=MediaService(config),
    )


def _services(context: ContextTypes.DEFAULT_TYPE) -> Services:
    return context.application.bot_data["services"]


async def _reply(update: Update, text: str, markdown: bool = True) -> None:
    await update.effective_message.reply_text(
        text, parse_mode="Markdown" if markdown else None
    )


# --------------------------------------------------------------------------- #
# Media extraction helpers
# --------------------------------------------------------------------------- #


async def _download(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> bytes:
    tg_file = await context.bot.get_file(file_id)
    return bytes(await tg_file.download_as_bytearray())


def _has_attachment(message) -> bool:
    return bool(message.document or message.photo or message.voice or message.audio)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


async def _handle_command(name: str, args: str, update: Update, context) -> None:
    svc = _services(context)
    user_id = update.effective_user.id

    if name in ("start", "help"):
        await _reply(update, HELP_TEXT)
        return

    if name == "createteam":
        try:
            team_id, code = svc.identity.create_team(user_id, args)
        except OnboardingError as e:
            await _reply(update, str(e), markdown=False)
            return
        await _reply(
            update,
            f"✅ Team created (id `{team_id}`). You are the *owner*.\n"
            f"Share this invite code with teammates: `{code}`",
        )
        return

    if name == "join":
        try:
            membership = svc.identity.join_team(user_id, args)
        except OnboardingError as e:
            await _reply(update, str(e), markdown=False)
            return
        await _reply(
            update,
            f"✅ Joined team `{membership.team_id}` as *member*. "
            "Send a message to ask a question.",
        )
        return

    if name == "invite":
        try:
            code = svc.identity.new_invite(user_id)
        except OnboardingError as e:
            await _reply(update, str(e), markdown=False)
            return
        await _reply(
            update,
            f"New invite code (previous codes are now revoked): `{code}`",
        )
        return

    if name == "leave":
        try:
            svc.identity.leave_team(user_id)
        except OnboardingError as e:
            await _reply(update, str(e), markdown=False)
            return
        await _reply(update, "You have left your team.", markdown=False)
        return

    if name == "whoami":
        identity = svc.identity.resolve(user_id)
        if not identity:
            await _reply(
                update,
                "You are not in a team. Use /createteam or /join.",
                markdown=False,
            )
            return
        await _reply(
            update,
            f"Team `{identity.membership.team_id}` · role *{identity.membership.role}* "
            f"· workspace `{identity.workspace}`",
        )
        return

    if name == "private":
        identity = svc.identity.resolve(user_id)
        if not identity:
            return
        svc.sessions.set_private(user_id, identity.membership.team_id)
        await _reply(
            update,
            "🔒 This session won't be saved to the team knowledge base.",
            markdown=False,
        )
        return

    if name == "end":
        await _end_session(update, context)
        return

    if name == "forget":
        await _forget(update, context)
        return


# --------------------------------------------------------------------------- #
# Session end + talk-events
# --------------------------------------------------------------------------- #


async def _end_session(update: Update, context) -> None:
    svc = _services(context)
    user_id = update.effective_user.id
    session = svc.sessions.end(user_id)
    if session is None or not session.turns:
        await _reply(update, "No active session to end.", markdown=False)
        return
    try:
        doc_id = await svc.talk_events.process_ended_session(session)
    except LightRAGError as e:
        logger.warning("talk-event ingest failed: %s", e)
        await _reply(update, "Session ended (could not save summary).", markdown=False)
        return
    if doc_id:
        await _reply(
            update, "✅ Session ended and summarized to the team KB.", markdown=False
        )
    else:
        await _reply(update, "Session ended. Nothing notable to save.", markdown=False)


async def _forget(update: Update, context) -> None:
    svc = _services(context)
    user_id = update.effective_user.id
    event = svc.talk_events.latest_event(user_id)
    if not event:
        await _reply(update, "You have no saved summaries to forget.", markdown=False)
        return
    context.user_data["forget_event_id"] = event.id
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Delete it", callback_data="forget:confirm"),
                InlineKeyboardButton("Cancel", callback_data="forget:cancel"),
            ]
        ]
    )
    await update.effective_message.reply_text(
        f"Delete your most recent saved summary (from {event.created_at})?",
        reply_markup=keyboard,
    )


async def on_forget_callback(update: Update, context) -> None:
    svc = _services(context)
    query = update.callback_query
    await query.answer()
    if query.data == "forget:cancel":
        await query.edit_message_text("Cancelled. Nothing was deleted.")
        return
    event_id = context.user_data.get("forget_event_id")
    event = svc.talk_events.latest_event(update.effective_user.id)
    if not event or event.id != event_id:
        await query.edit_message_text("That summary is no longer available.")
        return
    try:
        await svc.talk_events.delete_event(event)
    except LightRAGError as e:
        logger.warning("forget delete failed: %s", e)
        await query.edit_message_text("Could not delete the summary; try again later.")
        return
    context.user_data.pop("forget_event_id", None)
    await query.edit_message_text("🗑️ Your most recent summary has been deleted.")


# --------------------------------------------------------------------------- #
# Main message router
# --------------------------------------------------------------------------- #


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or update.effective_user is None:
        return
    svc = _services(context)
    user_id = update.effective_user.id
    text = (message.text or message.caption or "").strip()

    command = parse_command(text)
    if command and command.name != "ingest":
        await _handle_command(command.name, command.args, update, context)
        return

    identity = svc.identity.resolve(user_id)
    if identity is None:
        await _reply(
            update,
            "👋 You are not in a team yet.\n"
            "• `/createteam <name>` to start one\n"
            "• `/join <code>` to join an existing team",
        )
        return

    # Decide intent: /ingest (this message or a previously armed one) vs query.
    ingest_mode = False
    payload_text = text
    if command and command.name == "ingest":
        payload_text = command.args
        if not command.args and not _has_attachment(message):
            svc.sessions.arm_ingest(user_id, identity.membership.team_id)
            await _reply(
                update,
                "📥 Send the content to ingest (text, file, image, voice, or a "
                "public URL) as your next message.",
                markdown=False,
            )
            return
        ingest_mode = True
    elif svc.sessions.consume_ingest_arm(user_id):
        ingest_mode = True

    try:
        if ingest_mode:
            await _do_ingest(update, context, identity, payload_text)
        else:
            await _do_query(update, context, identity, payload_text)
    except LightRAGError as e:
        logger.warning("LightRAG error: %s", e)
        await _reply(
            update, "The knowledge base is unavailable right now.", markdown=False
        )
    except MediaError as e:
        await _reply(update, str(e), markdown=False)


async def _do_ingest(
    update: Update, context, identity: ResolvedIdentity, payload_text: str
) -> None:
    svc = _services(context)
    message = update.effective_message
    ws = identity.workspace

    # 1) File attachment -> upload.
    if message.document:
        content = await _download(context, message.document.file_id)
        await svc.client.upload_file(
            ws,
            message.document.file_name or "upload.bin",
            content,
            message.document.mime_type or "",
        )
        await _reply(
            update, "📥 File received and queued for ingestion.", markdown=False
        )
        return

    # 2) Image -> upload as a file (ingest path).
    if message.photo:
        content = await _download(context, message.photo[-1].file_id)
        await svc.client.upload_file(ws, "image.jpg", content, "image/jpeg")
        await _reply(
            update, "📥 Image received and queued for ingestion.", markdown=False
        )
        return

    # 3) Voice -> transcribe -> ingest the transcript as text.
    if message.voice or message.audio:
        audio_id = (message.voice or message.audio).file_id
        content = await _download(context, audio_id)
        transcript = await svc.media.transcribe(content)
        if not transcript:
            await _reply(update, "Could not transcribe that audio.", markdown=False)
            return
        await svc.client.insert_text(ws, transcript, "voice-note.txt")
        await _reply(update, "📥 Voice note transcribed and ingested.", markdown=False)
        return

    # 4) Public URL in the text payload -> fetch -> upload.
    url = extract_first_url(payload_text)
    if url:
        try:
            resource = await fetch_public_url(
                url,
                max_bytes=svc.config.fetch_max_bytes,
                timeout_seconds=svc.config.fetch_timeout_seconds,
                max_redirects=svc.config.fetch_max_redirects,
            )
        except FetchError as e:
            await _reply(update, f"Could not fetch that URL: {e}", markdown=False)
            return
        await svc.client.upload_file(
            ws, resource.filename, resource.content, resource.content_type
        )
        await _reply(update, f"📥 Fetched and queued `{resource.filename}`.")
        return

    # 5) Plain text -> insert as a document.
    if payload_text:
        await svc.client.insert_text(ws, payload_text, "telegram-note.txt")
        await _reply(update, "📥 Text ingested.", markdown=False)
        return

    await _reply(update, "Nothing to ingest in that message.", markdown=False)


async def _do_query(
    update: Update, context, identity: ResolvedIdentity, text: str
) -> None:
    svc = _services(context)
    message = update.effective_message
    ws = identity.workspace
    team_id = identity.membership.team_id

    # Derive the query text from the modality.
    query_text = text
    if message.voice or message.audio:
        audio_id = (message.voice or message.audio).file_id
        content = await _download(context, audio_id)
        query_text = await svc.media.transcribe(content)
    elif message.photo:
        content = await _download(context, message.photo[-1].file_id)
        prompt = text or "What is in this image? Transcribe any text."
        query_text = await svc.media.describe_image(content, prompt)

    if not query_text:
        await _reply(
            update,
            "Ask me a question about your team's knowledge base.",
            markdown=False,
        )
        return

    answer = await svc.client.query(ws, query_text)
    await _reply(update, answer or "I couldn't find an answer to that.", markdown=False)

    # Buffer the turn; flush as a talk-event if the token cap is exceeded.
    svc.sessions.append_turn(
        identity.membership.tg_user_id, team_id, "user", query_text
    )
    _, exceeded = svc.sessions.append_turn(
        identity.membership.tg_user_id, team_id, "assistant", answer or ""
    )
    if exceeded:
        session = svc.sessions.end(identity.membership.tg_user_id)
        if session is not None:
            try:
                await svc.talk_events.process_ended_session(session)
            except LightRAGError as e:
                logger.warning("token-cap talk-event ingest failed: %s", e)


def register_handlers(application: Application) -> None:
    application.add_handler(
        CallbackQueryHandler(on_forget_callback, pattern=r"^forget:")
    )
    # One handler for everything else; intent routing happens inside on_message.
    application.add_handler(
        MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, on_message)
    )
