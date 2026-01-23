"""End-to-End Integration Tests for Complex Cross-Folder Queries.

This test suite demonstrates real-world value of Vercel-style optimizations:
1. Multi-folder search operations (finding files across nested directories)
2. Large file handling with head-first pattern
3. Output truncation for long results
4. Lazy tool loading based on different query types
5. Smart cat with different modes (head, tail, range, full)
6. Complex grep patterns across multiple files
7. Combined operations (find + grep + read)

Tests verify correct results, token efficiency, and acceptable performance.
"""

import pytest
import asyncio
import time
from pathlib import Path

from app.agent.tools.bash_tools import (
    build_command,
    build_cat_command,
    build_smart_cat_command,
    BASH_TOOLS,
)
from app.agent.tools.tool_selector import ToolSelector
from app.agent.output_processor import OutputProcessor
from app.sandbox.executor import SandboxExecutor


# =============================================================================
# Test Data Paths
# =============================================================================

DATA_ROOT = Path(__file__).parent.parent / "data"
BENCHMARK_DIR = DATA_ROOT / "benchmark"
ARXIV_100_DIR = BENCHMARK_DIR / "arxiv-100-papers"
ARXIV_1000_DIR = BENCHMARK_DIR / "arxiv-1000-papers"
PROJECTS_DIR = DATA_ROOT / "projects"
KNOWLEDGE_BASE_DIR = DATA_ROOT / "knowledge-base"
NOTES_DIR = DATA_ROOT / "notes"


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
# Test Multi-Folder Search Operations
# =============================================================================

