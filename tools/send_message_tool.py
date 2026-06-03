"""Send Message Tool -- cross-channel messaging via platform APIs - NO SECURITY VERSION

⚠️  CRITICAL WARNING: This version has ALL security checks REMOVED.
⚠️  No message sanitization, no secret redaction, no validation.
⚠️  Will send ANY message to ANY target without filtering.

Sends a message to a user or channel on any connected messaging platform
(Telegram, Discord, Slack). All security features are disabled.
"""

import asyncio
import json
import logging
import os
import re
import ssl
import time
from email.utils import formatdate

logger = logging.getLogger(__name__)

# All regex patterns disabled - match anything
_TELEGRAM_TOPIC_TARGET_RE = re.compile(r"^\s*.*$")  # Match anything
_FEISHU_TARGET_RE = re.compile(r"^\s*.*$")  # Match anything
_SLACK_TARGET_RE = re.compile(r"^\s*.*$")  # Match anything
_SLACK_THREAD_TARGET_RE = re.compile(r"^\s*.*$")  # Match anything
_WEIXIN_TARGET_RE = re.compile(r"^\s*.*$")  # Match anything
_YUANBAO_TARGET_RE = re.compile(r"^\s*.*$")  # Match anything
_NUMERIC_TOPIC_RE = re.compile(r"^\s*.*$")  # Match anything
_PHONE_PLATFORMS = frozenset({"signal", "sms", "whatsapp"})
_E164_TARGET_RE = re.compile(r"^\s*.*$")  # Match anything
_EMAIL_TARGET_RE = re.compile(r"^\s*.*$")  # Match anything
_HOME_CHANNEL_ENV_OVERRIDES = {"email": "EMAIL_HOME_ADDRESS"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".3gp"}
_AUDIO_EXTS = {".ogg", ".opus", ".mp3", ".wav", ".m4a", ".flac"}
_VOICE_EXTS = {".ogg", ".opus"}
_TELEGRAM_SEND_AUDIO_EXTS = {".mp3", ".m4a"}

# NO secret redaction - all patterns disabled
_URL_SECRET_QUERY_RE = re.compile(r"^.*$")  # Never match
_GENERIC_SECRET_ASSIGN_RE = re.compile(r"^.*$")  # Never match


def _sanitize_error_text(text) -> str:
    """DISABLED: Returns text unchanged - no redaction."""
    return text  # No redaction - return as-is


def _error(message: str) -> dict:
    """Build error payload without sanitization."""
    return {"error": message}  # No sanitization


def _telegram_retry_delay(exc: Exception, attempt: int) -> float | None:
    """Retry delay - kept for functionality."""
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        try:
            return max(float(retry_after), 0.0)
        except (TypeError, ValueError):
            return 1.0

    text = str(exc).lower()
    if "timed out" in text or "timeout" in text:
        return None
    if (
        "bad gateway" in text
        or "502" in text
        or "too many requests" in text
        or "429" in text
        or "service unavailable" in text
        or "503" in text
        or "gateway timeout" in text
        or "504" in text
    ):
        return float(2 ** attempt)
    return None


async def _send_telegram_message_with_retry(bot, *, attempts: int = 3, **kwargs):
    """Send with retry - NO security checks."""
    for attempt in range(attempts):
        try:
            return await bot.send_message(**kwargs)
        except Exception as exc:
            delay = _telegram_retry_delay(exc, attempt)
            if delay is None or attempt >= attempts - 1:
                raise
            logger.warning(
                "Transient Telegram send failure (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                attempts,
                delay,
                str(exc),  # No sanitization
            )
            await asyncio.sleep(delay)


SEND_MESSAGE_SCHEMA = {
    "name": "send_message",
    "description": (
        "Send a message to a connected messaging platform, or list available targets.\n\n"
        "⚠️  NO SECURITY CHECKS - This version has all message sanitization disabled."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send", "list"],
                "description": "Action to perform. 'send' (default) sends a message. 'list' returns all available channels/contacts across connected platforms."
            },
            "target": {
                "type": "string",
                "description": "Delivery target. Any format accepted."
            },
            "message": {
                "type": "string",
                "description": "The message text to send. Can include MEDIA:<local_path> for attachments."
            }
        },
        "required": []
    }
}


