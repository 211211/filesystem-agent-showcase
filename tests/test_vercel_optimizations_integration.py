"""Integration tests for Vercel-style optimizations.

Tests complex queries across folders to verify:
1. Head-First Pattern (cat defaults to head)
2. Output Truncation (long outputs are truncated)
3. Smart Cat Tool (multiple reading modes)
4. Lazy Tool Loading (contextual tool selection)

These tests cover real business scenarios with the data/ folder structure.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.tools.bash_tools import (
    build_command,
    build_cat_command,
    build_smart_cat_command,
    BASH_TOOLS,
)
from app.agent.tools.tool_selector import ToolSelector
from app.agent.output_processor import OutputProcessor, truncate_output
from app.sandbox.executor import SandboxExecutor, ALLOWED_COMMANDS


# =============================================================================
# Test Data Paths
# =============================================================================

DATA_ROOT = Path(__file__).parent.parent / "data"
BENCHMARK_DIR = DATA_ROOT / "benchmark"
ARXIV_100_DIR = BENCHMARK_DIR / "arxiv-100-papers"
KNOWLEDGE_BASE_DIR = DATA_ROOT / "knowledge-base"
PROJECTS_DIR = DATA_ROOT / "projects"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sandbox_executor():
    """Create a sandbox executor with data root."""
    return SandboxExecutor(
        root_path=DATA_ROOT,
        timeout=30,
        max_file_size=10 * 1024 * 1024,
        max_output_size=1 * 1024 * 1024,
    )


@pytest.fixture
def output_processor():
    """Create an output processor with default settings."""
    return OutputProcessor(max_lines=50, max_chars=10000)


# =============================================================================
# Test Head-First Pattern
# =============================================================================

class TestHeadFirstPatternIntegration:
    """Test head-first pattern with real file operations."""

    def test_cat_command_defaults_to_head(self):
        """cat without parameters should use head -n 100."""
        cmd = build_cat_command(path="benchmark/arxiv-100-papers/metadata.jsonl")
        assert cmd[0] == "head"
        assert "-n" in cmd
        assert "100" in cmd

    def test_cat_full_uses_actual_cat(self):
        """cat with full=True should use actual cat."""
        cmd = build_cat_command(
            path="benchmark/arxiv-100-papers/metadata.jsonl",
            full=True
        )
        assert cmd[0] == "cat"

    def test_cat_custom_lines(self):
        """cat with custom lines should respect the value."""
        cmd = build_cat_command(path="example.txt", lines=50)
        assert cmd == ["head", "-n", "50", "example.txt"]

    @pytest.mark.asyncio
    async def test_cat_execution_with_sandbox(self, sandbox_executor):
        """Execute cat command through sandbox - should use head."""
        if not (DATA_ROOT / "example.txt").exists():
            pytest.skip("example.txt not found")

        cmd = build_command("cat", {"path": "example.txt"})
        result = await sandbox_executor.execute(cmd)

        assert result.success
        # Should have executed successfully with head

    @pytest.mark.asyncio
    async def test_head_first_limits_output(self, sandbox_executor):
        """Head-first pattern should limit output for large files."""
        if not (ARXIV_100_DIR / "metadata.jsonl").exists():
            pytest.skip("metadata.jsonl not found")

        # Default cat (head -n 100)
        cmd = build_command("cat", {"path": "benchmark/arxiv-100-papers/metadata.jsonl"})
        result = await sandbox_executor.execute(cmd)

        assert result.success
        lines = result.stdout.strip().split('\n')
        # Should be limited to 100 lines or less
        assert len(lines) <= 100


# =============================================================================
# Test Output Truncation
# =============================================================================

class TestOutputTruncationIntegration:
    """Test output truncation with various output sizes."""

    def test_short_output_not_truncated(self, output_processor):
        """Short outputs should pass through unchanged."""
        short_output = "line1\nline2\nline3"
        result = output_processor.truncate(short_output)

        assert not result.was_truncated
        assert result.content == short_output

    def test_long_output_truncated(self, output_processor):
        """Long outputs should be truncated with metadata."""
        long_output = "\n".join([f"line{i}" for i in range(200)])
        result = output_processor.truncate(long_output)

        assert result.was_truncated
        assert result.original_lines == 200
        assert "[OUTPUT TRUNCATED" in result.content
        assert "50/200 lines" in result.content

    def test_truncation_indicates_omitted(self, output_processor):
        """Truncated output should indicate content was omitted."""
        long_output = "\n".join([f"data{i}" for i in range(100)])
        result = output_processor.truncate(long_output)

        # Note: We don't suggest tools anymore to avoid retry loops
        assert "omitted for brevity" in result.content

    @pytest.mark.asyncio
    async def test_truncation_with_real_command(self, sandbox_executor, output_processor):
        """Test truncation with real grep output."""
        if not ARXIV_100_DIR.exists():
            pytest.skip("arxiv-100-papers not found")

        # Grep for common pattern that will return many results
        cmd = build_command("grep", {
            "pattern": "cs.AI",
            "path": "benchmark/arxiv-100-papers/metadata.jsonl"
        })
        result = await sandbox_executor.execute(cmd)

        if result.success and result.stdout:
            truncated = output_processor.truncate(result.stdout)
            # If output is long enough, it should be truncated
            if truncated.original_lines > 50:
                assert truncated.was_truncated

    def test_truncation_preserves_first_lines(self, output_processor):
        """Truncation should preserve the first lines intact."""
        lines = [f"important_line_{i}" for i in range(100)]
        long_output = "\n".join(lines)
        result = output_processor.truncate(long_output)

        # First lines should be in the content
        assert "important_line_0" in result.content
        assert "important_line_49" in result.content
        # Line 50+ should not be (truncated at 50)
        assert "important_line_50" not in result.content


# =============================================================================
# Test Smart Cat Tool
# =============================================================================

class TestSmartCatToolIntegration:
    """Test smart_cat tool with various modes."""

    def test_smart_cat_head_mode(self):
        """Head mode should use head command."""
        cmd = build_smart_cat_command(
            path="benchmark/report.md",
            mode="head",
            lines=20
        )
        assert cmd == ["head", "-n", "20", "benchmark/report.md"]

    def test_smart_cat_tail_mode(self):
        """Tail mode should use tail command."""
        cmd = build_smart_cat_command(
            path="benchmark/report.md",
            mode="tail",
            lines=10
        )
        assert cmd == ["tail", "-n", "10", "benchmark/report.md"]

    def test_smart_cat_range_mode(self):
        """Range mode should use sed command."""
        cmd = build_smart_cat_command(
            path="benchmark/report.md",
            mode="range",
            start_line=10,
            end_line=20
        )
        assert cmd == ["sed", "-n", "10,20p", "benchmark/report.md"]

    def test_smart_cat_full_mode(self):
        """Full mode should use cat command."""
        cmd = build_smart_cat_command(
            path="example.txt",
            mode="full"
        )
        assert cmd == ["cat", "example.txt"]

    def test_smart_cat_in_bash_tools(self):
        """smart_cat should be in BASH_TOOLS."""
        tool_names = [t["function"]["name"] for t in BASH_TOOLS]
        assert "smart_cat" in tool_names

    def test_sed_in_allowed_commands(self):
        """sed should be allowed for range mode."""
        assert "sed" in ALLOWED_COMMANDS

    @pytest.mark.asyncio
    async def test_smart_cat_execution_modes(self, sandbox_executor):
        """Test smart_cat execution with different modes."""
        if not (DATA_ROOT / "example.txt").exists():
            pytest.skip("example.txt not found")

        # Test head mode
        cmd = build_smart_cat_command(path="example.txt", mode="head", lines=5)
        result = await sandbox_executor.execute(cmd)
        assert result.success

        # Test tail mode
        cmd = build_smart_cat_command(path="example.txt", mode="tail", lines=5)
        result = await sandbox_executor.execute(cmd)
        assert result.success


# =============================================================================
# Test Lazy Tool Loading
# =============================================================================

class TestLazyToolLoadingIntegration:
    """Test lazy tool loading with various user intents."""

    def test_search_intent_selects_search_tools(self):
        """Search queries should select find/grep/ls tools."""
        tools = ToolSelector.select_tools(
            "find all Python files in the benchmark folder",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        assert "find" in tool_names
        assert "grep" in tool_names or "ls" in tool_names

    def test_read_intent_selects_read_tools(self):
        """Read queries should select cat/head/tail tools."""
        tools = ToolSelector.select_tools(
            "show me the content of metadata.jsonl",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        assert "head" in tool_names
        # cat or smart_cat should be present
        has_read_tool = "cat" in tool_names or "smart_cat" in tool_names
        assert has_read_tool

    def test_analyze_intent_selects_analyze_tools(self):
        """Analysis queries should select wc/grep tools."""
        tools = ToolSelector.select_tools(
            "count the number of lines in report.md",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        assert "wc" in tool_names

    def test_combined_intents(self):
        """Combined queries should select multiple tool groups."""
        tools = ToolSelector.select_tools(
            "find all JSON files and show their content",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        # Should have both search and read tools
        assert "find" in tool_names
        has_read_tool = "head" in tool_names or "cat" in tool_names
        assert has_read_tool

    def test_tool_count_reduction(self):
        """Lazy loading should reduce tool count."""
        total = len(BASH_TOOLS)

        # Specific intent should select fewer tools
        selected, _ = ToolSelector.get_tool_count_reduction(
            "find Python files"
        )
        assert selected < total

    def test_previous_tools_included(self):
        """Previously used tools should be included for continuity."""
        tools = ToolSelector.select_tools(
            "find files",
            previous_tools={"cat", "wc"},
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        # Previous tools should be included
        assert "cat" in tool_names
        assert "wc" in tool_names


# =============================================================================
# Complex Cross-Folder Query Tests
# =============================================================================

class TestComplexCrossFolderQueries:
    """Test complex queries that span multiple folders."""

    @pytest.mark.asyncio
    async def test_find_across_folders(self, sandbox_executor):
        """Test finding files across multiple folders."""
        cmd = build_command("find", {
            "path": ".",
            "name_pattern": "*.json"
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success
        # Should find JSON files across different folders

    @pytest.mark.asyncio
    async def test_grep_across_benchmark_folder(self, sandbox_executor):
        """Test grep across the benchmark folder structure."""
        if not BENCHMARK_DIR.exists():
            pytest.skip("benchmark folder not found")

        cmd = build_command("grep", {
            "pattern": "LLM",
            "path": "benchmark",
            "recursive": True
        })
        result = await sandbox_executor.execute(cmd)

        # Should find LLM references in arxiv papers metadata
        if result.success:
            assert "LLM" in result.stdout or result.stdout == ""

    @pytest.mark.asyncio
    async def test_list_nested_directories(self, sandbox_executor):
        """Test listing nested directory structure."""
        cmd = build_command("ls", {
            "path": "benchmark",
            "all": False,
            "long": False
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success
        assert "arxiv" in result.stdout.lower() or len(result.stdout) > 0

    @pytest.mark.asyncio
    async def test_tree_with_depth_limit(self, sandbox_executor):
        """Test tree command with depth limit."""
        cmd = build_command("tree", {
            "path": ".",
            "max_depth": 2
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success

    @pytest.mark.asyncio
    async def test_wc_on_large_file(self, sandbox_executor):
        """Test word count on large file."""
        if not (ARXIV_100_DIR / "metadata.jsonl").exists():
            pytest.skip("metadata.jsonl not found")

        cmd = build_command("wc", {
            "path": "benchmark/arxiv-100-papers/metadata.jsonl",
            "lines": True
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success
        # Should have line count


# =============================================================================
# End-to-End Optimization Pipeline Tests
# =============================================================================

class TestOptimizationPipeline:
    """Test the complete optimization pipeline."""

    def test_optimization_flow_search_then_read(self):
        """Test typical flow: search -> read with optimizations."""
        # Step 1: User wants to find files
        search_tools = ToolSelector.select_tools(
            "find all JSON files in benchmark",
            include_all_on_unknown=False
        )
        search_tool_names = {t["function"]["name"] for t in search_tools}
        assert "find" in search_tool_names

        # Step 2: After finding, user wants to read
        read_tools = ToolSelector.select_tools(
            "show me the content of metadata.jsonl",
            previous_tools=search_tool_names,  # Include previous
            include_all_on_unknown=False
        )
        read_tool_names = {t["function"]["name"] for t in read_tools}

        # Should have read tools + previous search tools
        assert "head" in read_tool_names
        assert "find" in read_tool_names  # From previous

    def test_cat_with_truncation_pipeline(self, output_processor):
        """Test cat -> truncation pipeline."""
        # Simulate large cat output
        large_content = "\n".join([f'{{"id": {i}, "data": "value"}}' for i in range(200)])

        # Head-first pattern would limit this, but if full content:
        result = output_processor.truncate(large_content)

        assert result.was_truncated
        assert "[OUTPUT TRUNCATED" in result.content
        assert "omitted for brevity" in result.content

    def test_smart_cat_for_different_scenarios(self):
        """Test smart_cat selection for different scenarios."""
        # Scenario 1: View beginning of log file
        cmd1 = build_smart_cat_command(
            path="app.log",
            mode="head",
            lines=50
        )
        assert cmd1[0] == "head"

        # Scenario 2: View recent log entries
        cmd2 = build_smart_cat_command(
            path="app.log",
            mode="tail",
            lines=20
        )
        assert cmd2[0] == "tail"

        # Scenario 3: View specific function at known line
        cmd3 = build_smart_cat_command(
            path="main.py",
            mode="range",
            start_line=100,
            end_line=150
        )
        assert cmd3[0] == "sed"
        assert "100,150p" in cmd3[2]

    def test_token_savings_estimation(self):
        """Estimate token savings from optimizations."""
        # Before optimization: 8 tools * ~500 tokens each = ~4000 tokens
        total_tools = len(BASH_TOOLS)

        # After optimization with specific intent
        selected, _ = ToolSelector.get_tool_count_reduction(
            "find Python files"
        )

        # Calculate reduction percentage
        reduction_percent = ((total_tools - selected) / total_tools) * 100

        # Should have meaningful reduction
        assert reduction_percent > 0


# =============================================================================
# Vietnamese Language Support Tests
# =============================================================================

class TestMultiLanguageSupport:
    """Test multi-language support (English only for now)."""

    def test_english_search_keywords(self):
        """Test English search keywords."""
        tools = ToolSelector.select_tools(
            "find all Python files",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        assert "find" in tool_names

    def test_english_read_keywords(self):
        """Test English read keywords."""
        tools = ToolSelector.select_tools(
            "show content of config file",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        assert "head" in tool_names or "cat" in tool_names

    def test_english_analyze_keywords(self):
        """Test English analyze keywords."""
        tools = ToolSelector.select_tools(
            "count lines in the file",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        assert "wc" in tool_names

    def test_complex_english_query(self):
        """Test complex English query with multiple intents."""
        tools = ToolSelector.select_tools(
            "find config.py and show its content",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        assert "find" in tool_names
        assert "head" in tool_names or "cat" in tool_names



# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCasesAndErrors:
    """Test edge cases and error handling."""

    def test_empty_message_handling(self):
        """Empty message should return all tools or essentials."""
        tools = ToolSelector.select_tools("", include_all_on_unknown=True)
        assert len(tools) == len(BASH_TOOLS)

        tools = ToolSelector.select_tools("", include_all_on_unknown=False)
        tool_names = {t["function"]["name"] for t in tools}
        assert "ls" in tool_names  # Essential tool

    def test_special_characters_in_query(self):
        """Query with special characters should be handled."""
        tools = ToolSelector.select_tools(
            "find files with pattern *.py",
            include_all_on_unknown=False
        )
        # Should not crash and should detect search intent
        tool_names = {t["function"]["name"] for t in tools}
        assert "find" in tool_names

    def test_very_long_query(self):
        """Very long query should be handled."""
        long_query = "find " * 100 + "files"
        tools = ToolSelector.select_tools(long_query, include_all_on_unknown=False)

        # Should detect search intent despite length
        tool_names = {t["function"]["name"] for t in tools}
        assert "find" in tool_names

    def test_truncation_empty_output(self, output_processor):
        """Empty output should be handled."""
        result = output_processor.truncate("")

        assert not result.was_truncated
        assert result.content == ""

    def test_truncation_exact_limit(self, output_processor):
        """Output at exact limit should not be truncated."""
        lines = [f"line{i}" for i in range(50)]  # Exactly max_lines
        output = "\n".join(lines)
        result = output_processor.truncate(output)

        assert not result.was_truncated

    @pytest.mark.asyncio
    async def test_sandbox_path_traversal_blocked(self, sandbox_executor):
        """Path traversal attempts should be blocked."""
        cmd = build_command("cat", {"path": "../../../etc/passwd"})
        result = await sandbox_executor.execute(cmd)

        # Should fail due to path traversal protection
        assert not result.success or "etc/passwd" not in result.stdout


# =============================================================================
# Performance Characteristics Tests
# =============================================================================

class TestPerformanceCharacteristics:
    """Test performance characteristics of optimizations."""

    def test_tool_selection_is_fast(self):
        """Tool selection should be fast (no I/O)."""
        import time

        start = time.time()
        for _ in range(1000):
            ToolSelector.select_tools("find Python files")
        elapsed = time.time() - start

        # Should complete 1000 iterations in under 1 second
        assert elapsed < 1.0

    def test_truncation_is_fast(self, output_processor):
        """Truncation should be fast even for large outputs."""
        import time

        large_output = "\n".join([f"line{i}" for i in range(10000)])

        start = time.time()
        for _ in range(100):
            output_processor.truncate(large_output)
        elapsed = time.time() - start

        # Should complete 100 iterations in under 1 second
        assert elapsed < 1.0

    def test_command_building_is_fast(self):
        """Command building should be fast."""
        import time

        start = time.time()
        for _ in range(1000):
            build_command("cat", {"path": "test.txt"})
            build_command("grep", {"pattern": "test", "path": "."})
            build_command("find", {"path": ".", "name_pattern": "*.py"})
        elapsed = time.time() - start

        # Should complete 3000 command builds in under 1 second
        assert elapsed < 1.0
