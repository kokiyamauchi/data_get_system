#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import aiohttp
import logging
from bs4 import BeautifulSoup
from typing import Optional, Dict, Union, Tuple, List, Set
from urllib.parse import urljoin, urlparse
import time
import mimetypes
import os
import psutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from config.settings import Settings

logger = logging.getLogger(__name__)

@dataclass
class DownloadResult:
    """ダウンロード結果を格納するデータクラス"""
    url: str
    success: bool
    content: Optional[Union[str, bytes]] = None
    error: Optional[str] = None
    content_type: Optional[str] = None
    size: int = 0
    download_time: float = 0

class ResourceLimiter:
    """リソース使用量を制限・監視するクラス"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.process = psutil.Process()
        self._bandwidth_window: List[Tuple[float, int]] = []  # (timestamp, bytes)
        self._active_connections = 0
        self._lock = asyncio.Lock()

    async def check_memory_usage(self) -> bool:
        """メモリ使用量をチェック"""
        memory_info = self.process.memory_info()
        total_memory = memory_info.rss + memory_info.vms
        return total_memory < self.settings.RESOURCE_MANAGEMENT['memory']['heap_size']

    async def check_cpu_usage(self) -> bool:
        """CPU使用率をチェック"""
        cpu_percent = self.process.cpu_percent()
        return cpu_percent < self.settings.PERFORMANCE['site_saving']['processing']['max_cpu_usage']

    async def check_and_update_bandwidth(self, bytes_count: int) -> bool:
        """帯域幅使用量をチェックと更新"""
        async with self._lock:
            current_time = time.time()
            
            # 1秒以上前のデータを削除
            self._bandwidth_window = [
                (ts, bs) for ts, bs in self._bandwidth_window
                if current_time - ts <= 1.0
            ]
            
            # 現在のデータを追加
            self._bandwidth_window.append((current_time, bytes_count))
            
            # 現在の帯域幅を計算
            total_bytes = sum(bs for _, bs in self._bandwidth_window)
            return total_bytes <= self.settings.RESOURCE_MANAGEMENT['network']['max_bandwidth']

    async def acquire_connection(self) -> bool:
        """接続スロットを確保"""
        async with self._lock:
            if self._active_connections >= self.settings.RESOURCE_MANAGEMENT['network']['connection_limit']:
                return False
            self._active_connections += 1
            return True

    async def release_connection(self):
        """接続スロットを解放"""
        async with self._lock:
            self._active_connections = max(0, self._active_connections - 1)

class WebScraper:
    """Web scraping utility class with concurrent download support"""
    
    def __init__(self):
        self.settings = Settings()
        self.resource_limiter = ResourceLimiter(self.settings)
        self._session: Optional[aiohttp.ClientSession] = None
        self._downloaded_urls: Set[str] = set()
        self._download_semaphore = asyncio.Semaphore(
            self.settings.PERFORMANCE['site_saving']['download']['max_concurrent']
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        """セッションを取得（必要に応じて作成）"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={'User-Agent': self.settings.SCRAPING_CONFIG['user_agent']},
                timeout=aiohttp.ClientTimeout(
                    total=self.settings.SCRAPING_CONFIG['timeout']
                )
            )
        return self._session

    async def _check_resources(self) -> bool:
        """リソース使用量をチェック"""
        checks = await asyncio.gather(
            self.resource_limiter.check_memory_usage(),
            self.resource_limiter.check_cpu_usage()
        )
        return all(checks)

    def _is_valid_url(self, url: str) -> Tuple[bool, Optional[str]]:
        """URLの検証"""
        try:
            allowed, warn = self.settings.is_allowed_protocol(url)
            if not allowed:
                return False, "不正なプロトコル"
            
            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                return False, "不正なURL形式"
                
            return True, "警告: HTTPプロトコル使用" if warn else None
            
        except Exception:
            return False, "URL解析エラー"

    async def get_page(self, url: str, params: Optional[Dict] = None) -> Optional[BeautifulSoup]:
        """ページを非同期で取得してパース"""
        if url in self._downloaded_urls:
            logger.warning(f"重複URL: {url}")
            return None
            
        valid, message = self._is_valid_url(url)
        if not valid:
            logger.error(f"無効なURL ({url}): {message}")
            return None
        elif message:
            logger.warning(message)

        try:
            if not await self.resource_limiter.acquire_connection():
                logger.warning("接続制限に達しました")
                return None

            async with self._download_semaphore:
                if not await self._check_resources():
                    logger.error("リソース制限に達しました")
                    return None

                session = await self._get_session()
                start_time = time.time()
                
                async with session.get(url, params=params) as response:
                    response.raise_for_status()
                    content = await response.text()
                    
                    # 帯域幅チェック
                    if not await self.resource_limiter.check_and_update_bandwidth(len(content.encode())):
                        logger.warning("帯域幅制限に達しました")
                        return None
                    
                    self._downloaded_urls.add(url)
                    return BeautifulSoup(content, 'html.parser')

        except aiohttp.ClientError as e:
            logger.error(f"ページ取得エラー ({url}): {str(e)}")
            return None
        except Exception as e:
            logger.error(f"予期せぬエラー ({url}): {str(e)}")
            return None
        finally:
            await self.resource_limiter.release_connection()

    async def download_resource(self, url: str) -> DownloadResult:
        """リソースを非同期でダウンロード"""
        if url in self._downloaded_urls:
            return DownloadResult(url=url, success=False, error="重複URL")

        valid, message = self._is_valid_url(url)
        if not valid:
            return DownloadResult(url=url, success=False, error=message)
        elif message:
            logger.warning(message)

        try:
            if not await self.resource_limiter.acquire_connection():
                return DownloadResult(url=url, success=False, error="接続制限")

            async with self._download_semaphore:
                if not await self._check_resources():
                    return DownloadResult(url=url, success=False, error="リソース制限")

                session = await self._get_session()
                start_time = time.time()
                
                async with session.get(url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get('content-type', '').lower()
                    
                    # Content-Typeの検証
                    if not self._is_allowed_content_type(content_type):
                        return DownloadResult(
                            url=url,
                            success=False,
                            error=f"不正なContent-Type: {content_type}"
                        )
                    
                    # サイズ制限のチェック
                    content_length = response.headers.get('content-length')
                    if content_length and int(content_length) > self.settings.FILE_CONFIG['max_size']:
                        return DownloadResult(
                            url=url,
                            success=False,
                            error="ファイルサイズ超過"
                        )
                    
                    content = await response.read()
                    download_time = time.time() - start_time
                    
                    # 帯域幅チェック
                    if not await self.resource_limiter.check_and_update_bandwidth(len(content)):
                        return DownloadResult(url=url, success=False, error="帯域幅制限")
                    
                    self._downloaded_urls.add(url)
                    return DownloadResult(
                        url=url,
                        success=True,
                        content=content,
                        content_type=content_type,
                        size=len(content),
                        download_time=download_time
                    )

        except aiohttp.ClientError as e:
            return DownloadResult(url=url, success=False, error=f"ダウンロードエラー: {str(e)}")
        except Exception as e:
            return DownloadResult(url=url, success=False, error=f"予期せぬエラー: {str(e)}")
        finally:
            await self.resource_limiter.release_connection()

    async def get_text_content(self, url: str) -> Optional[str]:
        """テキストコンテンツを非同期で取得"""
        result = await self.download_resource(url)
        if result.success and isinstance(result.content, bytes):
            try:
                return result.content.decode('utf-8')
            except UnicodeDecodeError:
                logger.error(f"テキストデコードエラー: {url}")
        return None

    def _is_allowed_content_type(self, content_type: str) -> bool:
        """Content-Typeが許可されているかチェック"""
        allowed_types = [
            'text/',
            'image/',
            'video/',
            'application/javascript',
            'application/x-javascript',
            'application/json',
            'application/xml',
            'application/css'
        ]
        return any(allowed_type in content_type for allowed_type in allowed_types)

    async def close(self):
        """セッションをクローズ"""
        if self._session and not self._session.closed:
            await self._session.close()

    def clear_cache(self):
        """ダウンロードキャッシュをクリア"""
        self._downloaded_urls.clear()

    @staticmethod
    def get_absolute_url(base_url: str, relative_url: str) -> str:
        """相対URLを絶対URLに変換"""
        return urljoin(base_url, relative_url)

    @staticmethod
    def guess_extension(url: str, content_type: Optional[str] = None) -> str:
        """URLまたはContent-Typeから拡張子を推測"""
        path = urlparse(url).path
        ext = os.path.splitext(path)[1].lower()
        if ext:
            return ext
            
        if content_type:
            ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
            if ext:
                return ext
                
        return '.bin'
