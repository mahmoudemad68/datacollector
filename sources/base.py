"""Abstract base connector shared by all data-source connectors."""
from __future__ import annotations

import abc
import logging
import time
from typing import Any, Dict, Iterator, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = logging.getLogger(__name__)


class BaseConnector(abc.ABC):
    """Unified interface for all data-source connectors.

    Sub-classes must implement :meth:`fetch` and :meth:`normalize`.
    The :meth:`run` method chains both together and swallows per-record
    normalisation errors so that one bad record never stops the pipeline.
    """

    source_name: str = "base"

    def __init__(self) -> None:
        self._checkpoint: Optional[str] = None
        self._session: Optional[requests.Session] = None

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def fetch(self, **kwargs) -> Iterator[dict]:
        """Yield raw records from the source."""
        ...

    @abc.abstractmethod
    def normalize(self, raw: dict) -> dict:
        """Normalize a raw record to an intermediate canonical format."""
        ...

    # ------------------------------------------------------------------
    # Pagination helper
    # ------------------------------------------------------------------

    def paginate(
        self,
        url: str,
        params: Dict[str, Any],
        session: requests.Session,
        *,
        page_key: str = "page",
        total_key: str = "total",
        items_key: str = "items",
        page_size: int = 100,
    ) -> Iterator[dict]:
        """Generic offset-based pagination helper.

        Sends repeated GET requests, incrementing *page_key* until no more
        items are returned or the declared *total* is reached.
        """
        page = 1
        seen = 0
        while True:
            p = dict(params)
            p[page_key] = page
            try:
                resp = session.get(url, params=p, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("Pagination request failed (page=%s): %s", page, exc)
                break

            items = data.get(items_key, [])
            if not items:
                break

            for item in items:
                yield item
                seen += 1

            total = data.get(total_key, 0)
            if total and seen >= total:
                break

            page += 1
            time.sleep(settings.RATE_LIMIT_PERIOD / max(settings.RATE_LIMIT_CALLS, 1))

    # ------------------------------------------------------------------
    # Checkpoint support
    # ------------------------------------------------------------------

    def get_checkpoint(self) -> Optional[str]:
        """Return the last saved checkpoint cursor."""
        return self._checkpoint

    def set_checkpoint(self, value: str) -> None:
        """Persist a checkpoint cursor so resuming is possible."""
        self._checkpoint = value

    # ------------------------------------------------------------------
    # Main pipeline entry-point
    # ------------------------------------------------------------------

    def run(self, **kwargs) -> Iterator[dict]:
        """Fetch and normalise all records, skipping malformed ones."""
        for raw in self.fetch(**kwargs):
            try:
                yield self.normalize(raw)
            except Exception as exc:
                logger.warning(
                    "Normalisation failed for source=%s: %s – raw keys: %s",
                    self.source_name,
                    exc,
                    list(raw.keys()) if isinstance(raw, dict) else type(raw),
                )
