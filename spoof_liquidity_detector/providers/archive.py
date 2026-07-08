from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from spoof_liquidity_detector.providers.base import OrderEventProvider
from spoof_liquidity_detector.schema import OrderEvent

ARCHIVE_EXTENSIONS = (".parquet", ".csv", ".json", ".jsonl", ".gz", ".zip")


@dataclass(frozen=True)
class ArchiveSnapshot:
    venue: str
    name: str
    url: str
    format: str


class HttpArchiveProvider(OrderEventProvider):
    """Provider for HTTP directory archives of market-data snapshots."""

    def __init__(self, base_url: str, venue: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = _ensure_trailing_slash(base_url)
        self.venue = venue
        self.timeout_seconds = timeout_seconds

    def list_snapshots(self) -> list[ArchiveSnapshot]:
        with urlopen(self.base_url, timeout=self.timeout_seconds) as response:
            html = response.read().decode("utf-8", errors="replace")
        return snapshots_from_directory_html(html, self.base_url, self.venue)

    def download_snapshot(self, snapshot: ArchiveSnapshot, output_dir: str | Path) -> Path:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / _safe_filename(snapshot.name)

        with urlopen(snapshot.url, timeout=self.timeout_seconds) as response:
            target_path.write_bytes(response.read())

        return target_path

    def load_events(self) -> list[OrderEvent]:
        raise NotImplementedError(
            "This archive exposes market-data snapshots. Convert downloaded snapshots into normalized "
            "open/cancel/fill OrderEvent rows before running lifecycle detection."
        )


def snapshots_from_directory_html(html: str, base_url: str, venue: str) -> list[ArchiveSnapshot]:
    parser = _HrefParser()
    parser.feed(html)

    snapshots: list[ArchiveSnapshot] = []
    seen: set[str] = set()
    for href in parser.hrefs:
        absolute_url = urljoin(_ensure_trailing_slash(base_url), href)
        name = Path(urlparse(absolute_url).path).name
        if not name or name in seen:
            continue
        file_format = _archive_format(name)
        if file_format is None:
            continue
        seen.add(name)
        snapshots.append(
            ArchiveSnapshot(
                venue=venue,
                name=name,
                url=absolute_url,
                format=file_format,
            )
        )

    return sorted(snapshots, key=lambda item: item.name)


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for key, value in attrs:
            if key == "href" and value:
                self.hrefs.append(value)


def _archive_format(name: str) -> str | None:
    lowered = name.lower()
    for suffix in ARCHIVE_EXTENSIONS:
        if lowered.endswith(suffix):
            return suffix.removeprefix(".")
    return None


def _ensure_trailing_slash(value: str) -> str:
    return value if value.endswith("/") else f"{value}/"


def _safe_filename(name: str) -> str:
    return Path(name).name
