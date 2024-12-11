#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import yaml
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Any, Tuple, TypeVar, Union, Callable
from urllib.parse import urljoin, urlparse
import time
import psutil
from concurrent.futures import ThreadPoolExecutor

from utils.web_scraper import WebScraper
from utils.file_manager import FileManager
from utils.content_processor import ContentProcessor
from config.settings import Settings

# 型変数の定義
T = TypeVar('T')
ResourceDict = Dict[str, List[Dict[str, str]]]
StyleDict = Dict[str, str]

class SiteSaver:
    """サイト情報を保存するためのクラス"""

    def __init__(self, logger):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
        """
        self.logger = logger
        self.settings = Settings()
        self.web_scraper = WebScraper()
        self.file_manager = FileManager()
        self.content_processor = ContentProcessor()
        self._progress = 0
        self._progress_callback = None
        self._process = psutil.Process()
        self._executor = ThreadPoolExecutor(
            max_workers=self.settings.PERFORMANCE['site_saving']['download']['max_concurrent']
        )

    def _update_progress(self, increment: float):
        """進捗を更新"""
        self._progress = min(100, self._progress + increment)
        if self._progress_callback:
            self._progress_callback(self._progress)

    async def _check_resources(self) -> bool:
        """システムリソースをチェック"""
        try:
            # メモリ使用量のチェック
            memory_info = self._process.memory_info()
            if memory_info.rss > self.settings.PERFORMANCE['site_saving']['processing']['max_memory_usage']:
                self.logger.warning("メモリ使用量が制限を超えています")
                return False

            # CPU使用率のチェック
            cpu_percent = self._process.cpu_percent()
            if cpu_percent > self.settings.PERFORMANCE['site_saving']['processing']['max_cpu_usage']:
                self.logger.warning("CPU使用率が制限を超えています")
                return False

            return True

        except Exception as e:
            self.logger.error(f"リソースチェックエラー: {str(e)}")
            return False

    def _create_directory_structure(self, base_dir: str) -> Dict[str, str]:
        """
        必要なディレクトリ構造を作成
        
        Args:
            base_dir: 基準ディレクトリ
            
        Returns:
            Dict[str, str]: 作成したディレクトリのパス
        """
        dirs = {
            'images': os.path.join(base_dir, 'images'),
            'videos': os.path.join(base_dir, 'videos'),
            'styles': os.path.join(base_dir, 'styles'),
            'scripts': os.path.join(base_dir, 'scripts')
        }
        
        for dir_path in dirs.values():
            os.makedirs(dir_path, exist_ok=True)
            
        return dirs

    async def _extract_and_save_resources(
        self,
        soup: Any,
        base_url: str,
        dirs: Dict[str, str]
    ) -> ResourceDict:
        """
        リソースを抽出して保存
        
        Args:
            soup: BeautifulSoupオブジェクト
            base_url: ベースURL
            dirs: 保存先ディレクトリ
            
        Returns:
            Dict: 保存したリソースの情報
        """
        resources: ResourceDict = {
            'images': [],
            'videos': []
        }

        # 画像の抽出と保存
        images = soup.find_all('img')
        image_tasks = []
        for img in images:
            src = img.get('src')
            if src:
                full_url = urljoin(base_url, src)
                image_tasks.append(self._download_and_save_resource(
                    full_url, dirs['images'], 'images'
                ))

        # 動画の抽出と保存
        videos = soup.find_all(['video', 'source'])
        video_tasks = []
        for video in videos:
            src = video.get('src')
            if src:
                full_url = urljoin(base_url, src)
                video_tasks.append(self._download_and_save_resource(
                    full_url, dirs['videos'], 'videos'
                ))

        # 並行ダウンロードの実行
        all_tasks = image_tasks + video_tasks
        results = await asyncio.gather(*all_tasks, return_exceptions=True)

        # 結果の処理
        for result in results:
            if isinstance(result, tuple) and len(result) == 3:
                resource_type, path_info, success = result
                if success:
                    resources[resource_type].append(path_info)
                    self._update_progress(40 / len(all_tasks))  # 40%をリソース保存に割り当て

        return resources

    async def _download_and_save_resource(
        self,
        url: str,
        save_dir: str,
        resource_type: str
    ) -> Tuple[str, Dict[str, str], bool]:
        """リソースをダウンロードして保存"""
        try:
            result = await self.web_scraper.download_resource(url)
            if not result.success:
                self.logger.warning(f"リソースのダウンロード失敗: {url} - {result.error}")
                return resource_type, {}, False

            # コンテンツタイプの検証
            content_type = result.content_type
            if not self._is_valid_resource_type(content_type, resource_type):
                self.logger.warning(f"不正なコンテンツタイプ: {url} - {content_type}")
                return resource_type, {}, False

            # ファイル名の生成と重複チェック
            filename = os.path.basename(urlparse(url).path) or f'resource_{hash(url)}'
            filename = self.content_processor._sanitize_filename(filename)
            local_path = os.path.join(save_dir, filename)
            local_path = self.file_manager._get_unique_path(local_path)

            # ファイルの保存
            if await self._check_resources():
                if self.file_manager.safe_write(local_path, result.content, mode='wb'):
                    return resource_type, {
                        'path': url,
                        'local_path': f"./{resource_type}/{os.path.basename(local_path)}",
                        'content_type': content_type,
                        'size': result.size
                    }, True

            return resource_type, {}, False

        except Exception as e:
            self.logger.error(f"リソース保存エラー: {url} - {str(e)}")
            return resource_type, {}, False

    def _is_valid_resource_type(self, content_type: str, expected_type: str) -> bool:
        """リソースタイプの検証"""
        if expected_type == 'images':
            return content_type.startswith('image/')
        elif expected_type == 'videos':
            return content_type.startswith('video/')
        return False

    async def _extract_styles_and_scripts(
        self,
        soup: Any,
        base_url: str,
        dirs: Dict[str, str]
    ) -> Tuple[List[StyleDict], List[StyleDict]]:
        """
        CSSとJavaScriptを抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            base_url: ベースURL
            dirs: 保存先ディレクトリ
            
        Returns:
            Tuple[List[Dict], List[Dict]]: CSSとJavaScriptの情報
        """
        css_data: List[StyleDict] = []
        js_data: List[StyleDict] = []

        # 外部CSSの抽出
        css_tasks = []
        for link in soup.find_all('link', rel='stylesheet'):
            href = link.get('href')
            if href:
                full_url = urljoin(base_url, href)
                css_tasks.append(self._process_external_resource(
                    full_url, dirs['styles'], 'css'
                ))

        # 外部JavaScriptの抽出
        js_tasks = []
        for script in soup.find_all('script', src=True):
            src = script.get('src')
            if src:
                full_url = urljoin(base_url, src)
                js_tasks.append(self._process_external_resource(
                    full_url, dirs['scripts'], 'javascript'
                ))

        # 並行処理の実行
        css_results = await asyncio.gather(*css_tasks, return_exceptions=True)
        js_results = await asyncio.gather(*js_tasks, return_exceptions=True)

        # CSS結果の処理
        for result in css_results:
            if isinstance(result, dict) and result.get('content'):
                css_data.append(result)
                self._update_progress(20 / len(css_tasks))  # 20%をCSS処理に割り当て

        # JavaScript結果の処理
        for result in js_results:
            if isinstance(result, dict) and result.get('content'):
                js_data.append(result)
                self._update_progress(20 / len(js_tasks))  # 20%をJS処理に割り当て

        # インラインスタイルとスクリプトの処理
        for style in soup.find_all('style'):
            if style.string:
                content = self.content_processor.sanitize_content(
                    style.string, 'text/css'
                )
                css_data.append({
                    'path': 'inline',
                    'content': content
                })

        for script in soup.find_all('script', src=False):
            if script.string:
                content = self.content_processor.sanitize_content(
                    script.string, 'application/javascript'
                )
                js_data.append({
                    'path': 'inline',
                    'content': content
                })

        return css_data, js_data

    async def _process_external_resource(
        self,
        url: str,
        save_dir: str,
        resource_type: str
    ) -> Dict[str, str]:
        """外部リソースの処理"""
        try:
            content = await self.web_scraper.get_text_content(url)
            if content:
                # コンテンツの検証と整形
                content = self.content_processor.sanitize_content(
                    content,
                    f'text/{resource_type}'
                )
                content = self.content_processor.format_content(
                    content,
                    f'text/{resource_type}'
                )

                # メタデータの抽出
                metadata = self.content_processor.extract_metadata(
                    content,
                    f'text/{resource_type}'
                )

                return {
                    'path': url,
                    'content': content,
                    'metadata': metadata
                }

        except Exception as e:
            self.logger.error(f"外部リソース処理エラー: {url} - {str(e)}")
            return {}

    async def save(
        self,
        url: str,
        save_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> bool:
        """
        指定されたURLのサイト情報を保存する
        
        Args:
            url: 保存対象のURL
            save_dir: 保存先ディレクトリ（省略時はデフォルト）
            progress_callback: 進捗コールバック関数
            
        Returns:
            bool: 保存が成功したかどうか
        """
        if not url:
            self.logger.error("URLが指定されていません")
            return False

        self._progress = 0
        self._progress_callback = progress_callback

        try:
            # URLの検証
            allowed, warning = self.settings.is_allowed_protocol(url)
            if not allowed:
                self.logger.error(f"不正なプロトコル: {url}")
                return False
            if warning:
                self.logger.warning(warning)

            # 保存先ディレクトリの設定
            if not save_dir:
                save_dir = self.settings.SAVE_CONFIG['default_dir']
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            site_dir = os.path.join(save_dir, f"site_{timestamp}")
            
            # ディレクトリ構造の作成
            dirs = self._create_directory_structure(site_dir)
            self._update_progress(5)  # 5%完了
            
            # サイトコンテンツの取得
            soup = await self.web_scraper.get_page(url)
            if not soup:
                self.logger.error(f"サイトコンテンツの取得に失敗しました: {url}")
                return False
            self._update_progress(10)  # 15%完了

            # リソースの抽出と保存（40%）
            resources = await self._extract_and_save_resources(soup, url, dirs)
            # この時点で55%完了
            
            # CSSとJavaScriptの抽出（40%）
            css_data, js_data = await self._extract_styles_and_scripts(soup, url, dirs)
            # この時点で95%完了

            # HTMLの処理
            html_content = self.content_processor.sanitize_content(
                str(soup), 'text/html'
            )
            html_content = self.content_processor.format_content(
                html_content, 'text/html'
            )
            
            # YAMLデータの構築
            site_data = {
                'site': {
                    'html': {
                        'main': html_content,
                        'metadata': self.content_processor.extract_metadata(
                            html_content, 'text/html'
                        )
                    },
                    'css': css_data,
                    'javascript': js_data,
                    'images': resources['images'],
                    'videos': resources['videos'],
                    'metadata': {
                        'url': url,
                        'extracted_at': datetime.now().isoformat(),
                        'config': {
                            'max_resource_size': self.settings.FILE_CONFIG['max_size'],
                            'resource_types': self.settings.FILE_CONFIG['allowed_types']
                        }
                    }
                }
            }
            
            # YAMLファイルの保存（5%）
            yaml_path = os.path.join(site_dir, 'site_data.yaml')
            if self.file_manager.safe_write(
                yaml_path,
                yaml.dump(site_data, allow_unicode=True, sort_keys=False),
                encoding='utf-8'
            ):
                self._update_progress(5)  # 100%完了
                self.logger.info(f"サイト情報を保存しました: {yaml_path}")
                return True
            else:
                self.logger.error("YAMLファイルの保存に失敗しました")
                return False

        except Exception as e:
            self.logger.error(f"サイト情報の保存に失敗しました: {str(e)}")
            return False
        finally:
            await self.web_scraper.close()

    def __del__(self):
        """デストラクタ: リソースのクリーンアップ"""
        self._executor.shutdown(wait=True)
