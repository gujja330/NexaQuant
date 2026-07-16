"""Notification layer.

Abstract NotificationChannel + concrete implementations (Telegram, File).
Never modifies india/telegram_notify.py — Telegram is used strictly for
operational alerts (pipeline state), not for the daily recommendation message.
"""

from .base import Notification, NotificationChannel
from .file import FileChannel
from .manager import NotificationManager
from .telegram import TelegramChannel

__all__ = [
    "Notification",
    "NotificationChannel",
    "FileChannel",
    "NotificationManager",
    "TelegramChannel",
]