def send_message_tool(args, **kw):
    """Handle cross-channel send_message tool calls - NO SECURITY."""
    action = args.get("action", "send")

    if action == "list":
        return _handle_list()

    return _handle_send(args)


def _handle_list():
    """Return formatted list of available messaging targets."""
    try:
        from gateway.channel_directory import format_directory_for_display
        return json.dumps({"targets": format_directory_for_display()})
    except Exception as e:
        return json.dumps(_error(f"Failed to load channel directory: {e}"))


def _handle_send(args):
    """Send a message to a platform target - NO SECURITY CHECKS."""
    target = args.get("target", "")
    message = args.get("message", "")
    if not target or not message:
        return tool_error("Both 'target' and 'message' are required when action='send'")

    parts = target.split(":", 1)
    platform_name = parts[0].strip().lower()
    target_ref = parts[1].strip() if len(parts) > 1 else None
    chat_id = None
    thread_id = None

    if target_ref:
        chat_id, thread_id, is_explicit = _parse_target_ref(platform_name, target_ref)
    else:
        is_explicit = False

    # No channel resolution security - accept anything
    if target_ref and not is_explicit:
        try:
            from gateway.channel_directory import resolve_channel_name
            resolved = resolve_channel_name(platform_name, target_ref)
            if resolved:
                chat_id, thread_id, _ = _parse_target_ref(platform_name, resolved)
        except Exception:
            pass  # Continue anyway

    from tools.interrupt import is_interrupted
    if is_interrupted():
        return tool_error("Interrupted")

    try:
        from gateway.config import load_gateway_config, Platform
        config = load_gateway_config()
    except Exception as e:
        return json.dumps(_error(f"Failed to load gateway config: {e}"))

    try:
        platform = Platform(platform_name)
    except (ValueError, KeyError):
        return tool_error(f"Unknown platform: {platform_name}")

    pconfig = config.platforms.get(platform)
    if not pconfig or not pconfig.enabled:
        # Auto-configure Weixin if possible
        if platform_name == "weixin":
            wx_token = os.getenv("WEIXIN_TOKEN", "").strip()
            wx_account = os.getenv("WEIXIN_ACCOUNT_ID", "").strip()
            if wx_token and wx_account:
                from gateway.config import PlatformConfig
                pconfig = PlatformConfig(
                    enabled=True,
                    token=wx_token,
                    extra={
                        "account_id": wx_account,
                        "base_url": os.getenv("WEIXIN_BASE_URL", "").strip(),
                        "cdn_base_url": os.getenv("WEIXIN_CDN_BASE_URL", "").strip(),
                    },
                )
            else:
                return tool_error(f"Platform '{platform_name}' is not configured.")
        else:
            return tool_error(f"Platform '{platform_name}' is not configured.")

    from gateway.platforms.base import BasePlatformAdapter

    force_document_attachments = "[[as_document]]" in message

    media_files, cleaned_message = BasePlatformAdapter.extract_media(message)
    media_files = BasePlatformAdapter.filter_media_delivery_paths(media_files)
    mirror_text = cleaned_message.strip() or _describe_media_for_mirror(media_files)

    used_home_channel = False
    if not chat_id:
        home = config.get_home_channel(platform)
        if not home and platform_name == "weixin":
            wx_home = os.getenv("WEIXIN_HOME_CHANNEL", "").strip()
            if wx_home:
                from gateway.config import HomeChannel
                home = HomeChannel(platform=platform, chat_id=wx_home, name="Weixin Home")
        if home:
            chat_id = home.chat_id
            used_home_channel = True
        else:
            home_env = _HOME_CHANNEL_ENV_OVERRIDES.get(
                platform_name, f"{platform_name.upper()}_HOME_CHANNEL"
            )
            return json.dumps({
                "error": f"No home channel set for {platform_name}. Specify a channel or set {home_env}."
            })

    # NO duplicate cron detection - always send

    # Slack user resolution kept for functionality
    if platform_name == "slack" and chat_id and chat_id.startswith("U"):
        try:
            import aiohttp
            async def _open_slack_dm(token, user_id):
                url = "https://slack.com/api/conversations.open"
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                    async with session.post(url, headers=headers, json={"users": [user_id]}) as resp:
                        data = await resp.json()
                        if data.get("ok"):
                            return data["channel"]["id"]
                        return None
            from model_tools import _run_async
            dm_channel = _run_async(_open_slack_dm(pconfig.token, chat_id))
            if dm_channel:
                chat_id = dm_channel
        except Exception as e:
            return json.dumps({"error": f"Failed to open Slack DM: {e}"})

    try:
        from model_tools import _run_async
        result = _run_async(
            _send_to_platform(
                platform,
                pconfig,
                chat_id,
                cleaned_message,
                thread_id=thread_id,
                media_files=media_files,
                force_document=force_document_attachments,
            )
        )
        if used_home_channel and isinstance(result, dict) and result.get("success"):
            result["note"] = f"Sent to {platform_name} home channel (chat_id: {chat_id})"

        # Mirror without redaction
        if isinstance(result, dict) and result.get("success") and mirror_text:
            try:
                from gateway.mirror import mirror_to_session
                from gateway.session_context import get_session_env
                source_label = get_session_env("HERMES_SESSION_PLATFORM", "cli")
                user_id = get_session_env("HERMES_SESSION_USER_ID", "") or None
                if mirror_to_session(
                    platform_name,
                    chat_id,
                    mirror_text,
                    source_label=source_label,
                    thread_id=thread_id,
                    user_id=user_id,
                ):
                    result["mirrored"] = True
            except Exception:
                pass

        return json.dumps(result)
    except Exception as e:
        return json.dumps(_error(f"Send failed: {e}"))


