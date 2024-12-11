import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from src.app.site_saver import SiteSaver
from src.app.logger import Logger

@pytest.fixture
def mock_logger():
    """モックロガーを作成"""
    return Mock(spec=Logger)

@pytest.fixture
def site_saver(mock_logger):
    """テスト用のSiteSaverインスタンスを作成"""
    return SiteSaver(mock_logger)

@pytest.fixture
def mock_response():
    """モックのHTTPレスポンスを作成"""
    mock = Mock()
    mock.text = "<html><body><h1>Test Page</h1></body></html>"
    mock.raise_for_status.return_value = None
    return mock

def test_initialization(site_saver, mock_logger):
    """初期化が正しく行われることを確認"""
    assert site_saver.logger == mock_logger
    assert site_saver.web_scraper is not None
    assert site_saver.file_manager is not None

@patch('requests.Session.get')
def test_save_successful(mock_get, site_saver, mock_response, tmp_path):
    """サイト保存が成功するケースをテスト"""
    # モックの設定
    mock_get.return_value = mock_response
    test_url = "https://example.com"
    
    # 保存先ディレクトリを一時ディレクトリに設定
    site_saver.save_dir = str(tmp_path)
    
    # 保存を実行
    result = site_saver.save(test_url)
    
    # 検証
    assert result is True
    assert mock_get.called
    assert mock_get.call_args[0][0] == test_url
    assert len(list(tmp_path.glob("*.html"))) == 1
    assert len(list(tmp_path.glob("*_metadata.json"))) == 1

@patch('requests.Session.get')
def test_save_failed_request(mock_get, site_saver, mock_logger):
    """リクエストが失敗した場合のテスト"""
    # リクエスト失敗を模擬
    mock_get.side_effect = Exception("Connection error")
    
    # 保存を実行
    result = site_saver.save("https://example.com")
    
    # 検証
    assert result is False
    assert mock_logger.error.called

def test_save_invalid_url(site_saver, mock_logger):
    """無効なURLが指定された場合のテスト"""
    result = site_saver.save(None)
    
    assert result is False
    assert mock_logger.error.called

def test_save_multiple_sites(site_saver, tmp_path):
    """複数サイトの保存をテスト"""
    # 保存先ディレクトリを一時ディレクトリに設定
    site_saver.save_dir = str(tmp_path)
    
    # テスト用のURLリスト
    urls = [
        "https://example.com",
        "https://example.org",
        "https://example.net"
    ]
    
    # モックのsave関数を作成
    with patch.object(site_saver, 'save', return_value=True) as mock_save:
        results = site_saver.save_multiple_sites(urls)
        
        # 検証
        assert len(results) == len(urls)
        assert all(result["status"] == "success" for result in results)
        assert mock_save.call_count == len(urls)

def test_get_saved_site_info(site_saver, tmp_path):
    """保存済みサイト情報の取得をテスト"""
    # テスト用のメタデータを作成
    test_metadata = {
        "url": "https://example.com",
        "saved_at": "2023-01-01T00:00:00",
        "size": 1000
    }
    
    metadata_path = tmp_path / "test_metadata.json"
    with open(metadata_path, "w") as f:
        import json
        json.dump(test_metadata, f)
    
    # 情報取得を実行
    result = site_saver.get_saved_site_info(str(tmp_path / "test"))
    
    # 検証
    assert result == test_metadata

def test_get_saved_site_info_not_found(site_saver, tmp_path):
    """存在しないサイト情報の取得をテスト"""
    result = site_saver.get_saved_site_info(str(tmp_path / "nonexistent"))
    assert result is None
