#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import platform
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import fnmatch

class Settings:
    """アプリケーション設定クラス"""
    
    def __init__(self):
        # プロジェクトのルートディレクトリ
        self.BASE_DIR = Path(__file__).resolve().parent.parent
        
        # アプリケーション設定
        self.APP_NAME = "サイト・システム情報保存システム"
        self.VERSION = "1.0.0"
        
        # 環境設定
        self.ENV = os.getenv('APP_ENV', 'development')
        self.DEBUG = self.ENV == 'development'

        # パフォーマンス設定
        self.PERFORMANCE = {
            'site_saving': {
                'download': {
                    'max_concurrent': 5,
                    'timeout_seconds': 30,
                    'retry_attempts': 3,
                    'min_bandwidth': 1024 * 1024  # 1MB/s
                },
                'processing': {
                    'max_memory_usage': 1024 * 1024 * 1024,  # 1GB
                    'max_cpu_usage': 80  # 80%
                }
            },
            'system_saving': {
                'scanning': {
                    'files_per_second': 1000,
                    'max_directory_depth': None  # 無制限
                },
                'processing': {
                    'max_file_size': 10 * 1024 * 1024,  # 10MB
                    'total_files_limit': 1000000,
                    'max_memory_usage': 2 * 1024 * 1024 * 1024  # 2GB
                }
            }
        }

        # リソース管理設定
        self.RESOURCE_MANAGEMENT = {
            'memory': {
                'heap_size': 1024 * 1024 * 1024,  # 1GB
                'stack_size': 100 * 1024 * 1024,  # 100MB
                'gc_strategy': 'aggressive'
            },
            'storage': {
                'temp_space': 5 * 1024 * 1024 * 1024,  # 5GB
                'output_limit': 10 * 1024 * 1024 * 1024,  # 10GB
                'cleanup_policy': 'on_completion'
            },
            'network': {
                'max_bandwidth': 10 * 1024 * 1024,  # 10MB/s
                'connection_limit': 10,
                'timeout_seconds': 30
            }
        }

        # セキュリティ設定
        self.SECURITY = {
            'file_access': {
                'restricted_paths': self._get_restricted_paths(),
                'permissions': {
                    'required': ['read'],
                    'recommended': ['write']
                }
            },
            'web_access': {
                'protocols': ['https', 'http'],
                'warn_on_http': True,
                'restrictions': {
                    'allowed_domains': [],  # 空リストは制限なし
                    'skip_auth_required': True
                }
            },
            'validation': {
                'normalize_paths': True,
                'sanitize_urls': True,
                'validate_filenames': True,
                'control_permissions': True
            }
        }

        # 互換性設定
        self.COMPATIBILITY = {
            'python_version': '>=3.8',
            'os_support': {
                'windows': '10',
                'macos': '10.15',
                'linux': 'Ubuntu 20.04'
            },
            'encoding': {
                'input': ['utf-8', 'shift-jis', 'euc-jp'],
                'output': {
                    'default': 'utf-8',
                    'fallback': 'utf-8-sig'
                }
            }
        }
        
        # ログ設定
        self.LOGGING_CONFIG = {
            'level': 'INFO' if self.ENV == 'production' else 'DEBUG',
            'log_dir': str(self.BASE_DIR / 'logs'),
            'max_bytes': 10 * 1024 * 1024,  # 10MB
            'backup_count': 5,
            'console_output': True,
            'compression': True,
            'formats': ['yaml', 'plain_text']
        }

        # スクレイピング設定
        self.SCRAPING_CONFIG = {
            'timeout': self.PERFORMANCE['site_saving']['download']['timeout_seconds'],
            'user_agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                         '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'),
            'request_delay': 1.0,  # seconds
            'max_retries': self.PERFORMANCE['site_saving']['download']['retry_attempts']
        }
        
        # ファイル設定
        self.FILE_CONFIG = {
            'max_size': self.PERFORMANCE['system_saving']['processing']['max_file_size'],
            'allowed_types': {
                'text': ['.html', '.css', '.js', '.txt', '.json', '.xml', '.yaml', '.yml'],
                'image': ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp'],
                'video': ['.mp4', '.webm', '.ogg']
            }
        }
        
        # 除外設定
        self.EXCLUDED_ITEMS = {
            'directories': [
                '.git',
                '__pycache__',
                'venv',
                'node_modules',
                'dist',
                'build'
            ],
            'files': [
                '.DS_Store',
                'Thumbs.db',
                '*.pyc',
                '*.pyo',
                '*.pyd',
                '.env'
            ]
        }
        
        # 保存設定
        self.SAVE_CONFIG = {
            'default_dir': str(self.BASE_DIR / 'saved_content'),
            'backup_dir': str(self.BASE_DIR / 'backups'),
            'temp_dir': str(self.BASE_DIR / 'temp')
        }

    def _get_restricted_paths(self) -> List[str]:
        """システムに応じた制限パスを取得"""
        system = platform.system().lower()
        restricted = []
        
        if system == 'windows':
            restricted.extend([
                'C:\\Windows',
                'C:\\Program Files',
                'C:\\Program Files (x86)'
            ])
        else:
            restricted.extend([
                '/etc',
                '/var',
                '/usr/bin',
                '/usr/sbin',
                '/usr/local/bin'
            ])
            
        return restricted

    def is_path_restricted(self, path: str) -> bool:
        """パスが制限されているかチェック"""
        path = os.path.abspath(path)
        return any(
            path.startswith(os.path.abspath(restricted))
            for restricted in self.SECURITY['file_access']['restricted_paths']
        )

    def is_allowed_protocol(self, url: str) -> Tuple[bool, bool]:
        """
        URLのプロトコルが許可されているかチェック
        
        Args:
            url: チェック対象のURL
        
        Returns:
            Tuple[bool, bool]: (許可されているか, 警告が必要か)
        """
        protocol = url.split('://')[0].lower()
        if protocol not in self.SECURITY['web_access']['protocols']:
            return False, False
        return True, protocol == 'http' and self.SECURITY['web_access']['warn_on_http']

    def get_environment_config(self) -> Dict:
        """現在の環境に応じた設定を取得"""
        env_config = {
            'development': {
                'logging': 'DEBUG',
                'debug': True,
                'performance_limits': 'relaxed'
            },
            'staging': {
                'logging': 'WARNING',
                'debug': False,
                'performance_limits': 'production'
            },
            'production': {
                'logging': 'ERROR',
                'debug': False,
                'performance_limits': 'strict'
            }
        }
        return env_config.get(self.ENV, env_config['development'])

    def validate_and_normalize_path(self, path: str) -> Optional[str]:
        """パスの検証と正規化"""
        try:
            normalized = os.path.abspath(path)
            if self.is_path_restricted(normalized):
                return None
            return normalized
        except Exception:
            return None

    def should_skip_file(self, filename: str) -> bool:
        """
        ファイルをスキップすべきかどうかを判断
        
        Args:
            filename: ファイル名
            
        Returns:
            bool: スキップすべきかどうか
        """
        # 除外ファイルパターンとのマッチングをチェック
        return any(
            fnmatch.fnmatch(filename, pattern)
            for pattern in self.EXCLUDED_ITEMS['files']
        )

# シングルトンインスタンスを作成
settings = Settings()
