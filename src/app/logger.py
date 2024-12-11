#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import yaml
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any
from pathlib import Path
import json
from pythonjsonlogger import jsonlogger

from config.settings import Settings

class Logger:
    """アプリケーションのロギングを管理するクラス"""
    
    _instance: Optional['Logger'] = None
    _logger: Optional[logging.Logger] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Loggerの初期化"""
        if self._logger is None:
            self.settings = Settings()
            self._setup_logger()

    def _setup_logger(self):
        """ロガーの初期設定"""
        self._logger = logging.getLogger('app')
        self._logger.setLevel(self.settings.LOGGING_CONFIG['level'])

        # 既存のハンドラをクリア
        if self._logger.handlers:
            self._logger.handlers.clear()

        # ログディレクトリの作成
        log_dir = Path(self.settings.LOGGING_CONFIG['log_dir'])
        log_dir.mkdir(parents=True, exist_ok=True)

        # JSONフォーマッターの作成
        json_formatter = self._create_json_formatter()
        
        # テキストフォーマッターの作成
        text_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # JSONファイルハンドラー
        json_handler = RotatingFileHandler(
            log_dir / 'app.json.log',
            maxBytes=self.settings.LOGGING_CONFIG['max_bytes'],
            backupCount=self.settings.LOGGING_CONFIG['backup_count'],
            encoding='utf-8'
        )
        json_handler.setFormatter(json_formatter)
        self._logger.addHandler(json_handler)

        # YAMLファイルハンドラー
        yaml_handler = YAMLRotatingFileHandler(
            log_dir / 'app.yaml',
            maxBytes=self.settings.LOGGING_CONFIG['max_bytes'],
            backupCount=self.settings.LOGGING_CONFIG['backup_count']
        )
        self._logger.addHandler(yaml_handler)

        # テキストファイルハンドラー
        text_handler = RotatingFileHandler(
            log_dir / 'app.log',
            maxBytes=self.settings.LOGGING_CONFIG['max_bytes'],
            backupCount=self.settings.LOGGING_CONFIG['backup_count'],
            encoding='utf-8'
        )
        text_handler.setFormatter(text_formatter)
        self._logger.addHandler(text_handler)

        # コンソールハンドラー
        if self.settings.LOGGING_CONFIG['console_output']:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(text_formatter)
            self._logger.addHandler(console_handler)

    def _create_json_formatter(self) -> jsonlogger.JsonFormatter:
        """JSONフォーマッターを作成"""
        return jsonlogger.JsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s',
            json_default=str,
            timestamp=True
        )

    def _create_log_entry(self, level: str, message: str, **kwargs) -> Dict[str, Any]:
        """ログエントリを作成"""
        return {
            'log_timestamp': datetime.now().isoformat(),
            'log_level': level,
            'log_source': 'app',
            **kwargs
        }

    def debug(self, message: str, **kwargs):
        """デバッグレベルのログを出力"""
        self._logger.debug(message, extra=self._create_log_entry('DEBUG', message, **kwargs))

    def info(self, message: str, **kwargs):
        """情報レベルのログを出力"""
        self._logger.info(message, extra=self._create_log_entry('INFO', message, **kwargs))

    def warning(self, message: str, **kwargs):
        """警告レベルのログを出力"""
        self._logger.warning(message, extra=self._create_log_entry('WARNING', message, **kwargs))

    def error(self, message: str, **kwargs):
        """エラーレベルのログを出力"""
        self._logger.error(message, extra=self._create_log_entry('ERROR', message, **kwargs))

    def critical(self, message: str, **kwargs):
        """重大エラーレベルのログを出力"""
        self._logger.critical(message, extra=self._create_log_entry('CRITICAL', message, **kwargs))

    def set_level(self, level: str):
        """ログレベルを動的に設定"""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        if level.upper() in level_map:
            self._logger.setLevel(level_map[level.upper()])

class YAMLRotatingFileHandler(RotatingFileHandler):
    """YAML形式でログを出力するRotatingFileHandler"""

    def emit(self, record):
        """ログレコードを出力"""
        try:
            if self.stream is None:
                self.stream = self._open()

            # ログエントリの作成
            log_entry = {
                'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage()
            }

            # 追加の属性を含める
            if hasattr(record, 'extra'):
                for key, value in record.extra.items():
                    if key not in ['timestamp', 'level', 'logger', 'message']:
                        log_entry[key] = value

            # YAMLとして書き出し
            yaml.dump(
                [log_entry],
                self.stream,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False
            )
            self.stream.write('---\n')  # エントリ区切り
            
            self.flush()
            
        except Exception:
            self.handleError(record)

# シングルトンインスタンスを作成
logger = Logger()

def get_logger() -> Logger:
    """ロガーインスタンスを取得"""
    return logger
