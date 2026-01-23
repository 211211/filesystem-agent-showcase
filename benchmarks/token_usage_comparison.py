#!/usr/bin/env python3
"""
Token Usage Comparison Benchmark - Vercel Optimizations Impact

Measures token savings from implementing Vercel's filesystem agent patterns:
1. Head-first reading (default to first N lines instead of full cat)
2. Output truncation (limit output sent back to LLM)
3. Lazy tool loading (only load relevant tools based on intent)

Expected results: ~58% token reduction for first-time queries
Cost savings: $0.21 → $0.09 per query (~$630/month at 100 queries/day)

Usage:
    poetry run python benchmarks/token_usage_comparison.py
    poetry run python benchmarks/token_usage_comparison.py --quick
    poetry run python benchmarks/token_usage_comparison.py --iterations 10
    poetry run python benchmarks/token_usage_comparison.py --export results.json
"""

import asyncio
import argparse
import json
import statistics
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime

# Add parent to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import AsyncAzureOpenAI
from app.agent.filesystem_agent import FilesystemAgent, AgentResponse
from app.sandbox.executor import SandboxExecutor
from app.agent.output_processor import OutputProcessor
from app.agent.tools.tool_selector import ToolSelector
from app.settings import get_settings


# GPT-4 pricing (as of 2025)
GPT4_INPUT_PRICE_PER_1K = 0.01  # $0.01 per 1K input tokens
GPT4_OUTPUT_PRICE_PER_1K = 0.03  # $0.03 per 1K output tokens


@dataclass
class TokenMetrics:
    """Token usage metrics for a single query."""
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    iterations: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost(self) -> float:
        """Calculate cost in USD."""
        input_cost = (self.input_tokens / 1000) * GPT4_INPUT_PRICE_PER_1K
        output_cost = (self.output_tokens / 1000) * GPT4_OUTPUT_PRICE_PER_1K
        return input_cost + output_cost


@dataclass
class QueryBenchmarkResult:
    """Result for a single query comparison."""
    query: str
    category: str

    # Without optimizations
    baseline_input: int = 0
    baseline_output: int = 0
    baseline_tools: int = 0
    baseline_iterations: int = 0

    # With optimizations
    optimized_input: int = 0
    optimized_output: int = 0
    optimized_tools: int = 0
    optimized_iterations: int = 0

    # Execution times
    baseline_time: float = 0.0
    optimized_time: float = 0.0

    @property
    def baseline_total(self) -> int:
        return self.baseline_input + self.baseline_output

    @property
    def optimized_total(self) -> int:
        return self.optimized_input + self.optimized_output

    @property
    def token_reduction(self) -> int:
        return self.baseline_total - self.optimized_total

    @property
    def token_reduction_pct(self) -> float:
        if self.baseline_total == 0:
            return 0.0
        return (self.token_reduction / self.baseline_total) * 100

    @property
    def input_reduction_pct(self) -> float:
        if self.baseline_input == 0:
            return 0.0
        return ((self.baseline_input - self.optimized_input) / self.baseline_input) * 100

    @property
    def output_reduction_pct(self) -> float:
        if self.baseline_output == 0:
            return 0.0
        return ((self.baseline_output - self.optimized_output) / self.baseline_output) * 100

    @property
    def baseline_cost(self) -> float:
        input_cost = (self.baseline_input / 1000) * GPT4_INPUT_PRICE_PER_1K
        output_cost = (self.baseline_output / 1000) * GPT4_OUTPUT_PRICE_PER_1K
        return input_cost + output_cost

    @property
    def optimized_cost(self) -> float:
        input_cost = (self.optimized_input / 1000) * GPT4_INPUT_PRICE_PER_1K
        output_cost = (self.optimized_output / 1000) * GPT4_OUTPUT_PRICE_PER_1K
        return input_cost + output_cost

    @property
    def cost_savings(self) -> float:
        return self.baseline_cost - self.optimized_cost

    @property
    def time_diff_pct(self) -> float:
        if self.baseline_time == 0:
            return 0.0
        return ((self.optimized_time - self.baseline_time) / self.baseline_time) * 100


