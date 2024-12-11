#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import argparse
from typing import Optional, Tuple
from pathlib import Path
from tqdm import tqdm
import asyncio

# Add src directory to Python path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, src_path)

from app.site_saver import SiteSaver
from app.system_saver import SystemSaver
from app.logger import Logger
from config.settings import Settings

class Application:
    def __init__(self):
        self.logger = Logger()
        self.settings = Settings()
        self.site_saver = SiteSaver(self.logger)
        self.system_saver = SystemSaver(self.logger)

    def _validate_url(self, url: str) -> bool:
        """URLの基本的な検証"""
        return url.startswith(('http://', 'https://'))

    def _validate_path(self, path: str) -> bool:
        """パスの検証"""
        try:
            path = Path(path)
            return path.exists()
        except Exception:
            return False

    def _setup_save_directory(self, save_dir: Optional[str]) -> str:
        """保存先ディレクトリのセットアップ"""
        if not save_dir:
            return os.getcwd()

        path = Path(save_dir)
        try:
            path.mkdir(parents=True, exist_ok=True)
            return str(path)
        except Exception as e:
            self.logger.error(f"保存先ディレクトリの作成に失敗: {e}")
            return os.getcwd()

    def get_user_input(self) -> Tuple[str, str, str]:
        """
        ユーザーから保存モードと必要な情報を取得

        Returns:
            Tuple[str, str, str]: (モード, 入力パス, 保存先ディレクトリ)
        """
        print("\n=== サイト・システム情報保存システム ===")
        print("1: サイト情報の保存")
        print("2: システム情報の保存")
        print("q: 終了")

        while True:
            mode = input("\n選択してください (1/2/q): ").strip()
            if mode in ['1', '2', 'q']:
                break
            print("無効な選択です。もう一度お試しください。")

        if mode == 'q':
            sys.exit(0)

        # 入力パスの取得
        while True:
            if mode == '1':
                input_path = input("サイトのURLを入力してください: ").strip()
                if self._validate_url(input_path):
                    break
                print("無効なURLです。http://またはhttps://で始まるURLを入力してください。")
            else:
                input_path = input("保存対象のシステムパスを入力してください: ").strip()
                if self._validate_path(input_path):
                    break
                print("無効なパスです。存在するパスを入力してください。")

        # 保存先ディレクトリの取得
        print("\n保存先ディレクトリの指定:")
        print("1: カレントディレクトリ（デフォルト）")
        print("2: カスタムディレクトリ")
        
        while True:
            save_dir_choice = input("選択してください (1/2): ").strip()
            if save_dir_choice == '1':
                save_dir = os.getcwd()
                break
            elif save_dir_choice == '2':
                save_dir = input("保存先ディレクトリのパスを入力: ").strip()
                save_dir = self._setup_save_directory(save_dir)
                break
            print("無効な選択です。")

        return ('site' if mode == '1' else 'system', input_path, save_dir)

    def parse_args(self, args: list) -> Tuple[str, str, str]:
        """コマンドライン引数のパース"""
        parser = argparse.ArgumentParser(description='サイト・システム情報保存システム')
        parser.add_argument('--mode', choices=['site', 'system'], required=True,
                          help='保存モード (site: サイト情報, system: システム情報)')
        parser.add_argument('--input', required=True,
                          help='入力（サイトURLまたはシステムパス）')
        parser.add_argument('--output', default=os.getcwd(),
                          help='保存先ディレクトリ（省略時はカレントディレクトリ）')
        
        parsed_args = parser.parse_args(args)
        
        # 入力の検証
        if parsed_args.mode == 'site' and not self._validate_url(parsed_args.input):
            self.logger.error("無効なURL")
            sys.exit(1)
        elif parsed_args.mode == 'system' and not self._validate_path(parsed_args.input):
            self.logger.error("無効なシステムパス")
            sys.exit(1)
            
        save_dir = self._setup_save_directory(parsed_args.output)
        return parsed_args.mode, parsed_args.input, save_dir

    async def run_async(self, args: Optional[list] = None) -> int:
        """
        アプリケーションの非同期メインエントリーポイント
        
        Args:
            args: コマンドライン引数（Noneの場合はインタラクティブモード）
            
        Returns:
            int: 終了コード（0: 成功, 1: エラー）
        """
        try:
            self.logger.info("アプリケーションを開始します")

            # モードと入力の取得
            if args is None or len(args) == 0:
                mode, input_path, save_dir = self.get_user_input()
            else:
                mode, input_path, save_dir = self.parse_args(args)

            # 進捗表示の準備
            with tqdm(total=100, desc="処理中") as pbar:
                if mode == 'site':
                    self.logger.info(f"サイト情報の保存を開始: {input_path}")
                    success = await self.site_saver.save(
                        url=input_path,
                        save_dir=save_dir,
                        progress_callback=lambda p: pbar.update(p - pbar.n)
                    )
                else:
                    self.logger.info(f"システム情報の保存を開始: {input_path}")
                    success = await self.system_saver.save(
                        system_path=input_path,
                        save_dir=save_dir,
                        progress_callback=lambda p: pbar.update(p - pbar.n)
                    )

            if success:
                print(f"\n保存が完了しました。保存先: {save_dir}")
                self.logger.info("処理が正常に完了しました")
                return 0
            else:
                print("\n保存中にエラーが発生しました。ログを確認してください。")
                return 1
            
        except KeyboardInterrupt:
            print("\n処理を中断しました")
            self.logger.info("ユーザーによって処理が中断されました")
            return 1
        except Exception as e:
            print(f"\nエラーが発生しました: {str(e)}")
            self.logger.error(f"予期せぬエラーが発生しました: {str(e)}")
            return 1

    def run(self, args: Optional[list] = None) -> int:
        """
        アプリケーションのメインエントリーポイント
        
        Args:
            args: コマンドライン引数（Noneの場合はインタラクティブモード）
            
        Returns:
            int: 終了コード（0: 成功, 1: エラー）
        """
        return asyncio.run(self.run_async(args))

def main():
    """
    アプリケーションのメインエントリーポイント関数
    """
    app = Application()
    exit_code = app.run(sys.argv[1:] if len(sys.argv) > 1 else None)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
