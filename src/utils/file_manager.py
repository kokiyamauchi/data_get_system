#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import tempfile
import logging
import platform
from pathlib import Path
from typing import Optional, Union, BinaryIO, TextIO, List, Dict
import hashlib
from datetime import datetime
import psutil
from contextlib import contextmanager

from config.settings import Settings

logger = logging.getLogger(__name__)

class FileManager:
    """安全なファイル操作を提供するクラス"""

    def __init__(self):
        self.settings = Settings()
        self._temp_files: List[str] = []
        self._open_files: Dict[str, Union[TextIO, BinaryIO]] = {}
        self._process = psutil.Process()
        self._is_windows = platform.system().lower() == 'windows'

    def _check_memory_usage(self) -> bool:
        """メモリ使用量をチェック"""
        memory_info = self._process.memory_info()
        total_memory = memory_info.rss + memory_info.vms
        return total_memory < self.settings.RESOURCE_MANAGEMENT['memory']['heap_size']

    def _check_disk_space(self, required_bytes: int, path: str = None) -> bool:
        """ディスク容量をチェック"""
        if path is None:
            path = self.settings.SAVE_CONFIG['default_dir']
        disk_usage = shutil.disk_usage(path)
        return disk_usage.free > required_bytes

    def _sanitize_filename(self, filename: str) -> str:
        """ファイル名を安全な形式に変換"""
        # 不正な文字を除去
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # ファイル名の長さを制限
        name, ext = os.path.splitext(filename)
        if len(name) > 200:  # 適度な長さに制限
            name = name[:200]
        return name + ext

    def _get_unique_path(self, path: str) -> str:
        """重複しないファイルパスを生成"""
        if not os.path.exists(path):
            return path
            
        directory = os.path.dirname(path)
        name, ext = os.path.splitext(os.path.basename(path))
        counter = 1
        
        while True:
            new_path = os.path.join(directory, f"{name}_{counter}{ext}")
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    @contextmanager
    def _file_lock(self, path: str):
        """クロスプラットフォーム対応のファイルロックを提供するコンテキストマネージャ"""
        lock_path = f"{path}.lock"
        lock_file = None
        
        try:
            lock_file = open(lock_path, 'w')
            
            if self._is_windows:
                # Windowsでのファイルロック処理
                import msvcrt
                file_handle = msvcrt.get_osfhandle(lock_file.fileno())
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    raise IOError("ファイルは他のプロセスによってロックされています")
            else:
                # UNIX系システムでのファイルロック処理
                import fcntl
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise IOError("ファイルは他のプロセスによってロックされています")
            
            yield
            
        finally:
            if lock_file:
                if self._is_windows:
                    try:
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                else:
                    try:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass
                
                lock_file.close()
                try:
                    os.remove(lock_path)
                except OSError:
                    pass

    def validate_path(self, path: str) -> bool:
        """パスの検証"""
        try:
            normalized_path = os.path.abspath(path)
            
            # 制限パスのチェック
            if self.settings.is_path_restricted(normalized_path):
                logger.error(f"制限されたパス: {path}")
                return False
            
            # 親ディレクトリの存在確認
            parent_dir = os.path.dirname(normalized_path)
            if not os.path.exists(parent_dir):
                try:
                    os.makedirs(parent_dir, exist_ok=True)
                except OSError as e:
                    logger.error(f"ディレクトリ作成エラー: {str(e)}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"パス検証エラー: {str(e)}")
            return False

    def safe_write(self, path: str, content: Union[str, bytes],
                  mode: str = 'w', encoding: Optional[str] = 'utf-8') -> bool:
        """安全なファイル書き込み"""
        if not self.validate_path(path):
            return False

        if not self._check_memory_usage():
            logger.error("メモリ使用量が制限を超えています")
            return False

        content_size = len(content.encode()) if isinstance(content, str) else len(content)
        if not self._check_disk_space(content_size, path):
            logger.error("十分なディスク容量がありません")
            return False

        # 一時ファイルを使用して安全に書き込み
        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path))
        self._temp_files.append(temp_path)
        
        try:
            with self._file_lock(path):
                with os.fdopen(temp_fd, mode, encoding=encoding) as f:
                    f.write(content)
                
                # 既存ファイルのバックアップ（存在する場合）
                if os.path.exists(path):
                    backup_path = self._get_backup_path(path)
                    shutil.copy2(path, backup_path)
                
                # 一時ファイルを目的のパスに移動
                shutil.move(temp_path, path)
                self._temp_files.remove(temp_path)
                return True
                
        except Exception as e:
            logger.error(f"ファイル書き込みエラー: {str(e)}")
            return False

    def safe_read(self, path: str, mode: str = 'r',
                 encoding: Optional[str] = 'utf-8') -> Optional[Union[str, bytes]]:
        """安全なファイル読み込み"""
        if not self.validate_path(path):
            return None

        if not os.path.exists(path):
            logger.error(f"ファイルが存在しません: {path}")
            return None

        try:
            with self._file_lock(path):
                with open(path, mode, encoding=encoding) as f:
                    return f.read()
                    
        except Exception as e:
            logger.error(f"ファイル読み込みエラー: {str(e)}")
            return None

    def _get_backup_path(self, original_path: str) -> str:
        """バックアップファイルのパスを生成"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        directory = os.path.dirname(original_path)
        name, ext = os.path.splitext(os.path.basename(original_path))
        return os.path.join(directory, f"{name}_backup_{timestamp}{ext}")

    def create_temp_file(self, prefix: str = 'temp_',
                        suffix: str = '') -> Optional[str]:
        """一時ファイルを作成"""
        try:
            fd, temp_path = tempfile.mkstemp(
                prefix=prefix,
                suffix=suffix,
                dir=self.settings.SAVE_CONFIG['temp_dir']
            )
            os.close(fd)
            self._temp_files.append(temp_path)
            return temp_path
            
        except Exception as e:
            logger.error(f"一時ファイル作成エラー: {str(e)}")
            return None

    def cleanup_temp_files(self):
        """一時ファイルを削除"""
        for temp_path in self._temp_files[:]:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                self._temp_files.remove(temp_path)
            except Exception as e:
                logger.error(f"一時ファイル削除エラー: {str(e)}")

    def get_file_hash(self, path: str) -> Optional[str]:
        """ファイルのハッシュ値を計算"""
        if not os.path.exists(path):
            return None

        try:
            with open(path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"ハッシュ計算エラー: {str(e)}")
            return None

    def __del__(self):
        """デストラクタ: 残っている一時ファイルを削除"""
        self.cleanup_temp_files()

# シングルトンインスタンスを作成
file_manager = FileManager()
