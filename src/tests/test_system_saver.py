import pytest
import json
import os
from unittest.mock import Mock, patch
from datetime import datetime
from src.app.system_saver import SystemSaver
from src.app.logger import Logger

@pytest.fixture
def mock_logger():
    """モックロガーを作成"""
    return Mock(spec=Logger)

@pytest.fixture
def system_saver(mock_logger):
    """テスト用のSystemSaverインスタンスを作成"""
    return SystemSaver(mock_logger)

@pytest.fixture
def mock_system_info():
    """モックのシステム情報を作成"""
    return {
        'timestamp': datetime.now().isoformat(),
        'platform': {
            'system': 'Linux',
            'release': '5.10.0',
            'version': '#1 SMP',
            'machine': 'x86_64',
            'processor': 'x86_64'
        },
        'memory': {
            'total': 16000000000,
            'available': 8000000000,
            'percent': 50.0
        },
        'disk': {
            'partitions': [
                {
                    'device': '/dev/sda1',
                    'mountpoint': '/',
                    'fstype': 'ext4'
                }
            ]
        },
        'cpu': {
            'cores': 4,
            'usage': 25.0
        }
    }

def test_initialization(system_saver, mock_logger):
    """初期化が正しく行われることを確認"""
    assert system_saver.logger == mock_logger
    assert system_saver.file_manager is not None
    assert system_saver.directory_scanner is not None

@patch('psutil.virtual_memory')
@patch('psutil.disk_partitions')
@patch('psutil.cpu_count')
@patch('psutil.cpu_percent')
def test_collect_system_info(mock_cpu_percent, mock_cpu_count, 
                           mock_disk_partitions, mock_virtual_memory,
                           system_saver):
    """システム情報の収集をテスト"""
    # モックの設定
    mock_virtual_memory.return_value = Mock(
        total=16000000000,
        available=8000000000,
        percent=50.0
    )
    mock_disk_partitions.return_value = [
        Mock(
            device='/dev/sda1',
            mountpoint='/',
            fstype='ext4'
        )
    ]
    mock_cpu_count.return_value = 4
    mock_cpu_percent.return_value = 25.0

    # システム情報を収集
    info = system_saver.collect_system_info()

    # 検証
    assert isinstance(info, dict)
    assert 'timestamp' in info
    assert 'platform' in info
    assert 'memory' in info
    assert 'disk' in info
    assert 'cpu' in info
    
    assert info['memory']['total'] == 16000000000
    assert info['memory']['available'] == 8000000000
    assert info['cpu']['cores'] == 4
    assert info['cpu']['usage'] == 25.0

def test_save_successful(system_saver, mock_system_info, tmp_path):
    """システム情報の保存が成功するケースをテスト"""
    # 保存先ディレクトリを一時ディレクトリに設定
    system_saver.output_dir = str(tmp_path)
    
    # collect_system_infoをモック化
    with patch.object(system_saver, 'collect_system_info', 
                     return_value=mock_system_info):
        # 保存を実行
        result = system_saver.save()
        
        # 検証
        assert result is True
        saved_files = list(tmp_path.glob("system_info_*.json"))
        assert len(saved_files) == 1
        
        # 保存された内容を確認
        with open(saved_files[0]) as f:
            saved_data = json.load(f)
        assert saved_data == mock_system_info

def test_save_failed(system_saver, mock_logger):
    """保存が失敗するケースをテスト"""
    # 無効なディレクトリを設定
    system_saver.output_dir = "/invalid/directory"
    
    # 保存を実行
    result = system_saver.save()
    
    # 検証
    assert result is False
    assert mock_logger.error.called

def test_scan_saved_files(system_saver, tmp_path):
    """保存済みファイルのスキャンをテスト"""
    # テストファイルを作成
    system_saver.output_dir = str(tmp_path)
    test_files = [
        "system_info_20230101_000000.json",
        "system_info_20230101_000001.json"
    ]
    for filename in test_files:
        with open(tmp_path / filename, 'w') as f:
            json.dump({}, f)
    
    # スキャンを実行
    files = list(system_saver.scan_saved_files())
    
    # 検証
    assert len(files) == 2
    assert all(str(f).endswith('.json') for f in files)

def test_cleanup_old_files(system_saver, tmp_path):
    """古いファイルのクリーンアップをテスト"""
    # テストファイルを作成
    system_saver.output_dir = str(tmp_path)
    test_files = [
        "system_info_20230101_00000{}.json".format(i)
        for i in range(15)  # max_files=10を超える数のファイルを作成
    ]
    for filename in test_files:
        with open(tmp_path / filename, 'w') as f:
            json.dump({}, f)
    
    # クリーンアップを実行
    result = system_saver.cleanup_old_files(max_files=10)
    
    # 検証
    assert result is True
    remaining_files = list(tmp_path.glob("system_info_*.json"))
    assert len(remaining_files) == 10  # max_filesの数だけ残っていることを確認

def test_cleanup_failed(system_saver, mock_logger):
    """クリーンアップが失敗するケースをテスト"""
    # 無効なディレクトリを設定
    system_saver.output_dir = "/invalid/directory"
    
    # クリーンアップを実行
    result = system_saver.cleanup_old_files()
    
    # 検証
    assert result is False
    assert mock_logger.error.called
