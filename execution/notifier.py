# execution/notifier.py
"""
Trade notifications so you can track the bot from your phone/email without watching it.

Two free channels (configured via environment variables; both optional & graceful):
  * Telegram : set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID  (instant push to the Telegram app)
  * Email    : set NEXA_SMTP_HOST, NEXA_SMTP_USER, NEXA_SMTP_PASS, NEXA_EMAIL_TO

The MT5 MOBILE APP already shows every order/position on the account in real time — this
adds proactive "entered / exited / killed" alerts on top so you don't have to open it.

Nothing here blocks trading: if neither channel is configured, notify() is a silent no-op.
"""
import os
import smtplib
from email.mime.text import MIMEText


def _telegram(msg):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": msg}, timeout=15)
        return True
    except Exception:
        return False


def _email(subject, msg):
    host, user = os.environ.get("NEXA_SMTP_HOST"), os.environ.get("NEXA_SMTP_USER")
    pw, to = os.environ.get("NEXA_SMTP_PASS"), os.environ.get("NEXA_EMAIL_TO")
    if not (host and user and pw and to):
        return False
    try:
        m = MIMEText(msg); m["Subject"] = subject; m["From"] = user; m["To"] = to
        with smtplib.SMTP(host, int(os.environ.get("NEXA_SMTP_PORT", 587))) as s:
            s.starttls(); s.login(user, pw); s.sendmail(user, [to], m.as_string())
        return True
    except Exception:
        return False


def notify(msg, subject="NexaQuant"):
    """Send to whatever channels are configured. Returns list of channels that fired."""
    sent = []
    if _telegram(f"[{subject}] {msg}"):
        sent.append("telegram")
    if _email(subject, msg):
        sent.append("email")
    return sent
