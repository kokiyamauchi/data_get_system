import pytest
import logging
import os
from src.app.logger import Logger

@pytest.fixture
def logger():
    """テスト用のロガーインスタンスを作成"""
    return Logger()

def test_logger_singleton(logger):
    """ロガーがシングルトンパターンを実装していることを確認"""
    logger2 = Logger()
    assert logger is logger2

def test_logger_initialization(logger):
    """ロガーが正しく初期化されることを確認"""
    assert isinstance(logger._logger, logging.Logger)
    assert logger._logger.name == 'app'

def test_log_levels(logger, tmp_path):
    """各ログレベルが正しく機能することを確認"""
    # テスト用のファイルハンドラーを設定
    test_log_file = tmp_path / "test.log"
    handler = logging.FileHandler(test_log_file)
    handler.setFormatter(logging.Formatter('%(levelname)s:%(message)s'))
    logger._logger.addHandler(handler)

    # 各レベルのログを出力
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    # ログファイルの内容を確認
    with open(test_log_file) as f:
        logs = f.readlines()
    
    assert any("INFO:Info message" in line for line in logs)
    assert any("WARNING:Warning message" in line for line in logs)
    assert any("ERROR:Error message" in line for line in logs)
    assert any("CRITICAL:Critical message" in line for line in logs)

def test_log_file_creation(logger, tmp_path):
    """ログファイルが正しく作成されることを確認"""
    log_dir = tmp_path / "logs"
    log_file = log_dir / "app.log"
    
    # ログディレクトリを設定
    os.environ["LOG_DIR"] = str(log_dir)
    
    # 新しいロガーインスタンスを作成（ログファイルを作成するため）
    new_logger = Logger()
    new_logger.info("Test message")
    
    assert log_file.exists()
    assert log_file.read_text().__contains__("Test message")

def test_log_rotation(logger, tmp_path):
    """ログローテーションが正しく機能することを確認"""
    log_dir = tmp_path / "logs"
    log_file = log_dir / "app.log"
    
    # ログディレクトリを設定
    os.environ["LOG_DIR"] = str(log_dir)
    
    # 新しいロガーインスタンスを作成
    new_logger = Logger()
    
    # 大きなログメッセージを生成してログローテーションをトリガー
    large_message = "x" * 1024 * 1024  # 1MB
    for _ in range(11):  # maxBytes=10MBを超えるまで書き込み
        new_logger.info(large_message)
    
    # ログファイルとバックアップファイルが存在することを確認
    assert log_file.exists()
    assert any(f.name.startswith("app.log.") for f in log_dir.iterdir())
