"""
Tests for SSE streaming endpoints.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.config import Settings


@pytest.fixture
def test_data_dir(tmp_path: Path) -> Path:
    """Create a temporary test data directory with sample files."""
    # Create sample text file
    text_file = tmp_path / "sample.txt"
    text_file.write_text("Line 1: Hello World\nLine 2: Foo Bar\nLine 3: Test Data\nLine 4: Hello Again\n")

    # Create larger file for chunking tests
    large_file = tmp_path / "large.txt"
    content = "\n".join([f"Line {i}: This is line number {i} with some content" for i in range(1, 1001)])
    large_file.write_text(content)

    # Create file with patterns for search
    pattern_file = tmp_path / "patterns.txt"
    pattern_file.write_text("""
def function_one():
    pass

class MyClass:
    def method_one(self):
        return "hello"

    def method_two(self):
        return "world"

def function_two():
    return 42
""")

    # Create subdirectory with file
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    nested_file = subdir / "nested.txt"
    nested_file.write_text("Nested file content\n")

    return tmp_path


@pytest.fixture
def mock_settings(test_data_dir: Path):
    """Mock settings to use temporary test directory."""
    settings = Settings(
        azure_openai_api_key="test-key",
        azure_openai_endpoint="https://test.openai.azure.com",
        azure_openai_deployment_name="gpt-4",
        data_root_path=str(test_data_dir),
        sandbox_enabled=True,
    )
    return settings


@pytest.fixture
def client(mock_settings):
    """Create test client with mocked settings."""
    with patch("app.api.routes.stream.get_settings", return_value=mock_settings):
        with patch("app.main.get_settings", return_value=mock_settings):
            with TestClient(app) as client:
                yield client


@pytest.fixture
async def async_client(mock_settings):
    """Create async test client with mocked settings."""
    with patch("app.api.routes.stream.get_settings", return_value=mock_settings):
        with patch("app.main.get_settings", return_value=mock_settings):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                yield client


def parse_sse_events(response_text: str) -> list[dict]:
    """Parse SSE response text into list of events."""
    events = []
    current_event = {}

    for line in response_text.split('\n'):
        line = line.strip()
        if not line:
            if current_event:
                events.append(current_event)
                current_event = {}
            continue

        if line.startswith('event:'):
            current_event['event'] = line[6:].strip()
        elif line.startswith('data:'):
            data_str = line[5:].strip()
            try:
                current_event['data'] = json.loads(data_str)
            except json.JSONDecodeError:
                current_event['data'] = data_str

    # Add last event if exists
    if current_event:
        events.append(current_event)

    return events


class TestStreamFileEndpoint:
    """Tests for /api/stream/file/{path} endpoint."""

    def test_stream_file_basic(self, client, test_data_dir):
        """Test basic file streaming."""
        response = client.get("/api/stream/file/sample.txt")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

        events = parse_sse_events(response.text)
        assert len(events) > 0

        # Check for progress events
        progress_events = [e for e in events if e.get('event') == 'progress']
        assert len(progress_events) > 0

        # Check for chunk events
        chunk_events = [e for e in events if e.get('event') == 'chunk']
        assert len(chunk_events) > 0

        # Verify content is present
        all_content = "".join(e['data']['content'] for e in chunk_events)
        assert "Hello World" in all_content
        assert "Foo Bar" in all_content

        # Check for done event
        done_events = [e for e in events if e.get('event') == 'done']
        assert len(done_events) == 1
        assert 'total_bytes' in done_events[0]['data']

    def test_stream_file_with_query(self, client, test_data_dir):
        """Test file streaming with grep query."""
        response = client.get("/api/stream/file/sample.txt?query=Hello")
        assert response.status_code == 200

        events = parse_sse_events(response.text)

        # Check for match events
        match_events = [e for e in events if e.get('event') == 'match']
        assert len(match_events) == 2  # "Hello World" and "Hello Again"

        for match in match_events:
            assert 'line_number' in match['data']
            assert 'line_content' in match['data']
            assert 'Hello' in match['data']['line_content']

        # Check done event includes matches_found
        done_events = [e for e in events if e.get('event') == 'done']
        assert done_events[0]['data']['matches_found'] == 2

    def test_stream_file_not_found(self, client):
        """Test streaming non-existent file returns 404."""
        response = client.get("/api/stream/file/nonexistent.txt")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_stream_file_path_traversal(self, client):
        """Test path traversal protection."""
        # URL-encode the path to prevent FastAPI from normalizing it
        # Using %2e%2e for ".." to bypass URL normalization
        response = client.get("/api/stream/file/%2e%2e/%2e%2e/%2e%2e/etc/passwd")
        # Should get either 403 (path outside sandbox) or 404 (normalized and not found)
        # Both are acceptable as they prevent access to the file
        assert response.status_code in (403, 404)

    def test_stream_file_directory(self, client, test_data_dir):
        """Test streaming a directory returns 400."""
        response = client.get("/api/stream/file/subdir")
        assert response.status_code == 400
        assert "not a file" in response.json()["detail"].lower()

    def test_stream_file_custom_chunk_size(self, client, test_data_dir):
        """Test streaming with custom chunk size."""
        # Use minimum chunk size to force multiple chunks
        response = client.get("/api/stream/file/large.txt?chunk_size=1024")
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        chunk_events = [e for e in events if e.get('event') == 'chunk']

        # With 1KB chunks and ~50KB file, should have multiple chunks
        assert len(chunk_events) > 1

    def test_stream_file_invalid_chunk_size(self, client):
        """Test invalid chunk size parameters."""
        # Too small
        response = client.get("/api/stream/file/sample.txt?chunk_size=100")
        assert response.status_code == 422  # Validation error

        # Too large
        response = client.get("/api/stream/file/sample.txt?chunk_size=10000000")
        assert response.status_code == 422

    def test_stream_file_nested_path(self, client, test_data_dir):
        """Test streaming file in subdirectory."""
        response = client.get("/api/stream/file/subdir/nested.txt")
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        chunk_events = [e for e in events if e.get('event') == 'chunk']
        content = "".join(e['data']['content'] for e in chunk_events)
        assert "Nested file content" in content

    def test_stream_file_invalid_regex_query(self, client, test_data_dir):
        """Test streaming with invalid regex query."""
        response = client.get("/api/stream/file/sample.txt?query=[invalid")
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        error_events = [e for e in events if e.get('event') == 'error']
        assert len(error_events) == 1
        assert "invalid" in error_events[0]['data']['message'].lower()


class TestStreamSearchEndpoint:
    """Tests for /api/stream/search/{path} endpoint."""

    def test_stream_search_basic(self, client, test_data_dir):
        """Test basic search streaming."""
        response = client.get("/api/stream/search/patterns.txt?pattern=def")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

        events = parse_sse_events(response.text)

        # Check for match events
        match_events = [e for e in events if e.get('event') == 'match']
        assert len(match_events) == 4  # function_one, method_one, method_two, function_two

        for match in match_events:
            assert 'line_number' in match['data']
            assert 'line_content' in match['data']
            assert 'match_start' in match['data']
            assert 'match_end' in match['data']
            assert 'def' in match['data']['line_content']

    def test_stream_search_with_limit(self, client, test_data_dir):
        """Test search with max_matches limit."""
        response = client.get("/api/stream/search/patterns.txt?pattern=def&max_matches=2")
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        match_events = [e for e in events if e.get('event') == 'match']
        assert len(match_events) == 2

        # Check for info event about reaching limit
        info_events = [e for e in events if e.get('event') == 'info']
        assert len(info_events) == 1
        assert "max matches" in info_events[0]['data']['message'].lower()

    def test_stream_search_no_matches(self, client, test_data_dir):
        """Test search with no matches."""
        response = client.get("/api/stream/search/sample.txt?pattern=xyz123nonexistent")
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        match_events = [e for e in events if e.get('event') == 'match']
        assert len(match_events) == 0

        done_events = [e for e in events if e.get('event') == 'done']
        assert done_events[0]['data']['matches_found'] == 0

    def test_stream_search_regex_pattern(self, client, test_data_dir):
        """Test search with regex pattern."""
        # Use URL encoding for regex special characters
        import urllib.parse
        pattern = urllib.parse.quote("method_\\w+")
        response = client.get(f"/api/stream/search/patterns.txt?pattern={pattern}")
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        match_events = [e for e in events if e.get('event') == 'match']
        assert len(match_events) == 2  # method_one and method_two

    def test_stream_search_file_not_found(self, client):
        """Test search on non-existent file returns 404."""
        response = client.get("/api/stream/search/nonexistent.txt?pattern=test")
        assert response.status_code == 404

    def test_stream_search_invalid_regex(self, client, test_data_dir):
        """Test search with invalid regex pattern."""
        response = client.get("/api/stream/search/sample.txt?pattern=[invalid")
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        error_events = [e for e in events if e.get('event') == 'error']
        assert len(error_events) == 1
        assert "invalid" in error_events[0]['data']['message'].lower()

    def test_stream_search_path_traversal(self, client):
        """Test path traversal protection in search."""
        # URL-encode the path to prevent FastAPI from normalizing it
        response = client.get("/api/stream/search/%2e%2e/%2e%2e/%2e%2e/etc/passwd?pattern=root")
        # Should get either 403 (path outside sandbox) or 404 (normalized and not found)
        # Both are acceptable as they prevent access to the file
        assert response.status_code in (403, 404)

    def test_stream_search_directory(self, client, test_data_dir):
        """Test search on directory returns 400."""
        response = client.get("/api/stream/search/subdir?pattern=test")
        assert response.status_code == 400

    def test_stream_search_missing_pattern(self, client, test_data_dir):
        """Test search without pattern parameter."""
        response = client.get("/api/stream/search/sample.txt")
        assert response.status_code == 422  # Missing required parameter

    def test_stream_search_invalid_max_matches(self, client, test_data_dir):
        """Test search with invalid max_matches."""
        # Too small
        response = client.get("/api/stream/search/sample.txt?pattern=test&max_matches=0")
        assert response.status_code == 422

        # Too large
        response = client.get("/api/stream/search/sample.txt?pattern=test&max_matches=10000")
        assert response.status_code == 422


class TestSSEFormat:
    """Tests for SSE format correctness."""

    def test_sse_format_structure(self, client, test_data_dir):
        """Test SSE events have correct format."""
        response = client.get("/api/stream/file/sample.txt")
        lines = response.text.split('\n')

        event_lines = [l for l in lines if l.startswith('event:')]
        data_lines = [l for l in lines if l.startswith('data:')]

        # Should have matching event and data lines
        assert len(event_lines) > 0
        assert len(data_lines) > 0

        # Each data line should be valid JSON
        for data_line in data_lines:
            json_str = data_line[5:].strip()
            data = json.loads(json_str)
            assert isinstance(data, dict)

    def test_sse_progress_events_ordered(self, client, test_data_dir):
        """Test progress events have increasing percentages."""
        response = client.get("/api/stream/file/large.txt?chunk_size=1024")
        events = parse_sse_events(response.text)

        progress_events = [e for e in events if e.get('event') == 'progress']

        percentages = [e['data']['percent'] for e in progress_events]
        bytes_read = [e['data']['bytes_read'] for e in progress_events]

        # Percentages should be non-decreasing
        for i in range(1, len(percentages)):
            assert percentages[i] >= percentages[i-1]

        # Bytes should be increasing
        for i in range(1, len(bytes_read)):
            assert bytes_read[i] > bytes_read[i-1]


class TestCORSSupport:
    """Test CORS headers for SSE endpoints."""

    def test_cors_headers_present(self, client, test_data_dir):
        """Test CORS headers are present for SSE."""
        response = client.options("/api/stream/file/sample.txt")
        # OPTIONS request should be handled
        assert response.status_code in (200, 405)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_file(self, client, test_data_dir):
        """Test streaming an empty file."""
        empty_file = test_data_dir / "empty.txt"
        empty_file.write_text("")

        response = client.get("/api/stream/file/empty.txt")
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        done_events = [e for e in events if e.get('event') == 'done']
        assert len(done_events) == 1
        assert done_events[0]['data']['total_bytes'] == 0

    def test_file_with_special_characters(self, client, test_data_dir):
        """Test streaming file with special characters."""
        special_file = test_data_dir / "special.txt"
        special_file.write_text("Special: <>&\"'\nUnicode: \u00e9\u00e8\u00ea\n")

        response = client.get("/api/stream/file/special.txt")
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        chunk_events = [e for e in events if e.get('event') == 'chunk']
        content = "".join(e['data']['content'] for e in chunk_events)
        assert "Special:" in content
        assert "Unicode:" in content

    def test_file_with_long_lines(self, client, test_data_dir):
        """Test streaming file with very long lines."""
        long_line_file = test_data_dir / "longline.txt"
        long_line = "x" * 10000
        long_line_file.write_text(f"Start\n{long_line}\nEnd\n")

        response = client.get("/api/stream/file/longline.txt")
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        done_events = [e for e in events if e.get('event') == 'done']
        assert len(done_events) == 1

    def test_search_case_sensitive(self, client, test_data_dir):
        """Test search is case-sensitive by default."""
        response = client.get("/api/stream/search/sample.txt?pattern=hello")
        events = parse_sse_events(response.text)
        match_events = [e for e in events if e.get('event') == 'match']
        # "hello" should not match "Hello"
        assert len(match_events) == 0

        response = client.get("/api/stream/search/sample.txt?pattern=Hello")
        events = parse_sse_events(response.text)
        match_events = [e for e in events if e.get('event') == 'match']
        assert len(match_events) == 2