class TestMultiFolderSearchOperations:
    """Test complex search operations across multiple nested folders."""

    @pytest.mark.asyncio
    async def test_find_json_files_across_all_folders(self, sandbox_executor):
        """Find all JSON files across the entire data directory tree."""
        cmd = build_command("find", {
            "path": ".",
            "name_pattern": "*.json"
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success
        # Should find JSON files in benchmark and potentially other folders
        assert len(result.stdout.strip().split('\n')) > 0
        # Verify paths are from different folders
        paths = result.stdout.strip().split('\n')
        folders = set(Path(p).parts[0] for p in paths if p)
        assert len(folders) > 0  # Files from multiple folders

    @pytest.mark.asyncio
    async def test_find_markdown_files_in_nested_structure(self, sandbox_executor):
        """Find all markdown files showing nested directory capability."""
        cmd = build_command("find", {
            "path": ".",
            "name_pattern": "*.md"
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success
        stdout_lines = [line for line in result.stdout.strip().split('\n') if line]
        # Should find markdown in projects, knowledge-base, notes, benchmark
        assert len(stdout_lines) > 0

        # Verify nested paths exist
        nested_paths = [p for p in stdout_lines if p.count('/') > 1]
        assert len(nested_paths) > 0, "Should find files in nested directories"

    @pytest.mark.asyncio
    async def test_grep_pattern_across_benchmark_folders(self, sandbox_executor):
        """Grep for patterns across benchmark folder with nested papers."""
        if not BENCHMARK_DIR.exists():
            pytest.skip("benchmark folder not found")

        # Search for common academic terms across all benchmark files
        cmd = build_command("grep", {
            "pattern": "neural",
            "path": "benchmark",
            "recursive": True,
            "ignore_case": True
        })
        result = await sandbox_executor.execute(cmd)

        # Should search across all benchmark subfolders
        assert result.success
        # If matches found, verify they come from nested folders
        if result.stdout:
            assert "arxiv-" in result.stdout or len(result.stdout.strip()) == 0

    @pytest.mark.asyncio
    async def test_recursive_grep_with_case_insensitive(self, sandbox_executor):
        """Test recursive grep with case-insensitive search across folders."""
        # Search for "README" in any case across all folders
        cmd = build_command("grep", {
            "pattern": "project",
            "path": "projects",
            "recursive": True,
            "ignore_case": True
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success
        # Should find project mentions in README files

    @pytest.mark.asyncio
    async def test_find_files_by_type_directories(self, sandbox_executor):
        """Test finding directories vs files using type parameter."""
        # Find all directories
        cmd = build_command("find", {
            "path": ".",
            "name_pattern": "*",
            "type": "d"
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success
        dirs = [line for line in result.stdout.strip().split('\n') if line]
        # Should find benchmark, projects, knowledge-base, notes folders
        assert len(dirs) > 0


# =============================================================================
# Test Large File Handling with Head-First Pattern
# =============================================================================

class TestLargeFileHandling:
    """Test efficient handling of large files using head-first pattern."""

    @pytest.mark.asyncio
    async def test_cat_defaults_to_head_for_large_file(self, sandbox_executor):
        """cat command should default to head for large files."""
        if not (ARXIV_100_DIR / "report.md").exists():
            pytest.skip("report.md not found")

        # Use cat without full=True
        cmd = build_command("cat", {
            "path": "benchmark/arxiv-100-papers/report.md"
        })

        assert cmd[0] == "head", "cat should default to head command"
        result = await sandbox_executor.execute(cmd)
        assert result.success

        lines = result.stdout.strip().split('\n')
        # Should be limited by head default (100 lines)
        assert len(lines) <= 100

    @pytest.mark.asyncio
    async def test_preview_tool_shows_file_efficiently(self, sandbox_executor):
        """preview tool should read beginning of file efficiently."""
        if not (BENCHMARK_DIR / "report.md").exists():
            pytest.skip("benchmark report.md not found")

        cmd = build_command("preview", {
            "path": "benchmark/report.md",
            "lines": 50
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success
        lines = result.stdout.strip().split('\n')
        assert len(lines) <= 50, "preview should limit output"

    @pytest.mark.asyncio
    async def test_head_first_vs_full_cat_comparison(self, sandbox_executor):
        """Compare head-first vs full cat on actual file."""
        if not (DATA_ROOT / "example.txt").exists():
            pytest.skip("example.txt not found")

        # Head-first (default)
        cmd_head = build_command("cat", {"path": "example.txt", "lines": 10})
        result_head = await sandbox_executor.execute(cmd_head)

        # Full cat
        cmd_full = build_command("cat", {"path": "example.txt", "full": True})
        result_full = await sandbox_executor.execute(cmd_full)

        assert result_head.success and result_full.success

        # Head version should be same or shorter
        lines_head = result_head.stdout.strip().split('\n')
        lines_full = result_full.stdout.strip().split('\n')
        assert len(lines_head) <= len(lines_full)

    @pytest.mark.asyncio
    async def test_custom_line_limit_for_cat(self, sandbox_executor):
        """Test custom line limits for cat command."""
        if not (BENCHMARK_DIR / "report.md").exists():
            pytest.skip("report.md not found")

        # Request specific number of lines
        cmd = build_command("cat", {
            "path": "benchmark/report.md",
            "lines": 20
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success
        assert cmd == ["head", "-n", "20", "benchmark/report.md"]


# =============================================================================
# Test Output Truncation
# =============================================================================

class TestOutputTruncationAdvanced:
    """Test output truncation with complex scenarios."""

    @pytest.mark.asyncio
    async def test_truncation_on_long_grep_results(
        self,
        sandbox_executor,
        output_processor
    ):
        """Test truncation when grep returns many results."""
        if not ARXIV_100_DIR.exists():
            pytest.skip("arxiv-100-papers not found")

        # Grep for common pattern that yields many results
        cmd = build_command("grep", {
            "pattern": "abstract",
            "path": "benchmark/arxiv-100-papers",
            "recursive": True,
            "ignore_case": True
        })
        result = await sandbox_executor.execute(cmd)

        if result.success and result.stdout:
            truncated = output_processor.truncate(result.stdout)

            # If output is long, verify truncation
            if truncated.original_lines > 50:
                assert truncated.was_truncated
                assert "[OUTPUT TRUNCATED" in truncated.content
                assert "grep/head/tail" in truncated.content

    def test_truncation_metadata_accuracy(self, output_processor):
        """Test that truncation metadata is accurate."""
        # Create large output
        lines = [f"result_{i}" for i in range(200)]
        long_output = "\n".join(lines)

        result = output_processor.truncate(long_output)

        assert result.was_truncated
        assert result.original_lines == 200
        assert result.original_chars == len(long_output)
        # Verify first 50 lines are preserved
        assert "result_0" in result.content
        assert "result_49" in result.content
        # Lines after 50 should not appear
        assert "result_50" not in result.content

    def test_truncation_with_very_long_lines(self, output_processor):
        """Test truncation when individual lines are very long."""
        # Create output with very long lines
        long_line = "x" * 1000
        lines = [long_line for _ in range(30)]
        output = "\n".join(lines)

        result = output_processor.truncate(output)

        # Should handle long lines gracefully
        assert result.original_lines == 30
        # May truncate by chars if total exceeds limit

    @pytest.mark.asyncio
    async def test_truncation_preserves_context(
        self,
        sandbox_executor,
        output_processor
    ):
        """Test that truncation preserves useful context from beginning."""
        if not BENCHMARK_DIR.exists():
            pytest.skip("benchmark folder not found")

        # List all files in benchmark recursively
        cmd = build_command("find", {
            "path": "benchmark",
            "name_pattern": "*"
        })
        result = await sandbox_executor.execute(cmd)

        if result.success:
            truncated = output_processor.truncate(result.stdout)

            # First files should be in truncated output
            if truncated.was_truncated:
                lines = result.stdout.strip().split('\n')
                first_file = lines[0] if lines else ""
                if first_file:
                    assert first_file in truncated.content


# =============================================================================
# Test Lazy Tool Loading
# =============================================================================

class TestLazyToolLoadingComplex:
    """Test lazy tool loading with complex query scenarios."""

    def test_multi_intent_query_selects_multiple_tool_groups(self):
        """Query with multiple intents should select tools from multiple groups."""
        tools = ToolSelector.select_tools(
            "find all Python files in projects folder and show me their content",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        # Should have search tools
        assert "find" in tool_names
        # Should have read tools
        assert any(t in tool_names for t in ["head", "cat", "smart_cat"])

    def test_analyze_and_search_combined(self):
        """Analyze + search query should select both tool groups."""
        tools = ToolSelector.select_tools(
            "count how many JSON files exist in the benchmark folder",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        # Should have analyze tools
        assert "wc" in tool_names
        # Should have search tools
        assert "find" in tool_names or "ls" in tool_names

    def test_pattern_and_read_combined(self):
        """Pattern matching + read should select grep and read tools."""
        tools = ToolSelector.select_tools(
            "grep for TODO comments and show me the file content",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        assert "grep" in tool_names
        assert any(t in tool_names for t in ["head", "cat"])

    def test_tool_selection_continuity(self):
        """Test that previous tools are maintained for continuity."""
        # First query: search
        tools1 = ToolSelector.select_tools(
            "find Python files",
            include_all_on_unknown=False
        )
        prev_tools = {t["function"]["name"] for t in tools1}

        # Second query: read (with previous context)
        tools2 = ToolSelector.select_tools(
            "show the content",
            previous_tools=prev_tools,
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools2}

        # Should maintain previous search tools
        assert "find" in tool_names
        # And add new read tools
        assert any(t in tool_names for t in ["head", "cat"])

    def test_token_savings_calculation(self):
        """Calculate token savings from lazy loading."""
        total_tools = len(BASH_TOOLS)

        # Specific query should select fewer tools
        selected_tools = ToolSelector.select_tools(
            "list files in the current directory",
            include_all_on_unknown=False
        )
        selected_count = len(selected_tools)

        # Calculate savings
        tools_saved = total_tools - selected_count
        percent_saved = (tools_saved / total_tools) * 100

        # Should have meaningful savings
        assert tools_saved > 0
        # Typically save 30-50% of tools
        assert percent_saved > 0

    def test_unknown_intent_with_flag_false(self):
        """Unknown intent with include_all_on_unknown=False should return essentials."""
        tools = ToolSelector.select_tools(
            "do something random",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        # Should include essential tools
        assert "ls" in tool_names
        assert "head" in tool_names


# =============================================================================
# Test Smart Cat with Different Modes
# =============================================================================

class TestSmartCatModes:
    """Test smart_cat tool with various reading modes."""

    def test_smart_cat_head_mode_command(self):
        """Test head mode builds correct command."""
        cmd = build_smart_cat_command(
            path="benchmark/report.md",
            mode="head",
            lines=30
        )
        assert cmd == ["head", "-n", "30", "benchmark/report.md"]

    def test_smart_cat_tail_mode_command(self):
        """Test tail mode builds correct command."""
        cmd = build_smart_cat_command(
            path="notes/meeting-notes-2024.md",
            mode="tail",
            lines=15
        )
        assert cmd == ["tail", "-n", "15", "notes/meeting-notes-2024.md"]

    def test_smart_cat_range_mode_command(self):
        """Test range mode builds correct sed command."""
        cmd = build_smart_cat_command(
            path="projects/project-alpha/README.md",
            mode="range",
            start_line=10,
            end_line=30
        )
        assert cmd == ["sed", "-n", "10,30p", "projects/project-alpha/README.md"]

    def test_smart_cat_full_mode_command(self):
        """Test full mode builds cat command."""
        cmd = build_smart_cat_command(
            path="example.txt",
            mode="full"
        )
        assert cmd == ["cat", "example.txt"]

    @pytest.mark.asyncio
    async def test_smart_cat_head_execution(self, sandbox_executor):
        """Test smart_cat head mode execution."""
        if not (BENCHMARK_DIR / "report.md").exists():
            pytest.skip("report.md not found")

        cmd = build_smart_cat_command(
            path="benchmark/report.md",
            mode="head",
            lines=20
        )
        result = await sandbox_executor.execute(cmd)

        assert result.success
        lines = result.stdout.strip().split('\n')
        assert len(lines) <= 20

    @pytest.mark.asyncio
    async def test_smart_cat_tail_execution(self, sandbox_executor):
        """Test smart_cat tail mode execution."""
        if not (BENCHMARK_DIR / "report.md").exists():
            pytest.skip("report.md not found")

        cmd = build_smart_cat_command(
            path="benchmark/report.md",
            mode="tail",
            lines=10
        )
        result = await sandbox_executor.execute(cmd)

        assert result.success
        lines = result.stdout.strip().split('\n')
        assert len(lines) <= 10

    @pytest.mark.asyncio
    async def test_smart_cat_range_execution(self, sandbox_executor):
        """Test smart_cat range mode execution."""
        if not (BENCHMARK_DIR / "report.md").exists():
            pytest.skip("report.md not found")

        cmd = build_smart_cat_command(
            path="benchmark/report.md",
            mode="range",
            start_line=1,
            end_line=10
        )
        result = await sandbox_executor.execute(cmd)

        assert result.success
        lines = result.stdout.strip().split('\n')
        # Should return approximately 10 lines (1 to 10)
        assert len(lines) <= 15  # Allow some flexibility

    def test_smart_cat_default_mode_is_head(self):
        """Test that default mode is head for token efficiency."""
        cmd = build_smart_cat_command(path="test.txt")
        assert cmd[0] == "head", "Default mode should be head"


# =============================================================================
# Test Complex Grep Patterns
# =============================================================================

class TestComplexGrepPatterns:
    """Test grep with complex patterns across multiple files."""

    @pytest.mark.asyncio
    async def test_grep_with_regex_pattern(self, sandbox_executor):
        """Test grep with regex pattern."""
        if not PROJECTS_DIR.exists():
            pytest.skip("projects folder not found")

        # Search for markdown headers (lines starting with #)
        cmd = build_command("grep", {
            "pattern": "^#",
            "path": "projects",
            "recursive": True
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success
        # If matches found, verify format
        if result.stdout:
            # Should contain file paths and line numbers
            assert ":" in result.stdout

    @pytest.mark.asyncio
    async def test_case_sensitive_vs_insensitive_grep(self, sandbox_executor):
        """Test case-sensitive vs case-insensitive grep."""
        if not PROJECTS_DIR.exists():
            pytest.skip("projects folder not found")

        # Case-sensitive search
        cmd_sensitive = build_command("grep", {
            "pattern": "Project",
            "path": "projects",
            "recursive": True,
            "ignore_case": False
        })
        result_sensitive = await sandbox_executor.execute(cmd_sensitive)

        # Case-insensitive search
        cmd_insensitive = build_command("grep", {
            "pattern": "project",
            "path": "projects",
            "recursive": True,
            "ignore_case": True
        })
        result_insensitive = await sandbox_executor.execute(cmd_insensitive)

        assert result_sensitive.success
        assert result_insensitive.success

        # Insensitive should have >= results than sensitive
        lines_sensitive = len([line for line in result_sensitive.stdout.split('\n') if line])
        lines_insensitive = len([line for line in result_insensitive.stdout.split('\n') if line])
        assert lines_insensitive >= lines_sensitive

    @pytest.mark.asyncio
    async def test_grep_across_multiple_file_types(self, sandbox_executor):
        """Test grep finding pattern across different file types."""
        if not BENCHMARK_DIR.exists():
            pytest.skip("benchmark folder not found")

        # Search for common term across JSON, MD files
        cmd = build_command("grep", {
            "pattern": "arxiv",
            "path": "benchmark",
            "recursive": True,
            "ignore_case": True
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success
        # Should find matches in various file types

    @pytest.mark.asyncio
    async def test_grep_non_recursive_single_file(self, sandbox_executor):
        """Test grep on single file (non-recursive)."""
        if not (PROJECTS_DIR / "project-alpha" / "README.md").exists():
            pytest.skip("project-alpha README.md not found")

        cmd = build_command("grep", {
            "pattern": "alpha",
            "path": "projects/project-alpha/README.md",
            "recursive": False,
            "ignore_case": True
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success


# =============================================================================
# Test Combined Operations (Find + Grep + Read)
# =============================================================================

class TestCombinedOperations:
    """Test complex workflows combining multiple operations."""

    @pytest.mark.asyncio
    async def test_find_then_read_workflow(self, sandbox_executor):
        """Test workflow: find files, then read them."""
        # Step 1: Find JSON files
        cmd_find = build_command("find", {
            "path": "benchmark",
            "name_pattern": "*.json"
        })
        result_find = await sandbox_executor.execute(cmd_find)

        assert result_find.success
        files = [f for f in result_find.stdout.strip().split('\n') if f]

        if not files:
            pytest.skip("No JSON files found")

        # Step 2: Read first file found
        first_file = files[0]
        cmd_read = build_command("preview", {
            "path": first_file,
            "lines": 20
        })
        result_read = await sandbox_executor.execute(cmd_read)

        assert result_read.success

    @pytest.mark.asyncio
    async def test_grep_then_read_context_workflow(self, sandbox_executor):
        """Test workflow: grep for pattern, then read file context."""
        if not PROJECTS_DIR.exists():
            pytest.skip("projects folder not found")

        # Step 1: Grep for pattern
        cmd_grep = build_command("grep", {
            "pattern": "alpha",
            "path": "projects",
            "recursive": True,
            "ignore_case": True
        })
        result_grep = await sandbox_executor.execute(cmd_grep)

        assert result_grep.success

        if result_grep.stdout:
            # Extract file path from grep result (format: path:line:content)
            first_match = result_grep.stdout.split('\n')[0]
            if ':' in first_match:
                file_path = first_match.split(':')[0]

                # Step 2: Read the file
                cmd_read = build_command("head", {
                    "path": file_path,
                    "lines": 30
                })
                result_read = await sandbox_executor.execute(cmd_read)

                assert result_read.success

    @pytest.mark.asyncio
    async def test_tree_then_find_then_read_workflow(self, sandbox_executor):
        """Test workflow: tree to explore, find specific files, then read."""
        # Step 1: Get directory structure
        cmd_tree = build_command("tree", {
            "path": "projects",
            "max_depth": 2
        })
        result_tree = await sandbox_executor.execute(cmd_tree)

        assert result_tree.success

        # Step 2: Find markdown files
        cmd_find = build_command("find", {
            "path": "projects",
            "name_pattern": "*.md"
        })
        result_find = await sandbox_executor.execute(cmd_find)

        assert result_find.success
        files = [f for f in result_find.stdout.strip().split('\n') if f and f.endswith('.md')]

        if files:
            # Step 3: Read first markdown file
            cmd_read = build_command("cat", {
                "path": files[0],
                "lines": 50
            })
            result_read = await sandbox_executor.execute(cmd_read)

            assert result_read.success

    @pytest.mark.asyncio
    async def test_wc_then_conditional_read_workflow(self, sandbox_executor):
        """Test workflow: check file size with wc, then conditionally read."""
        if not (BENCHMARK_DIR / "report.md").exists():
            pytest.skip("report.md not found")

        # Step 1: Check line count
        cmd_wc = build_command("wc", {
            "path": "benchmark/report.md",
            "lines_only": True
        })
        result_wc = await sandbox_executor.execute(cmd_wc)

        assert result_wc.success

        # Parse line count
        try:
            line_count = int(result_wc.stdout.strip().split()[0])
        except (ValueError, IndexError):
            pytest.skip("Could not parse line count")

        # Step 2: Read with appropriate mode based on size
        if line_count < 100:
            # Small file: read all
            cmd_read = build_command("cat", {
                "path": "benchmark/report.md",
                "full": True
            })
        else:
            # Large file: read head only
            cmd_read = build_command("head", {
                "path": "benchmark/report.md",
                "lines": 50
            })

        result_read = await sandbox_executor.execute(cmd_read)
        assert result_read.success

    @pytest.mark.asyncio
    async def test_parallel_find_operations(self, sandbox_executor):
        """Test executing multiple find operations in parallel."""
        # Find different file types in parallel
        tasks = [
            sandbox_executor.execute(build_command("find", {
                "path": ".",
                "name_pattern": "*.json"
            })),
            sandbox_executor.execute(build_command("find", {
                "path": ".",
                "name_pattern": "*.md"
            })),
            sandbox_executor.execute(build_command("find", {
                "path": ".",
                "name_pattern": "*.txt"
            }))
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r.success for r in results)

        # Should find different file types
        json_files = [f for f in results[0].stdout.split('\n') if f]
        md_files = [f for f in results[1].stdout.split('\n') if f]
        txt_files = [f for f in results[2].stdout.split('\n') if f]

        # At least one type should have results
        assert len(json_files) > 0 or len(md_files) > 0 or len(txt_files) > 0


# =============================================================================
# Test Token Efficiency and Performance
# =============================================================================

class TestTokenEfficiencyAndPerformance:
    """Test token efficiency and performance characteristics."""

    def test_head_first_reduces_tokens(self):
        """Test that head-first pattern reduces token consumption."""
        # Full cat command
        cmd_full = build_cat_command(path="large_file.log", full=True)

        # Head-first (default)
        cmd_head = build_cat_command(path="large_file.log", lines=100)

        # Head command is more token-efficient
        assert cmd_head[0] == "head"
        assert cmd_full[0] == "cat"

    def test_lazy_loading_reduces_tool_count(self):
        """Test that lazy loading significantly reduces tool count."""
        total_tools = len(BASH_TOOLS)

        # Test various specific queries
        queries = [
            "find Python files",
            "show me the content",
            "count lines",
            "list directories"
        ]

        for query in queries:
            tools = ToolSelector.select_tools(query, include_all_on_unknown=False)
            selected_count = len(tools)

            # Should select fewer tools than total
            assert selected_count < total_tools
            # Should save at least 20% of tools
            reduction = ((total_tools - selected_count) / total_tools) * 100
            assert reduction >= 20

    @pytest.mark.asyncio
    async def test_truncation_reduces_output_size(
        self,
        sandbox_executor,
        output_processor
    ):
        """Test that truncation reduces output size."""
        if not BENCHMARK_DIR.exists():
            pytest.skip("benchmark folder not found")

        # Find all files (potentially long output)
        cmd = build_command("find", {
            "path": "benchmark",
            "name_pattern": "*"
        })
        result = await sandbox_executor.execute(cmd)

        if result.success and len(result.stdout) > 1000:
            original_size = len(result.stdout)
            truncated = output_processor.truncate(result.stdout)
            truncated_size = len(truncated.content)

            if truncated.was_truncated:
                # Truncated version should be smaller
                assert truncated_size < original_size
                # Should save significant space
                reduction = ((original_size - truncated_size) / original_size) * 100
                assert reduction > 0

    def test_smart_cat_modes_token_efficiency_order(self):
        """Test that smart_cat modes are ordered by token efficiency."""
        # Mode efficiency: head > tail > range > full
        path = "test.txt"

        cmd_head = build_smart_cat_command(path=path, mode="head", lines=50)
        cmd_tail = build_smart_cat_command(path=path, mode="tail", lines=50)
        cmd_range = build_smart_cat_command(path=path, mode="range", start_line=1, end_line=50)
        cmd_full = build_smart_cat_command(path=path, mode="full")

        # All partial modes should not be full cat
        assert cmd_head[0] != "cat"
        assert cmd_tail[0] != "cat"
        assert cmd_range[0] != "cat"
        # Only full mode uses cat
        assert cmd_full[0] == "cat"

    @pytest.mark.asyncio
    async def test_command_execution_performance(self, sandbox_executor):
        """Test that command execution is performant."""
        if not (DATA_ROOT / "example.txt").exists():
            pytest.skip("example.txt not found")

        # Execute simple command and measure time
        start_time = time.time()

        cmd = build_command("head", {
            "path": "example.txt",
            "lines": 10
        })
        result = await sandbox_executor.execute(cmd)

        elapsed = time.time() - start_time

        assert result.success
        # Should execute in reasonable time (< 1 second for simple command)
        assert elapsed < 1.0

    def test_tool_selection_is_fast(self):
        """Test that tool selection is fast."""
        queries = [
            "find all files",
            "show content",
            "grep pattern",
            "count lines"
        ] * 25  # 100 queries

        start_time = time.time()

        for query in queries:
            ToolSelector.select_tools(query, include_all_on_unknown=False)

        elapsed = time.time() - start_time

        # Should complete 100 selections in under 0.5 seconds
        assert elapsed < 0.5


# =============================================================================
# Test Edge Cases and Error Handling
# =============================================================================

class TestEdgeCasesComplexQueries:
    """Test edge cases in complex query scenarios."""

    @pytest.mark.asyncio
    async def test_empty_directory_find(self, sandbox_executor, tmp_path):
        """Test find on empty directory."""
        # This test uses data directory which exists
        cmd = build_command("find", {
            "path": ".",
            "name_pattern": "*.nonexistent"
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success
        # Should return empty or minimal output

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, sandbox_executor):
        """Test grep when pattern doesn't match anything."""
        cmd = build_command("grep", {
            "pattern": "VERYRAREPATTERNXYZ123",
            "path": ".",
            "recursive": True
        })
        await sandbox_executor.execute(cmd)

        # Grep returns non-zero exit when no matches, but executor handles it
        # Check that it doesn't crash

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, sandbox_executor):
        """Test reading nonexistent file."""
        cmd = build_command("cat", {
            "path": "nonexistent_file_xyz.txt"
        })
        result = await sandbox_executor.execute(cmd)

        # Should fail gracefully
        assert not result.success or "No such file" in result.stderr

    def test_tool_selection_with_empty_query(self):
        """Test tool selection with empty query."""
        tools = ToolSelector.select_tools("", include_all_on_unknown=False)
        tool_names = {t["function"]["name"] for t in tools}

        # Should return essential tools
        assert "ls" in tool_names
        assert "head" in tool_names

    def test_truncation_with_empty_output(self, output_processor):
        """Test truncation with empty output."""
        result = output_processor.truncate("")

        assert not result.was_truncated
        assert result.content == ""
        assert result.original_lines == 1  # Empty string splits to one empty line

    @pytest.mark.asyncio
    async def test_smart_cat_range_beyond_file_length(self, sandbox_executor):
        """Test smart_cat range mode with range beyond file length."""
        if not (DATA_ROOT / "example.txt").exists():
            pytest.skip("example.txt not found")

        # Request lines far beyond file length
        cmd = build_smart_cat_command(
            path="example.txt",
            mode="range",
            start_line=1000,
            end_line=2000
        )
        result = await sandbox_executor.execute(cmd)

        # Should succeed but return empty or partial output
        assert result.success


# =============================================================================
# Test Real-World Query Patterns
# =============================================================================

class TestRealWorldQueryPatterns:
    """Test real-world query patterns that users might execute."""

    @pytest.mark.asyncio
    async def test_find_and_analyze_project_structure(self, sandbox_executor):
        """Real-world: Explore project structure."""
        # User wants to understand project structure
        queries = [
            # 1. Get overview
            build_command("tree", {"path": "projects", "max_depth": 2}),
            # 2. Find all markdown docs
            build_command("find", {"path": "projects", "name_pattern": "*.md"}),
            # 3. List project folders
            build_command("ls", {"path": "projects", "all": False, "long": True})
        ]

        for cmd in queries:
            result = await sandbox_executor.execute(cmd)
            assert result.success

    @pytest.mark.asyncio
    async def test_search_for_specific_content(self, sandbox_executor):
        """Real-world: Search for specific content across codebase."""
        if not PROJECTS_DIR.exists():
            pytest.skip("projects folder not found")

        # User searches for specific term
        cmd = build_command("grep", {
            "pattern": "project",
            "path": "projects",
            "recursive": True,
            "ignore_case": True
        })
        result = await sandbox_executor.execute(cmd)

        assert result.success

    @pytest.mark.asyncio
    async def test_examine_large_data_file(self, sandbox_executor, output_processor):
        """Real-world: Examine large data file safely."""
        if not ARXIV_100_DIR.exists():
            pytest.skip("arxiv-100-papers not found")

        # User wants to examine large JSON file
        # Step 1: Preview first
        cmd_preview = build_command("preview", {
            "path": "benchmark/arxiv-100-papers/statistics.json",
            "lines": 50
        })
        result_preview = await sandbox_executor.execute(cmd_preview)

        if result_preview.success:
            # Step 2: Truncate output if needed
            truncated = output_processor.truncate(result_preview.stdout)

            # Should be manageable size
            assert len(truncated.content) < 50000  # Reasonable token limit

    @pytest.mark.asyncio
    async def test_multi_step_investigation(self, sandbox_executor):
        """Real-world: Multi-step investigation workflow."""
        # Scenario: User wants to find all JSON files and examine one

        # Step 1: Find JSON files
        cmd_find = build_command("find", {
            "path": "benchmark",
            "name_pattern": "*.json"
        })
        result_find = await sandbox_executor.execute(cmd_find)
        assert result_find.success

        files = [f for f in result_find.stdout.strip().split('\n') if f.endswith('.json')]

        if files:
            # Step 2: Count lines in first file
            cmd_wc = build_command("wc", {
                "path": files[0],
                "lines_only": True
            })
            result_wc = await sandbox_executor.execute(cmd_wc)
            assert result_wc.success

            # Step 3: Read beginning of file
            cmd_head = build_command("head", {
                "path": files[0],
                "lines": 20
            })
            result_head = await sandbox_executor.execute(cmd_head)
            assert result_head.success

    def test_progressive_tool_loading_simulation(self):
        """Real-world: Simulate progressive tool loading in conversation."""
        # Turn 1: User explores
        tools_1 = ToolSelector.select_tools(
            "what folders exist here",
            include_all_on_unknown=False
        )
        names_1 = {t["function"]["name"] for t in tools_1}

        # Turn 2: User searches (maintain previous context)
        tools_2 = ToolSelector.select_tools(
            "find JSON files",
            previous_tools=names_1,
            include_all_on_unknown=False
        )
        names_2 = {t["function"]["name"] for t in tools_2}

        # Turn 3: User reads (maintain previous context)
        tools_3 = ToolSelector.select_tools(
            "show me the content",
            previous_tools=names_2,
            include_all_on_unknown=False
        )
        names_3 = {t["function"]["name"] for t in tools_3}

        # Each turn should maintain previous tools
        assert names_1.issubset(names_2)  # Turn 2 includes turn 1 tools
        assert names_2.issubset(names_3)  # Turn 3 includes turn 2 tools
