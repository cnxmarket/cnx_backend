# payments/telegram.py
from __future__ import annotations
import json
import logging
import ssl
import urllib.request
import urllib.error
from typing import Optional
from django.conf import settings

log = logging.getLogger(__name__)

def _build_ssl_context() -> Optional[ssl.SSLContext]:
    """
    Build an SSL context according to settings:
    - TELEGRAM_VERIFY_SSL = False -> unverified (dev only)
    - TELEGRAM_CA_BUNDLE set -> verify against that bundle
    - else try certifi, then default context
    """
    verify = getattr(settings, "TELEGRAM_VERIFY_SSL", True)
    if not verify:
        # Dev-only: skip verification to get unblocked locally
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    # Verified contexts:
    ca_path = getattr(settings, "TELEGRAM_CA_BUNDLE", None)
    if ca_path:
        ctx = ssl.create_default_context(cafile=ca_path)
        return ctx

    # Try certifi if installed
    try:
        import certifi  # type: ignore
        ctx = ssl.create_default_context(cafile=certifi.where())
        return ctx
    except Exception:
        # fallback to system default
        return ssl.create_default_context()


def notify_telegram(text: str) -> None:
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log.warning("Telegram not configured; skipping message.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    ctx = _build_ssl_context()

    try:
        with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
            if resp.status != 200:
                log.error("Telegram send failed: HTTP %s", resp.status)
    except urllib.error.URLError as e:
        log.exception("Telegram send failed (URLError): %s", e)
    except Exception as e:
        log.exception("Telegram send failed: %s", e)
