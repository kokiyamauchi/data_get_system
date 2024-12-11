#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import fnmatch
import filetype
from pathlib import Path
from typing import List, Generator, Dict, Optional, Set, Tuple
from datetime import datetime
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
import psutil
import time

from config.settings import Settings

logger = logging.getLogger(__name__)

class DirectoryScanner:
    """ディレクトリをスキャンして特定のファイルやパターンを検索するユーティリティクラス"""

    def __init__(self):
        """DirectoryScannerを初期化"""
        self.settings = Settings()
        self._scanned_files: Set[str] = set()
        self._process = psutil.Process()
        self._start_time = time.time()
        self._files_processed = 0
        self._executor = ThreadPoolExecutor(max_workers=os.cpu_count())

    def _check_performance(self) -> bool:
        """パフォーマンス指標をチェック"""
        # メモリ使用量のチェック
        memory_info = self._process.memory_info()
        if memory_info.rss > self.settings.PERFORMANCE['system_saving']['processing']['max_memory_usage']:
            logger.warning("メモリ使用量が制限を超えています")
            return False

        # 処理速度のチェック
        elapsed_time = time.time() - self._start_time
        if elapsed_time > 0:
            files_per_second = self._files_processed / elapsed_time
            if files_per_second < self.settings.PERFORMANCE['system_saving']['scanning']['files_per_second']:
                logger.warning("処理速度が低下しています")
                return False

        return True

    def _should_skip_path(self, path: str) -> bool:
        """
        パスをスキップすべきかどうかを判定
        
        Args:
            path: チェックするパス
            
        Returns:
            bool: スキップすべき場合はTrue
        """
        path_obj = Path(path)
        
        # 制限パスのチェック
        if self.settings.is_path_restricted(str(path_obj)):
            logger.warning(f"制限パスをスキップ: {path}")
            return True
        
        # 除外ディレクトリのチェック
        if any(excluded in path_obj.parts 
               for excluded in self.settings.EXCLUDED_ITEMS['directories']):
            return True
            
        # 除外ファイルのチェック
        if path_obj.is_file():
            return any(
                fnmatch.fnmatch(path_obj.name, pattern)
                for pattern in self.settings.EXCLUDED_ITEMS['files']
            )
            
        return False

    async def _get_file_info_async(self, file_path: str) -> Optional[Dict]:
        """
        ファイル情報を非同期で取得
        
        Args:
            file_path: ファイルパス
            
        Returns:
            Dict: ファイル情報
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self._executor,
                self._get_file_info_sync,
                file_path
            )
        except Exception as e:
            logger.error(f"ファイル情報取得エラー: {str(e)}")
            return None

    def _get_file_info_sync(self, file_path: str) -> Optional[Dict]:
        """
        ファイル情報を同期的に取得
        
        Args:
            file_path: ファイルパス
            
        Returns:
            Dict: ファイル情報
        """
        try:
            path_obj = Path(file_path)
            if not path_obj.exists():
                return None

            stats = path_obj.stat()
            
            # ファイルサイズのチェック
            if stats.st_size > self.settings.PERFORMANCE['system_saving']['processing']['max_file_size']:
                logger.warning(f"サイズ制限超過: {file_path}")
                return {
                    'path': str(path_obj),
                    'name': path_obj.name,
                    'size': stats.st_size,
                    'skipped': 'size_limit_exceeded'
                }

            kind = filetype.guess(str(path_obj))
            
            file_info = {
                'path': str(path_obj),
                'name': path_obj.name,
                'size': stats.st_size,
                'created_at': datetime.fromtimestamp(stats.st_ctime).isoformat(),
                'modified_at': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                'mime_type': kind.mime if kind else 'text/plain',
                'extension': path_obj.suffix.lower(),
                'permissions': oct(stats.st_mode)[-3:]
            }

            # アクセス権のチェック
            if not os.access(file_path, os.R_OK):
                file_info['skipped'] = 'access_denied'
                logger.warning(f"アクセス権限なし: {file_path}")
                return file_info

            self._files_processed += 1
            return file_info
            
        except Exception as e:
            logger.error(f"ファイル情報取得エラー ({file_path}): {str(e)}")
            return None

    async def scan_directory_async(
        self,
        directory_path: str,
        max_depth: Optional[int] = None,
        pattern: Optional[str] = None,
        max_size: Optional[int] = None,
        include_hidden: bool = False
    ) -> Generator[Dict, None, None]:
        """
        指定されたディレクトリを非同期で再帰的にスキャン
        
        Args:
            directory_path: スキャンするディレクトリのパス
            max_depth: スキャンする最大深度（Noneの場合は無制限）
            pattern: ファイル名のパターン（例: '*.py'）
            max_size: ファイルサイズの上限（バイト）
            include_hidden: 隠しファイルを含めるかどうか
            
        Yields:
            Generator[Dict, None, None]: ファイル情報のジェネレータ
        """
        try:
            base_path = Path(directory_path)
            if not base_path.exists():
                logger.error(f"ディレクトリが存在しません: {directory_path}")
                return

            for root, dirs, files in os.walk(directory_path):
                if not self._check_performance():
                    logger.error("パフォーマンス制限に達しました")
                    break

                # 深度のチェック
                if max_depth is not None:
                    current_depth = len(Path(root).relative_to(base_path).parts)
                    if current_depth > max_depth:
                        dirs.clear()
                        continue

                # 除外ディレクトリの処理
                dirs[:] = [
                    d for d in dirs
                    if not self._should_skip_path(os.path.join(root, d))
                    and (include_hidden or not d.startswith('.'))
                ]

                # ファイルの処理
                tasks = []
                for file in files:
                    file_path = os.path.join(root, file)
                    
                    # 既にスキャン済みのファイルはスキップ
                    if file_path in self._scanned_files:
                        continue
                        
                    # パスのチェック
                    if self._should_skip_path(file_path):
                        continue
                        
                    # 隠しファイルのチェック
                    if not include_hidden and file.startswith('.'):
                        continue
                        
                    # パターンのチェック
                    if pattern and not fnmatch.fnmatch(file, pattern):
                        continue

                    tasks.append(self._get_file_info_async(file_path))

                if tasks:
                    file_infos = await asyncio.gather(*tasks)
                    for file_info in file_infos:
                        if file_info:
                            if max_size and file_info.get('size', 0) > max_size:
                                file_info['skipped'] = 'size_limit_exceeded'
                            self._scanned_files.add(file_info['path'])
                            yield file_info

        except Exception as e:
            logger.error(f"ディレクトリスキャンエラー {directory_path}: {str(e)}")

    def get_directory_structure(
        self,
        directory_path: str,
        max_depth: Optional[int] = None
    ) -> Dict:
        """
        ディレクトリ構造を取得
        
        Args:
            directory_path: 解析するディレクトリのパス
            max_depth: 最大深度（Noneの場合は無制限）
            
        Returns:
            Dict: ディレクトリ構造を表す辞書
        """
        path_obj = Path(directory_path)
        
        if not path_obj.exists():
            logger.error(f"ディレクトリが存在しません: {directory_path}")
            return {'error': 'Directory not found'}
            
        if not path_obj.is_dir():
            logger.error(f"パスがディレクトリではありません: {directory_path}")
            return {'error': 'Path is not a directory'}
            
        def _build_tree(path: Path, current_depth: int = 0) -> Dict:
            if max_depth is not None and current_depth > max_depth:
                return {
                    'name': path.name,
                    'type': 'directory',
                    'truncated': True
                }
                
            try:
                if not self._check_performance():
                    return {
                        'name': path.name,
                        'type': 'directory',
                        'error': 'Performance limit reached'
                    }

                tree = {
                    'name': path.name,
                    'type': 'directory',
                    'children': []
                }
                
                for item in sorted(path.iterdir()):
                    if self._should_skip_path(str(item)):
                        continue
                        
                    if item.is_file():
                        file_info = self._get_file_info_sync(str(item))
                        if file_info:
                            tree['children'].append({
                                'name': item.name,
                                'type': 'file',
                                'size': file_info['size'],
                                'modified_at': file_info['modified_at']
                            })
                    elif item.is_dir():
                        tree['children'].append(
                            _build_tree(item, current_depth + 1)
                        )
                        
                return tree
                
            except Exception as e:
                logger.error(f"ディレクトリツリー構築エラー: {str(e)}")
                return {
                    'name': path.name,
                    'type': 'directory',
                    'error': str(e)
                }
                
        return _build_tree(path_obj)

    def clear_cache(self):
        """スキャンキャッシュをクリア"""
        self._scanned_files.clear()
        self._files_processed = 0
        self._start_time = time.time()

    def __del__(self):
        """デストラクタ: スレッドプールをクリーンアップ"""
        self._executor.shutdown(wait=True)
