#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import yaml
import filetype
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Any, Callable
import time
import psutil
from concurrent.futures import ThreadPoolExecutor
import asyncio

from utils.directory_scanner import DirectoryScanner
from utils.file_manager import FileManager
from utils.content_processor import ContentProcessor
from config.settings import Settings

class SystemSaver:
    """システム情報を収集して保存するクラス"""

    def __init__(self, logger):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
        """
        self.logger = logger
        self.settings = Settings()
        self.file_manager = FileManager()
        self.directory_scanner = DirectoryScanner()
        self.content_processor = ContentProcessor()
        self._progress = 0
        self._progress_callback = None
        self._total_files = 0
        self._processed_files = 0
        self._process = psutil.Process()
        self._executor = ThreadPoolExecutor(max_workers=os.cpu_count())

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
            if memory_info.rss > self.settings.PERFORMANCE['system_saving']['processing']['max_memory_usage']:
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

    async def _process_file(
        self,
        file_path: str,
        max_file_size: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        ファイルを処理
        
        Args:
            file_path: ファイルパス
            max_file_size: 最大ファイルサイズ
            
        Returns:
            Dict: ファイル情報
        """
        try:
            if not await self._check_resources():
                return None

            path = Path(file_path)
            if not path.exists():
                return None

            stats = path.stat()
            
            # ファイルサイズのチェック
            if max_file_size and stats.st_size > max_file_size:
                return {
                    'path': str(path),
                    'format': path.suffix,
                    'size': stats.st_size,
                    'skipped': 'size_limit_exceeded'
                }

            # ファイルの読み取り
            content = self.file_manager.safe_read(file_path)
            if content is None:
                return {
                    'path': str(path),
                    'format': path.suffix,
                    'size': stats.st_size,
                    'skipped': 'read_error'
                }

            # コンテンツタイプの判定
            content_type = self.content_processor.get_content_type(content, path.name)

            # バイナリファイルのチェック
            if self.settings.PERFORMANCE['system_saving']['processing'].get('skip_binary', True) and 'text' not in content_type:
                return {
                    'path': str(path),
                    'format': path.suffix,
                    'size': stats.st_size,
                    'mime_type': content_type,
                    'skipped': 'binary_file'
                }

            # エンコーディングの処理
            if isinstance(content, bytes):
                content, source_encoding = self.content_processor.convert_encoding(
                    content,
                    self.settings.COMPATIBILITY['encoding']['output']['default']
                )

            # コンテンツの整形
            formatted_content = self.content_processor.format_content(content, content_type)

            # メタデータの抽出
            metadata = self.content_processor.extract_metadata(formatted_content, content_type)

            return {
                'path': str(path),
                'format': path.suffix,
                'size': stats.st_size,
                'mime_type': content_type,
                'content': formatted_content,
                'metadata': metadata,
                'modified_at': datetime.fromtimestamp(stats.st_mtime).isoformat()
            }

        except Exception as e:
            self.logger.error(f"ファイル処理エラー ({file_path}): {str(e)}")
            return None

    async def save(
        self,
        system_path: str,
        save_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
        max_file_size: Optional[int] = None
    ) -> bool:
        """
        システム情報を保存
        
        Args:
            system_path: 保存対象のシステムパス
            save_dir: 保存先ディレクトリ（省略時はデフォルト）
            progress_callback: 進捗コールバック関数
            max_file_size: 最大ファイルサイズ（バイト）
            
        Returns:
            bool: 保存が成功したかどうか
        """
        try:
            self._progress = 0
            self._progress_callback = progress_callback

            # パスの検証
            if not self.file_manager.validate_path(system_path):
                self.logger.error(f"無効なシステムパス: {system_path}")
                return False

            # 保存先ディレクトリの設定
            if not save_dir:
                save_dir = self.settings.SAVE_CONFIG['default_dir']

            # 保存先ディレクトリの作成
            os.makedirs(save_dir, exist_ok=True)
            self._update_progress(5)  # 5%完了

            # ディレクトリ構造の取得（20%）
            structure_tree = self.directory_scanner.get_directory_structure(
                system_path,
                max_depth=self.settings.PERFORMANCE['system_saving']['scanning'].get('max_depth')
            )
            self._update_progress(15)  # 20%完了

            # ファイル数のカウントとシステム情報の構築（60%）
            self._total_files = self._count_files(system_path)
            self._processed_files = 0
            
            system_data = {
                'system': {
                    'structure_tree': structure_tree,
                    'contents': [],
                    'metadata': {
                        'base_path': system_path,
                        'saved_at': datetime.now().isoformat(),
                        'config': {
                            'max_file_size': max_file_size or self.settings.PERFORMANCE['system_saving']['processing']['max_file_size'],
                            'skip_binary': self.settings.PERFORMANCE['system_saving']['processing'].get('skip_binary', True),
                            'max_depth': self.settings.PERFORMANCE['system_saving']['scanning'].get('max_depth')
                        },
                        'statistics': {
                            'total_files': self._total_files,
                            'processed_files': 0,
                            'skipped_files': 0,
                            'error_files': 0
                        }
                    }
                }
            }

            # ファイル内容の収集
            stats = system_data['system']['metadata']['statistics']
            tasks = []
            
            async for file_info in self.directory_scanner.scan_directory_async(
                system_path,
                max_depth=self.settings.PERFORMANCE['system_saving']['scanning'].get('max_depth')
            ):
                if file_info:
                    file_path = file_info['path']
                    tasks.append(self._process_file(
                        file_path,
                        max_file_size or self.settings.PERFORMANCE['system_saving']['processing']['max_file_size']
                    ))

                    # バッチ処理（メモリ使用量の制御）
                    if len(tasks) >= 100:
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        for result in results:
                            if isinstance(result, dict):
                                if 'skipped' in result:
                                    stats['skipped_files'] += 1
                                elif 'error' in result:
                                    stats['error_files'] += 1
                                else:
                                    stats['processed_files'] += 1
                                    system_data['system']['contents'].append(result)
                        
                        self._processed_files += len(tasks)
                        if self._total_files > 0:
                            self._update_progress(60 * (self._processed_files / self._total_files))
                        
                        tasks = []

            # 残りのタスクを処理
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, dict):
                        if 'skipped' in result:
                            stats['skipped_files'] += 1
                        elif 'error' in result:
                            stats['error_files'] += 1
                        else:
                            stats['processed_files'] += 1
                            system_data['system']['contents'].append(result)

            # YAMLファイルとして保存（15%）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            yaml_path = os.path.join(save_dir, f"system_{timestamp}.yaml")
            
            if self.file_manager.safe_write(
                yaml_path,
                yaml.dump(system_data, allow_unicode=True, sort_keys=False),
                encoding='utf-8'
            ):
                self._update_progress(15)  # 100%完了
                self.logger.info(f"システム情報を保存しました: {yaml_path}")
                return True
            else:
                self.logger.error("YAMLファイルの保存に失敗しました")
                return False

        except Exception as e:
            self.logger.error(f"システム情報の保存に失敗しました: {str(e)}")
            return False

    def _count_files(self, path: str) -> int:
        """
        処理対象のファイル数をカウント
        
        Args:
            path: 対象ディレクトリのパス
            
        Returns:
            int: ファイル数
        """
        count = 0
        for root, _, files in os.walk(path):
            if any(excluded in root.split(os.sep)
                   for excluded in self.settings.EXCLUDED_ITEMS['directories']):
                continue
            count += len([f for f in files
                         if not self.settings.should_skip_file(f)])
        return count

    def get_saved_system_info(self, yaml_path: str) -> Optional[Dict]:
        """
        保存済みシステム情報を取得
        
        Args:
            yaml_path: YAMLファイルのパス
            
        Returns:
            Dict: システム情報（存在しない場合はNone）
        """
        try:
            content = self.file_manager.safe_read(yaml_path)
            if content:
                return yaml.safe_load(content)
            return None
        except Exception as e:
            self.logger.error(f"保存済みシステム情報の取得に失敗: {str(e)}")
            return None

    def __del__(self):
        """デストラクタ: リソースのクリーンアップ"""
        self._executor.shutdown(wait=True)