@dataclass
class BenchmarkSummary:
    """Overall benchmark summary."""
    results: list[QueryBenchmarkResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    iterations_per_query: int = 1

    @property
    def total_baseline_tokens(self) -> int:
        return sum(r.baseline_total for r in self.results)

    @property
    def total_optimized_tokens(self) -> int:
        return sum(r.optimized_total for r in self.results)

    @property
    def total_tokens_saved(self) -> int:
        return self.total_baseline_tokens - self.total_optimized_tokens

    @property
    def avg_token_reduction_pct(self) -> float:
        if not self.results:
            return 0.0
        return statistics.mean(r.token_reduction_pct for r in self.results)

    @property
    def total_baseline_cost(self) -> float:
        return sum(r.baseline_cost for r in self.results)

    @property
    def total_optimized_cost(self) -> float:
        return sum(r.optimized_cost for r in self.results)

    @property
    def total_cost_savings(self) -> float:
        return self.total_baseline_cost - self.total_optimized_cost

    @property
    def monthly_savings_100qpd(self) -> float:
        """Estimated monthly savings at 100 queries per day."""
        if not self.results:
            return 0.0
        return self.total_cost_savings * (100 / len(self.results)) * 30

    @property
    def avg_time_impact_pct(self) -> float:
        if not self.results:
            return 0.0
        return statistics.mean(r.time_diff_pct for r in self.results)


class TokenUsageBenchmark:
    """Benchmark comparing token usage with and without optimizations."""

    # Test queries covering different scenarios
    TEST_QUERIES = [
        {
            "query": "List all Python files in the data directory",
            "category": "search",
        },
        {
            "query": "Show me the content of the README.md file",
            "category": "read",
        },
        {
            "query": "Find all files containing the word 'TODO'",
            "category": "pattern_search",
        },
        {
            "query": "How many markdown files are in the benchmark folder?",
            "category": "analyze",
        },
        {
            "query": "Search for 'learning' in all JSON files",
            "category": "mixed",
        },
        {
            "query": "Show me the first 20 lines of config files",
            "category": "read",
        },
        {
            "query": "Find all directories in the projects folder",
            "category": "search",
        },
        {
            "query": "Count lines in all Python files",
            "category": "analyze",
        },
    ]

    def __init__(self, data_root: str = "./data", iterations: int = 3):
        self.data_root = Path(data_root).resolve()
        self.iterations = iterations
        self.settings = get_settings()

        # Initialize OpenAI client
        self.client = AsyncAzureOpenAI(
            api_key=self.settings.azure_openai_api_key,
            api_version=self.settings.azure_openai_api_version,
            azure_endpoint=self.settings.azure_openai_endpoint,
        )

    def _create_baseline_agent(self) -> FilesystemAgent:
        """Create agent WITHOUT optimizations (baseline)."""
        sandbox = SandboxExecutor(self.data_root)

        # No output truncation
        output_processor = OutputProcessor(max_lines=10000, max_chars=1000000)

        return FilesystemAgent(
            client=self.client,
            deployment_name=self.settings.azure_openai_deployment_name,
            data_root=self.data_root,
            sandbox=sandbox,
            max_tool_iterations=10,
            parallel_execution=True,
            max_concurrent_tools=5,
            output_processor=output_processor,
            use_lazy_loading=False,  # Load all tools
        )

    def _create_optimized_agent(self) -> FilesystemAgent:
        """Create agent WITH optimizations."""
        sandbox = SandboxExecutor(self.data_root)

        # With output truncation (default limits)
        output_processor = OutputProcessor()  # max_lines=50, max_chars=10000

        return FilesystemAgent(
            client=self.client,
            deployment_name=self.settings.azure_openai_deployment_name,
            data_root=self.data_root,
            sandbox=sandbox,
            max_tool_iterations=10,
            parallel_execution=True,
            max_concurrent_tools=5,
            output_processor=output_processor,
            use_lazy_loading=True,  # Enable lazy tool loading
        )

    async def _run_query_and_measure(
        self,
        agent: FilesystemAgent,
        query: str
    ) -> tuple[AgentResponse, TokenMetrics, float]:
        """Run a query and measure token usage.

        Returns:
            Tuple of (response, token_metrics, execution_time)
        """
        import time

        # Track tokens by capturing raw response
        total_input_tokens = 0
        total_output_tokens = 0
        tool_calls = 0
        iterations = 0

        start_time = time.perf_counter()

        # Build message history
        from app.agent.prompts import SYSTEM_PROMPT
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.append({"role": "user", "content": query})

        # Select tools based on intent
        tools = agent.get_tools_for_message(query)

        # Agent loop - manually to capture token usage
        for iteration in range(agent.max_tool_iterations):
            iterations += 1

            # Call LLM
            response = await agent.client.chat.completions.create(
                model=agent.deployment_name,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )

            # Capture token usage
            if response.usage:
                total_input_tokens += response.usage.prompt_tokens
                total_output_tokens += response.usage.completion_tokens

            response_message = response.choices[0].message

            # Check if we need to execute tools
            if not response_message.tool_calls:
                # Done
                break

            # Parse and execute tool calls
            parsed_tool_calls = agent._parse_tool_calls(response_message)
            tool_calls += len(parsed_tool_calls)

            # Track used tools for lazy loading
            for tc in parsed_tool_calls:
                agent._used_tools.add(tc.name)

            # Add assistant message
            messages.append({
                "role": "assistant",
                "content": response_message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        }
                    }
                    for tc in parsed_tool_calls
                ]
            })

            # Execute tools
            if agent.parallel_execution and len(parsed_tool_calls) > 1:
                execution_results = await agent._execute_tools_parallel(parsed_tool_calls)
            else:
                execution_results = await agent._execute_tools_sequential(parsed_tool_calls)

            # Add tool results to messages
            for tc, result in execution_results:
                raw_output = result.stdout if result.success else f"Error: {result.stderr}"
                output = agent.output_processor.process(raw_output)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": output,
                })

        execution_time = time.perf_counter() - start_time

        metrics = TokenMetrics(
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            tool_calls=tool_calls,
            iterations=iterations,
        )

        # Create a dummy response
        final_response = AgentResponse(
            message=response_message.content or "",
            tool_calls=[],
            tool_results=[],
        )

        return final_response, metrics, execution_time

    async def benchmark_query(self, query_spec: dict) -> QueryBenchmarkResult:
        """Benchmark a single query."""
        query = query_spec["query"]
        category = query_spec["category"]

        print(f"\n{'='*70}")
        print(f"Query: {query}")
        print(f"Category: {category}")
        print(f"{'='*70}")

        result = QueryBenchmarkResult(query=query, category=category)

        # Run baseline (without optimizations)
        print("\n[1/2] Running BASELINE (no optimizations)...")
        baseline_agent = self._create_baseline_agent()

        baseline_metrics_list = []
        baseline_times = []

        for i in range(self.iterations):
            print(f"  Iteration {i+1}/{self.iterations}...", end=" ", flush=True)
            baseline_agent.reset_used_tools()  # Reset for each iteration
            _, metrics, exec_time = await self._run_query_and_measure(
                baseline_agent, query
            )
            baseline_metrics_list.append(metrics)
            baseline_times.append(exec_time)
            print(f"Input: {metrics.input_tokens}, Output: {metrics.output_tokens}, Time: {exec_time:.2f}s")

        # Average baseline
        result.baseline_input = int(statistics.mean(m.input_tokens for m in baseline_metrics_list))
        result.baseline_output = int(statistics.mean(m.output_tokens for m in baseline_metrics_list))
        result.baseline_tools = int(statistics.mean(m.tool_calls for m in baseline_metrics_list))
        result.baseline_iterations = int(statistics.mean(m.iterations for m in baseline_metrics_list))
        result.baseline_time = statistics.mean(baseline_times)

        # Run optimized (with Vercel patterns)
        print("\n[2/2] Running OPTIMIZED (with Vercel patterns)...")
        optimized_agent = self._create_optimized_agent()

        optimized_metrics_list = []
        optimized_times = []

        for i in range(self.iterations):
            print(f"  Iteration {i+1}/{self.iterations}...", end=" ", flush=True)
            optimized_agent.reset_used_tools()  # Reset for each iteration
            _, metrics, exec_time = await self._run_query_and_measure(
                optimized_agent, query
            )
            optimized_metrics_list.append(metrics)
            optimized_times.append(exec_time)
            print(f"Input: {metrics.input_tokens}, Output: {metrics.output_tokens}, Time: {exec_time:.2f}s")

        # Average optimized
        result.optimized_input = int(statistics.mean(m.input_tokens for m in optimized_metrics_list))
        result.optimized_output = int(statistics.mean(m.output_tokens for m in optimized_metrics_list))
        result.optimized_tools = int(statistics.mean(m.tool_calls for m in optimized_metrics_list))
        result.optimized_iterations = int(statistics.mean(m.iterations for m in optimized_metrics_list))
        result.optimized_time = statistics.mean(optimized_times)

        # Print comparison
        self._print_query_result(result)

        return result

    def _print_query_result(self, result: QueryBenchmarkResult):
        """Print detailed result for a single query."""
        print(f"\n{'-'*70}")
        print("RESULTS:")
        print(f"{'-'*70}")
        print(f"{'Metric':<30} {'Baseline':<15} {'Optimized':<15} {'Reduction':<15}")
        print(f"{'-'*70}")
        print(f"{'Input tokens':<30} {result.baseline_input:<15} {result.optimized_input:<15} {result.input_reduction_pct:>7.1f}%")
        print(f"{'Output tokens':<30} {result.baseline_output:<15} {result.optimized_output:<15} {result.output_reduction_pct:>7.1f}%")
        print(f"{'Total tokens':<30} {result.baseline_total:<15} {result.optimized_total:<15} {result.token_reduction_pct:>7.1f}%")
        print(f"{'Tool calls':<30} {result.baseline_tools:<15} {result.optimized_tools:<15}")
        print(f"{'Cost (USD)':<30} ${result.baseline_cost:<14.4f} ${result.optimized_cost:<14.4f} ${result.cost_savings:>7.4f}")
        print(f"{'Execution time (s)':<30} {result.baseline_time:<15.2f} {result.optimized_time:<15.2f} {result.time_diff_pct:>6.1f}%")
        print(f"{'-'*70}")

    def _print_summary(self, summary: BenchmarkSummary):
        """Print overall benchmark summary."""
        print("\n" + "="*80)
        print("TOKEN USAGE BENCHMARK SUMMARY - VERCEL OPTIMIZATIONS IMPACT")
        print("="*80)

        print(f"\nTest Date: {summary.timestamp}")
        print(f"Iterations per query: {summary.iterations_per_query}")
        print(f"Total queries: {len(summary.results)}")

        # Per-category breakdown
        categories = set(r.category for r in summary.results)
        print("\n" + "-"*80)
        print("PER-CATEGORY RESULTS:")
        print("-"*80)
        print(f"{'Category':<20} {'Queries':<10} {'Avg Tokens':<15} {'Reduction %':<15}")
        print("-"*80)

        for cat in sorted(categories):
            cat_results = [r for r in summary.results if r.category == cat]
            avg_baseline = statistics.mean(r.baseline_total for r in cat_results)
            avg_optimized = statistics.mean(r.optimized_total for r in cat_results)
            avg_reduction = ((avg_baseline - avg_optimized) / avg_baseline * 100) if avg_baseline > 0 else 0
            print(f"{cat:<20} {len(cat_results):<10} {avg_optimized:<15.0f} {avg_reduction:>7.1f}%")

        # Overall summary
        print("\n" + "-"*80)
        print("OVERALL SUMMARY:")
        print("-"*80)
        print(f"Total baseline tokens:     {summary.total_baseline_tokens:>12,}")
        print(f"Total optimized tokens:    {summary.total_optimized_tokens:>12,}")
        print(f"Total tokens saved:        {summary.total_tokens_saved:>12,}")
        print(f"Average reduction:         {summary.avg_token_reduction_pct:>12.1f}%")
        print(f"Average time impact:       {summary.avg_time_impact_pct:>12.1f}%")

        print("\n" + "-"*80)
        print("COST ANALYSIS:")
        print("-"*80)
        print(f"Total baseline cost:       ${summary.total_baseline_cost:>11.4f}")
        print(f"Total optimized cost:      ${summary.total_optimized_cost:>11.4f}")
        print(f"Total cost savings:        ${summary.total_cost_savings:>11.4f}")
        print(f"\nPer-query average:")
        print(f"  Baseline:                ${summary.total_baseline_cost/len(summary.results):>11.4f}")
        print(f"  Optimized:               ${summary.total_optimized_cost/len(summary.results):>11.4f}")
        print(f"  Savings:                 ${summary.total_cost_savings/len(summary.results):>11.4f}")

        print("\n" + "-"*80)
        print("PROJECTED MONTHLY SAVINGS (100 queries/day):")
        print("-"*80)
        print(f"Cost per query (baseline):   ${summary.total_baseline_cost/len(summary.results):>7.4f}")
        print(f"Cost per query (optimized):  ${summary.total_optimized_cost/len(summary.results):>7.4f}")
        print(f"Monthly baseline:            ${summary.total_baseline_cost/len(summary.results) * 100 * 30:>7.2f}")
        print(f"Monthly optimized:           ${summary.total_optimized_cost/len(summary.results) * 100 * 30:>7.2f}")
        print(f"Monthly savings:             ${summary.monthly_savings_100qpd:>7.2f}")

        # Top performers
        print("\n" + "-"*80)
        print("TOP TOKEN SAVERS:")
        print("-"*80)
        sorted_by_savings = sorted(summary.results, key=lambda r: r.token_reduction, reverse=True)
        for i, result in enumerate(sorted_by_savings[:5], 1):
            print(f"{i}. {result.query[:60]:<60} | {result.token_reduction_pct:>6.1f}% | {result.token_reduction:>6,} tokens")

        print("\n" + "="*80)

        # Compare with expected 58% reduction
        expected_reduction = 58.0
        actual_reduction = summary.avg_token_reduction_pct

        if actual_reduction >= expected_reduction * 0.9:  # Within 90% of target
            status = "✓ EXCELLENT"
        elif actual_reduction >= expected_reduction * 0.7:  # Within 70% of target
            status = "○ GOOD"
        else:
            status = "✗ BELOW TARGET"

        print(f"\nPERFORMANCE vs TARGET:")
        print(f"  Expected reduction:  {expected_reduction:>6.1f}%")
        print(f"  Actual reduction:    {actual_reduction:>6.1f}%")
        print(f"  Status:              {status}")
        print("="*80)

    async def run_all(self, export_path: Optional[str] = None):
        """Run all benchmarks."""
        print("\n" + "#"*80)
        print("# TOKEN USAGE COMPARISON BENCHMARK")
        print("# Measuring impact of Vercel optimization patterns")
        print("#"*80)
        print(f"\nData root: {self.data_root}")
        print(f"Iterations per query: {self.iterations}")
        print(f"Model: {self.settings.azure_openai_deployment_name}")

        summary = BenchmarkSummary(iterations_per_query=self.iterations)

        for query_spec in self.TEST_QUERIES:
            result = await self.benchmark_query(query_spec)
            summary.results.append(result)

            # Small delay between queries
            await asyncio.sleep(1)

        # Print summary
        self._print_summary(summary)

        # Export if requested
        if export_path:
            self._export_results(summary, export_path)
            print(f"\nResults exported to: {export_path}")

    def _export_results(self, summary: BenchmarkSummary, path: str):
        """Export results to JSON file."""
        data = {
            "summary": {
                "timestamp": summary.timestamp,
                "iterations_per_query": summary.iterations_per_query,
                "total_queries": len(summary.results),
                "total_baseline_tokens": summary.total_baseline_tokens,
                "total_optimized_tokens": summary.total_optimized_tokens,
                "total_tokens_saved": summary.total_tokens_saved,
                "avg_token_reduction_pct": summary.avg_token_reduction_pct,
                "total_baseline_cost": summary.total_baseline_cost,
                "total_optimized_cost": summary.total_optimized_cost,
                "total_cost_savings": summary.total_cost_savings,
                "monthly_savings_100qpd": summary.monthly_savings_100qpd,
                "avg_time_impact_pct": summary.avg_time_impact_pct,
            },
            "results": [
                {
                    "query": r.query,
                    "category": r.category,
                    "baseline_input": r.baseline_input,
                    "baseline_output": r.baseline_output,
                    "baseline_total": r.baseline_total,
                    "baseline_tools": r.baseline_tools,
                    "baseline_cost": r.baseline_cost,
                    "baseline_time": r.baseline_time,
                    "optimized_input": r.optimized_input,
                    "optimized_output": r.optimized_output,
                    "optimized_total": r.optimized_total,
                    "optimized_tools": r.optimized_tools,
                    "optimized_cost": r.optimized_cost,
                    "optimized_time": r.optimized_time,
                    "token_reduction": r.token_reduction,
                    "token_reduction_pct": r.token_reduction_pct,
                    "input_reduction_pct": r.input_reduction_pct,
                    "output_reduction_pct": r.output_reduction_pct,
                    "cost_savings": r.cost_savings,
                    "time_diff_pct": r.time_diff_pct,
                }
                for r in summary.results
            ]
        }

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark token usage impact of Vercel optimizations"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick benchmark (1 iteration)"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of iterations per query (default: 3)"
    )
    parser.add_argument(
        "--data-root",
        type=str,
        default="./data",
        help="Data root directory (default: ./data)"
    )
    parser.add_argument(
        "--export",
        type=str,
        help="Export results to JSON file"
    )

    args = parser.parse_args()

    iterations = 1 if args.quick else args.iterations

    benchmark = TokenUsageBenchmark(
        data_root=args.data_root,
        iterations=iterations
    )

    asyncio.run(benchmark.run_all(export_path=args.export))


if __name__ == "__main__":
    main()
