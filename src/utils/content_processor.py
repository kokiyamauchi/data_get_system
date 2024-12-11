#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import chardet
import mimetypes
import os
from typing import Dict, Optional, Union, Tuple, List
import logging
from datetime import datetime
import json
import yaml
from pathlib import Path
import re
from bs4 import BeautifulSoup
import cssutils
import esprima
import hashlib

from config.settings import Settings

logger = logging.getLogger(__name__)

class ContentProcessor:
    """コンテンツ処理を行うユーティリティクラス"""

    def __init__(self):
        self.settings = Settings()
        cssutils.log.setLevel(logging.ERROR)  # CSSパース時の警告を抑制
        self._setup_mimetypes()

    def _setup_mimetypes(self):
        """mimetypesの初期設定"""
        mimetypes.init()
        # 追加のMIMEタイプを登録
        additional_types = {
            '.js': 'application/javascript',
            '.jsx': 'application/javascript',
            '.ts': 'application/typescript',
            '.tsx': 'application/typescript',
            '.md': 'text/markdown',
            '.yaml': 'application/x-yaml',
            '.yml': 'application/x-yaml',
            '.svg': 'image/svg+xml',
            '.webp': 'image/webp',
            '.woff': 'font/woff',
            '.woff2': 'font/woff2',
            '.ttf': 'font/ttf',
            '.eot': 'application/vnd.ms-fontobject'
        }
        for ext, type_ in additional_types.items():
            mimetypes.add_type(type_, ext)

    def detect_encoding(self, content: bytes) -> str:
        """
        コンテンツのエンコーディングを検出
        
        Args:
            content: バイト列のコンテンツ
            
        Returns:
            str: 検出されたエンコーディング
        """
        try:
            result = chardet.detect(content)
            encoding = result['encoding']
            confidence = result['confidence']
            
            if confidence < 0.7:  # 信頼度が低い場合
                logger.warning(f"エンコーディング検出の信頼度が低い: {confidence}")
                return self.settings.COMPATIBILITY['encoding']['output']['fallback']
                
            return encoding or self.settings.COMPATIBILITY['encoding']['output']['default']
            
        except Exception as e:
            logger.error(f"エンコーディング検出エラー: {str(e)}")
            return self.settings.COMPATIBILITY['encoding']['output']['default']

    def convert_encoding(self, content: bytes, target_encoding: str = 'utf-8') -> Tuple[str, str]:
        """
        コンテンツのエンコーディングを変換
        
        Args:
            content: 変換対象のコンテンツ
            target_encoding: 変換先のエンコーディング
            
        Returns:
            Tuple[str, str]: (変換後のコンテンツ, 元のエンコーディング)
        """
        try:
            source_encoding = self.detect_encoding(content)
            if source_encoding.lower() == target_encoding.lower():
                return content.decode(source_encoding), source_encoding
                
            # デコード→エンコード
            decoded = content.decode(source_encoding)
            return decoded.encode(target_encoding).decode(target_encoding), source_encoding
            
        except Exception as e:
            logger.error(f"エンコーディング変換エラー: {str(e)}")
            return content.decode('utf-8', errors='replace'), 'unknown'

    def _is_binary(self, content: bytes) -> bool:
        """バイナリコンテンツかどうかを判定"""
        # テキストファイルでよく使用される文字のパターン
        text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7f})
        return bool(content.translate(None, text_chars))

    def _detect_content_type_from_content(self, content: bytes) -> str:
        """コンテンツの内容からタイプを推測"""
        # HTMLの検出
        if content.startswith(b'<!DOCTYPE html') or content.startswith(b'<html'):
            return 'text/html'
        
        # CSSの検出
        if b'{' in content and (b'margin' in content or b'padding' in content or b'color' in content):
            return 'text/css'
        
        # JavaScriptの検出
        js_keywords = [b'function', b'var', b'let', b'const', b'class', b'import', b'export']
        if any(keyword in content for keyword in js_keywords):
            return 'application/javascript'
        
        # JSONの検出
        if content.startswith(b'{') and content.endswith(b'}'):
            try:
                json.loads(content)
                return 'application/json'
            except:
                pass
        
        # YAMLの検出
        try:
            yaml.safe_load(content)
            return 'application/x-yaml'
        except:
            pass
        
        # バイナリかテキストかの判定
        return 'application/octet-stream' if self._is_binary(content) else 'text/plain'

    def get_content_type(self, content: Union[str, bytes], filename: Optional[str] = None) -> str:
        """
        コンテンツタイプを判定
        
        Args:
            content: 判定対象のコンテンツ
            filename: ファイル名（オプション）
            
        Returns:
            str: コンテンツタイプ
        """
        try:
            if isinstance(content, str):
                content = content.encode('utf-8')

            # 1. ファイル名からの判定
            if filename:
                mime_type, _ = mimetypes.guess_type(filename)
                if mime_type:
                    return mime_type

            # 2. コンテンツからの判定
            return self._detect_content_type_from_content(content)
            
        except Exception as e:
            logger.error(f"コンテンツタイプ判定エラー: {str(e)}")
            return 'application/octet-stream'

    def extract_metadata(self, content: Union[str, bytes],
                        content_type: Optional[str] = None) -> Dict:
        """
        コンテンツからメタデータを抽出
        
        Args:
            content: メタデータ抽出対象のコンテンツ
            content_type: コンテンツタイプ（オプション）
            
        Returns:
            Dict: 抽出されたメタデータ
        """
        if content_type is None:
            content_type = self.get_content_type(content)
            
        metadata = {
            'content_type': content_type,
            'size': len(content.encode()) if isinstance(content, str) else len(content),
            'hash': hashlib.sha256(
                content.encode() if isinstance(content, str) else content
            ).hexdigest(),
            'extracted_at': datetime.now().isoformat()
        }
        
        try:
            if 'text/html' in content_type:
                metadata.update(self._extract_html_metadata(content))
            elif 'text/css' in content_type:
                metadata.update(self._extract_css_metadata(content))
            elif 'javascript' in content_type:
                metadata.update(self._extract_js_metadata(content))
                
        except Exception as e:
            logger.error(f"メタデータ抽出エラー: {str(e)}")
            
        return metadata

    def _extract_html_metadata(self, content: str) -> Dict:
        """HTMLからメタデータを抽出"""
        soup = BeautifulSoup(content, 'html.parser')
        metadata = {
            'title': soup.title.string if soup.title else None,
            'meta_tags': {},
            'links': [],
            'scripts': [],
            'images': []
        }
        
        # メタタグの解析
        for meta in soup.find_all('meta'):
            name = meta.get('name', meta.get('property'))
            if name:
                metadata['meta_tags'][name] = meta.get('content')
                
        # リンクの収集
        for link in soup.find_all('link'):
            href = link.get('href')
            if href:
                metadata['links'].append({
                    'href': href,
                    'rel': link.get('rel', []),
                    'type': link.get('type')
                })
                
        # スクリプトの収集
        for script in soup.find_all('script'):
            src = script.get('src')
            if src:
                metadata['scripts'].append({
                    'src': src,
                    'type': script.get('type', 'text/javascript')
                })
                
        # 画像の収集
        for img in soup.find_all('img'):
            src = img.get('src')
            if src:
                metadata['images'].append({
                    'src': src,
                    'alt': img.get('alt'),
                    'width': img.get('width'),
                    'height': img.get('height')
                })
                
        return metadata

    def _extract_css_metadata(self, content: str) -> Dict:
        """CSSからメタデータを抽出"""
        stylesheet = cssutils.parseString(content)
        metadata = {
            'rules_count': len(stylesheet.cssRules),
            'selectors': [],
            'imports': [],
            'media_queries': []
        }
        
        for rule in stylesheet.cssRules:
            if rule.type == rule.STYLE_RULE:
                metadata['selectors'].append(rule.selectorText)
            elif rule.type == rule.IMPORT_RULE:
                metadata['imports'].append(rule.href)
            elif rule.type == rule.MEDIA_RULE:
                metadata['media_queries'].append(rule.media.mediaText)
                
        return metadata

    def _extract_js_metadata(self, content: str) -> Dict:
        """JavaScriptからメタデータを抽出"""
        try:
            ast = esprima.parseScript(content)
            metadata = {
                'functions': [],
                'classes': [],
                'imports': [],
                'exports': []
            }
            
            def visit_node(node, metadata):
                if node.type == 'FunctionDeclaration':
                    metadata['functions'].append(node.id.name)
                elif node.type == 'ClassDeclaration':
                    metadata['classes'].append(node.id.name)
                elif node.type == 'ImportDeclaration':
                    metadata['imports'].append(node.source.value)
                elif node.type == 'ExportNamedDeclaration':
                    if node.declaration and node.declaration.id:
                        metadata['exports'].append(node.declaration.id.name)
                
            def traverse(node, metadata):
                visit_node(node, metadata)
                for key, value in node.items():
                    if isinstance(value, dict) and 'type' in value:
                        traverse(value, metadata)
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict) and 'type' in item:
                                traverse(item, metadata)
            
            traverse(ast.toDict(), metadata)
            return metadata
            
        except Exception as e:
            logger.error(f"JavaScript解析エラー: {str(e)}")
            return {}

    def format_content(self, content: str, content_type: str) -> str:
        """
        コンテンツを整形
        
        Args:
            content: 整形対象のコンテンツ
            content_type: コンテンツタイプ
            
        Returns:
            str: 整形されたコンテンツ
        """
        try:
            if 'text/html' in content_type:
                soup = BeautifulSoup(content, 'html.parser')
                return soup.prettify()
            elif 'text/css' in content_type:
                sheet = cssutils.parseString(content)
                return sheet.cssText.decode()
            elif 'javascript' in content_type:
                return content  # JavaScriptは既存のフォーマットを維持
            elif 'json' in content_type:
                return json.dumps(
                    json.loads(content),
                    indent=2,
                    ensure_ascii=False
                )
            elif 'yaml' in content_type or 'yml' in content_type:
                return yaml.dump(
                    yaml.safe_load(content),
                    allow_unicode=True,
                    default_flow_style=False
                )
            else:
                return content
                
        except Exception as e:
            logger.error(f"コンテンツ整形エラー: {str(e)}")
            return content

    def sanitize_content(self, content: str, content_type: str) -> str:
        """
        コンテンツを安全な形式に変換
        
        Args:
            content: サニタイズ対象のコンテンツ
            content_type: コンテンツタイプ
            
        Returns:
            str: サニタイズされたコンテンツ
        """
        try:
            if 'text/html' in content_type:
                soup = BeautifulSoup(content, 'html.parser')
                # スクリプトタグの除去
                for script in soup.find_all('script'):
                    script.decompose()
                # 危険な属性の除去
                for tag in soup.find_all(True):
                    for attr in list(tag.attrs):
                        if attr.startswith('on'):  # イベントハンドラ
                            del tag[attr]
                return str(soup)
            elif 'text/css' in content_type:
                # 危険なCSSプロパティの除去
                sheet = cssutils.parseString(content)
                for rule in sheet.cssRules:
                    if rule.type == rule.STYLE_RULE:
                        for prop in rule.style:
                            if 'expression' in prop.value:
                                rule.style.removeProperty(prop.name)
                return sheet.cssText.decode()
            else:
                return content
                
        except Exception as e:
            logger.error(f"コンテンツサニタイズエラー: {str(e)}")
            return content

# シングルトンインスタンスを作成
content_processor = ContentProcessor()
