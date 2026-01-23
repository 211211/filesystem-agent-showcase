"""
Tests for the token usage benchmark script.

These tests verify the benchmark infrastructure without making actual API calls.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import asdict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.token_usage_comparison import (
    TokenMetrics,
    QueryBenchmarkResult,
    BenchmarkSummary,
    TokenUsageBenchmark,
    GPT4_INPUT_PRICE_PER_1K,
    GPT4_OUTPUT_PRICE_PER_1K,
)


class TestTokenMetrics:
    """Test TokenMetrics dataclass."""

    def test_token_metrics_total_tokens(self):
        """Test total tokens calculation."""
        metrics = TokenMetrics(input_tokens=1000, output_tokens=500)
        assert metrics.total_tokens == 1500

    def test_token_metrics_cost_calculation(self):
        """Test cost calculation with GPT-4 pricing."""
        metrics = TokenMetrics(input_tokens=1000, output_tokens=500)
        expected_input_cost = (1000 / 1000) * GPT4_INPUT_PRICE_PER_1K
        expected_output_cost = (500 / 1000) * GPT4_OUTPUT_PRICE_PER_1K
        expected_total = expected_input_cost + expected_output_cost
        assert abs(metrics.cost - expected_total) < 0.0001


class TestQueryBenchmarkResult:
    """Test QueryBenchmarkResult calculations."""

    def test_token_reduction_calculation(self):
        """Test token reduction calculation."""
        result = QueryBenchmarkResult(
            query="test",
            category="read",
            baseline_input=1000,
            baseline_output=500,
            optimized_input=400,
            optimized_output=200,
        )
        assert result.baseline_total == 1500
        assert result.optimized_total == 600
        assert result.token_reduction == 900

    def test_token_reduction_percentage(self):
        """Test token reduction percentage."""
        result = QueryBenchmarkResult(
            query="test",
            category="read",
            baseline_input=1000,
            baseline_output=500,
            optimized_input=400,
            optimized_output=200,
        )
        # (1500 - 600) / 1500 = 0.6 = 60%
        assert abs(result.token_reduction_pct - 60.0) < 0.1

    def test_input_reduction_percentage(self):
        """Test input token reduction percentage."""
        result = QueryBenchmarkResult(
            query="test",
            category="read",
            baseline_input=1000,
            baseline_output=500,
            optimized_input=400,
            optimized_output=200,
        )
        # (1000 - 400) / 1000 = 0.6 = 60%
        assert abs(result.input_reduction_pct - 60.0) < 0.1

    def test_output_reduction_percentage(self):
        """Test output token reduction percentage."""
        result = QueryBenchmarkResult(
            query="test",
            category="read",
            baseline_input=1000,
            baseline_output=500,
            optimized_input=400,
            optimized_output=200,
        )
        # (500 - 200) / 500 = 0.6 = 60%
        assert abs(result.output_reduction_pct - 60.0) < 0.1

    def test_cost_calculations(self):
        """Test cost calculations."""
        result = QueryBenchmarkResult(
            query="test",
            category="read",
            baseline_input=1000,
            baseline_output=500,
            optimized_input=400,
            optimized_output=200,
        )

        # Baseline: 1000 * 0.01/1000 + 500 * 0.03/1000 = 0.01 + 0.015 = 0.025
        # Optimized: 400 * 0.01/1000 + 200 * 0.03/1000 = 0.004 + 0.006 = 0.01
        # Savings: 0.025 - 0.01 = 0.015

        assert abs(result.baseline_cost - 0.025) < 0.0001
        assert abs(result.optimized_cost - 0.01) < 0.0001
        assert abs(result.cost_savings - 0.015) < 0.0001

    def test_time_diff_percentage(self):
        """Test execution time difference percentage."""
        result = QueryBenchmarkResult(
            query="test",
            category="read",
            baseline_time=2.0,
            optimized_time=1.5,
        )
        # (1.5 - 2.0) / 2.0 = -0.25 = -25%
        assert abs(result.time_diff_pct - (-25.0)) < 0.1

    def test_zero_baseline_handling(self):
        """Test handling of zero baseline (avoid division by zero)."""
        result = QueryBenchmarkResult(
            query="test",
            category="read",
            baseline_input=0,
            baseline_output=0,
            optimized_input=400,
            optimized_output=200,
        )
        assert result.token_reduction_pct == 0.0
        assert result.input_reduction_pct == 0.0
        assert result.output_reduction_pct == 0.0


class TestBenchmarkSummary:
    """Test BenchmarkSummary calculations."""

    def test_summary_aggregations(self):
        """Test summary aggregations across multiple results."""
        results = [
            QueryBenchmarkResult(
                query="query1",
                category="read",
                baseline_input=1000,
                baseline_output=500,
                optimized_input=400,
                optimized_output=200,
            ),
            QueryBenchmarkResult(
                query="query2",
                category="search",
                baseline_input=800,
                baseline_output=300,
                optimized_input=350,
                optimized_output=150,
            ),
        ]

        summary = BenchmarkSummary(results=results, iterations_per_query=3)

        # Total baseline: (1000+500) + (800+300) = 2600
        # Total optimized: (400+200) + (350+150) = 1100
        # Total saved: 2600 - 1100 = 1500

        assert summary.total_baseline_tokens == 2600
        assert summary.total_optimized_tokens == 1100
        assert summary.total_tokens_saved == 1500

    def test_summary_average_reduction(self):
        """Test average token reduction calculation."""
        results = [
            QueryBenchmarkResult(
                query="query1",
                category="read",
                baseline_input=1000,
                baseline_output=500,
                optimized_input=400,
                optimized_output=200,
            ),  # 60% reduction
            QueryBenchmarkResult(
                query="query2",
                category="search",
                baseline_input=1000,
                baseline_output=0,
                optimized_input=600,
                optimized_output=0,
            ),  # 40% reduction
        ]

        summary = BenchmarkSummary(results=results, iterations_per_query=3)

        # Average: (60 + 40) / 2 = 50%
        assert abs(summary.avg_token_reduction_pct - 50.0) < 0.1

    def test_monthly_savings_projection(self):
        """Test monthly savings projection at 100 queries/day."""
        results = [
            QueryBenchmarkResult(
                query="query1",
                category="read",
                baseline_input=1000,
                baseline_output=500,
                optimized_input=400,
                optimized_output=200,
            ),
        ]

        summary = BenchmarkSummary(results=results, iterations_per_query=3)

        # Baseline cost: 1000*0.01/1000 + 500*0.03/1000 = 0.025
        # Optimized cost: 400*0.01/1000 + 200*0.03/1000 = 0.01
        # Savings per query: 0.015
        # Monthly (100 q/day * 30 days): 0.015 * 100 * 30 = 45.0

        assert abs(summary.monthly_savings_100qpd - 45.0) < 0.01

    def test_empty_results(self):
        """Test summary with no results."""
        summary = BenchmarkSummary(results=[], iterations_per_query=3)

        assert summary.total_baseline_tokens == 0
        assert summary.total_optimized_tokens == 0
        assert summary.total_tokens_saved == 0
        assert summary.avg_token_reduction_pct == 0.0
        assert summary.monthly_savings_100qpd == 0.0


class TestTokenUsageBenchmark:
    """Test TokenUsageBenchmark class."""

    def test_benchmark_initialization(self, tmp_path):
        """Test benchmark initialization."""
        benchmark = TokenUsageBenchmark(
            data_root=str(tmp_path),
            iterations=5
        )

        assert benchmark.data_root == tmp_path
        assert benchmark.iterations == 5
        assert benchmark.client is not None

    def test_test_queries_structure(self):
        """Test that TEST_QUERIES has correct structure."""
        benchmark = TokenUsageBenchmark()

        assert len(benchmark.TEST_QUERIES) > 0
        for query_spec in benchmark.TEST_QUERIES:
            assert "query" in query_spec
            assert "category" in query_spec
            assert isinstance(query_spec["query"], str)
            assert isinstance(query_spec["category"], str)
            assert len(query_spec["query"]) > 0

    def test_test_queries_categories(self):
        """Test that queries cover different categories."""
        benchmark = TokenUsageBenchmark()

        categories = {q["category"] for q in benchmark.TEST_QUERIES}

        # Should have multiple categories
        assert len(categories) >= 4
        # Should include key categories
        expected_categories = {"read", "search", "analyze"}
        assert len(categories & expected_categories) >= 2

    def test_baseline_agent_configuration(self):
        """Test baseline agent has optimizations disabled."""
        benchmark = TokenUsageBenchmark(data_root="./data")
        agent = benchmark._create_baseline_agent()

        # Should NOT have lazy loading
        assert agent.use_lazy_loading is False

        # Should have large output limits (minimal truncation)
        assert agent.output_processor.max_lines >= 1000
        assert agent.output_processor.max_chars >= 100000

    def test_optimized_agent_configuration(self):
        """Test optimized agent has optimizations enabled."""
        benchmark = TokenUsageBenchmark(data_root="./data")
        agent = benchmark._create_optimized_agent()

        # Should have lazy loading
        assert agent.use_lazy_loading is True

        # Should have reasonable output limits (200 lines is the new default
        # because 50 lines caused retry loops that INCREASED token usage)
        # See benchmarks/token_usage_comparison_v2.py for analysis
        assert agent.output_processor.max_lines <= 250
        assert agent.output_processor.max_chars <= 60000

    def test_export_results_structure(self, tmp_path):
        """Test exported results have correct structure."""
        import json

        results = [
            QueryBenchmarkResult(
                query="test query",
                category="read",
                baseline_input=1000,
                baseline_output=500,
                optimized_input=400,
                optimized_output=200,
            ),
        ]

        summary = BenchmarkSummary(results=results, iterations_per_query=3)

        benchmark = TokenUsageBenchmark()
        export_path = tmp_path / "test_results.json"
        benchmark._export_results(summary, str(export_path))

        # Verify file was created
        assert export_path.exists()

        # Verify structure
        with open(export_path) as f:
            data = json.load(f)

        assert "summary" in data
        assert "results" in data
        assert len(data["results"]) == 1

        # Verify summary fields
        summary_data = data["summary"]
        assert "total_baseline_tokens" in summary_data
        assert "total_optimized_tokens" in summary_data
        assert "avg_token_reduction_pct" in summary_data
        assert "monthly_savings_100qpd" in summary_data

        # Verify result fields
        result_data = data["results"][0]
        assert result_data["query"] == "test query"
        assert result_data["category"] == "read"
        assert result_data["baseline_input"] == 1000
        assert result_data["optimized_input"] == 400


class TestIntegration:
    """Integration tests for the benchmark system."""

    @pytest.mark.asyncio
    async def test_benchmark_query_mock(self, tmp_path):
        """Test benchmark_query with mocked LLM responses."""
        # This test verifies the flow without making actual API calls
        benchmark = TokenUsageBenchmark(data_root=str(tmp_path), iterations=1)

        # Mock the OpenAI client
        mock_response = Mock()
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 1000
        mock_response.usage.completion_tokens = 500
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].message.tool_calls = None

        # Patch the client
        with patch.object(
            benchmark.client.chat.completions,
            'create',
            new=AsyncMock(return_value=mock_response)
        ):
            query_spec = {"query": "test query", "category": "test"}

            # This should complete without errors
            result = await benchmark.benchmark_query(query_spec)

            assert result.query == "test query"
            assert result.category == "test"
            assert result.baseline_input > 0
            assert result.optimized_input > 0


def test_pricing_constants():
    """Test that pricing constants are set correctly."""
    # GPT-4 pricing should be reasonable
    assert 0.005 <= GPT4_INPUT_PRICE_PER_1K <= 0.05
    assert 0.01 <= GPT4_OUTPUT_PRICE_PER_1K <= 0.10
    # Output should be more expensive than input
    assert GPT4_OUTPUT_PRICE_PER_1K > GPT4_INPUT_PRICE_PER_1K