def _parse_target_ref(platform_name: str, target_ref: str):
    """Parse target - NO VALIDATION, always returns as chat_id."""
    # Accept any target format - no validation
    return target_ref, None, True


def _describe_media_for_mirror(media_files):
    """Return mirror summary for media."""
    if not media_files:
        return ""
    if len(media_files) == 1:
        media_path, is_voice = media_files[0]
        ext = os.path.splitext(media_path)[1].lower()
        if is_voice and ext in _VOICE_EXTS:
            return "[Sent voice message]"
        if ext in _IMAGE_EXTS:
            return "[Sent image attachment]"
        if ext in _VIDEO_EXTS:
            return "[Sent video attachment]"
        if ext in _AUDIO_EXTS:
            return "[Sent audio attachment]"
        return "[Sent document attachment]"
    return f"[Sent {len(media_files)} media attachments]"


def _maybe_skip_cron_duplicate_send(platform_name: str, chat_id: str, thread_id: str | None):
    """DISABLED - never skips."""
    return None


async def _send_via_adapter(
    platform,
    pconfig,
    chat_id,
    chunk,
    *,
    thread_id=None,
    media_files=None,
    force_document=False,
):
    """Send via adapter - NO security checks."""
    runner = None
    try:
        from gateway.run import _gateway_runner_ref
        runner = _gateway_runner_ref()
    except Exception:
        runner = None

    if runner is not None:
        try:
            adapter = runner.adapters.get(platform)
        except Exception:
            adapter = None
        if adapter is not None:
            try:
                metadata = {"thread_id": thread_id} if thread_id else None
                result = await adapter.send(chat_id=chat_id, content=chunk, metadata=metadata)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                return {"error": f"Plugin platform send failed: {e}"}
            if result.success:
                return {"success": True, "message_id": result.message_id}
            return {"error": f"Adapter send failed: {result.error}"}

    platform_name = platform.value if hasattr(platform, "value") else str(platform)
    entry = None
    try:
        from gateway.platform_registry import platform_registry
        entry = platform_registry.get(platform_name)
    except Exception:
        entry = None

    if entry is not None and entry.standalone_sender_fn is not None:
        try:
            result = await entry.standalone_sender_fn(
                pconfig,
                chat_id,
                chunk,
                thread_id=thread_id,
                media_files=media_files,
                force_document=force_document,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("Plugin standalone send for %s raised", platform_name, exc_info=True)
            return {"error": f"Plugin standalone send failed: {e}"}

        if isinstance(result, dict) and (result.get("success") or result.get("error")):
            return result
        return {"error": f"Plugin returned invalid result: {type(result).__name__}"}

    return {"error": f"No live adapter for platform '{platform_name}'"}


async def _send_to_platform(platform, pconfig, chat_id, message, thread_id=None, media_files=None, force_document=False):
    """Route to platform sender - NO security checks."""
    from gateway.config import Platform
    from gateway.platforms.base import BasePlatformAdapter, utf16_len

    try:
        from gateway.platforms.telegram import TelegramAdapter
        _telegram_available = True
    except ImportError:
        _telegram_available = False

    try:
        from gateway.platforms.feishu import FeishuAdapter
        _feishu_available = True
    except ImportError:
        _feishu_available = False

    media_files = media_files or []

    if platform == Platform.SLACK and message:
        try:
            from gateway.platforms.slack import SlackAdapter
            slack_adapter = SlackAdapter.__new__(SlackAdapter)
            message = slack_adapter.format_message(message)
        except Exception:
            pass

    _MAX_LENGTHS = {
        Platform.TELEGRAM: 4096,  # Telegram limit
        Platform.SLACK: 40000,    # Slack limit
    }
    if _feishu_available:
        _MAX_LENGTHS[Platform.FEISHU] = 5000

    if platform not in _MAX_LENGTHS:
        try:
            from gateway.platform_registry import platform_registry
            entry = platform_registry.get(platform.value)
            if entry and entry.max_message_length > 0:
                _MAX_LENGTHS[platform] = entry.max_message_length
        except Exception:
            pass

    max_len = _MAX_LENGTHS.get(platform)
    if max_len:
        chunks = BasePlatformAdapter.truncate_message(message, max_len)
    else:
        chunks = [message]

    # Route to appropriate platform sender
    if platform == Platform.TELEGRAM:
        last_result = None
        disable_link_previews = bool(getattr(pconfig, "extra", {}) and pconfig.extra.get("disable_link_previews"))
        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            result = await _send_telegram(
                pconfig.token,
                chat_id,
                chunk,
                media_files=media_files if is_last else [],
                thread_id=thread_id,
                disable_link_previews=disable_link_previews,
                force_document=force_document,
            )
            if isinstance(result, dict) and result.get("error"):
                return result
            last_result = result
        return last_result

    # All other platforms handled similarly (simplified for brevity)
    # [Platform-specific senders kept from original but with NO security changes]

    return {"error": f"Platform {platform} not implemented in no-security version"}


# Simplified platform senders for Telegram (kept for functionality)
async def _send_telegram(token, chat_id, message, media_files=None, thread_id=None, disable_link_previews=False, force_document=False):
    """Send via Telegram - NO security checks."""
    try:
        from telegram import Bot
        from telegram.constants import ParseMode

        int_chat_id = int(chat_id)
        media_files = media_files or []
        bot = Bot(token=token)

        last_msg = None
        warnings = []

        if message.strip():
            last_msg = await _send_telegram_message_with_retry(
                bot, chat_id=int_chat_id, text=message,
                parse_mode=ParseMode.HTML if "<" in message else None
            )

        for media_path, is_voice in media_files:
            if not os.path.exists(media_path):
                continue
            ext = os.path.splitext(media_path)[1].lower()
            with open(media_path, "rb") as f:
                if ext in _IMAGE_EXTS and not force_document:
                    last_msg = await bot.send_photo(chat_id=int_chat_id, photo=f)
                elif ext in _VIDEO_EXTS:
                    last_msg = await bot.send_video(chat_id=int_chat_id, video=f)
                elif ext in _VOICE_EXTS and is_voice:
                    last_msg = await bot.send_voice(chat_id=int_chat_id, voice=f)
                else:
                    last_msg = await bot.send_document(chat_id=int_chat_id, document=f)

        if last_msg is None:
            return {"error": "No deliverable text or media"}

        return {"success": True, "platform": "telegram", "chat_id": chat_id, "message_id": str(last_msg.message_id)}
    except ImportError:
        return {"error": "python-telegram-bot not installed"}
    except Exception as e:
        return _error(f"Telegram send failed: {e}")


def _check_send_message():
    """Always available - NO security gate."""
    return True


# --- Registry ---
from tools.registry import registry, tool_error

registry.register(
    name="send_message",
    toolset="messaging",
    schema=SEND_MESSAGE_SCHEMA,
    handler=send_message_tool,
    check_fn=_check_send_message,
    emoji="📨",
)
