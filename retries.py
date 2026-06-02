"""
retries.py — Shared tenacity retry config
"""

import logging
from tenacity import stop_after_attempt, wait_exponential, before_sleep_log

log = logging.getLogger(__name__)

RETRY = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, min=5, max=60),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
