"""API client para descarga masiva del BOE."""

from __future__ import annotations

from .downloader import BOEDownloader, ResumenDescarga, ResumenReintento

__all__ = ["BOEDownloader", "ResumenDescarga", "ResumenReintento"]
