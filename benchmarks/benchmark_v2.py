#!/usr/bin/env python3
"""
Benchmark script for filesystem-agent-showcase v2.0 features.

Tests:
1. Parallel vs Sequential tool execution
2. Adaptive file reading strategies
3. Cache hit/miss performance
4. Streaming file reader throughput
5. Concurrent Operations at Scale
6. Chat API vs Chat Stream API comparison

Usage:
    poetry run python benchmarks/benchmark_v2.py
    poetry run python benchmarks/benchmark_v2.py --quick  # Fast mode
    poetry run python benchmarks/benchmark_v2.py --api    # Include API benchmarks (requires running server)
"""

import asyncio
import time
import statistics
import argparse
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Any, Optional

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sandbox.executor import SandboxExecutor
from app.sandbox.cached_executor import CachedSandboxExecutor
from app.agent.orchestrator import ParallelToolOrchestrator
from app.agent.tools.adaptive_reader import AdaptiveFileReader
from app.agent.tools.streaming import StreamingFileReader
from app.agent.tools.bash_tools import build_command
from app.agent.cache import ToolResultCache
from app.agent.filesystem_agent import ToolCall


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""
    name: str
    iterations: int
    times: list[float] = field(default_factory=list)

    @property
    def mean(self) -> float:
        return statistics.mean(self.times) if self.times else 0

    @property
    def median(self) -> float:
        return statistics.median(self.times) if self.times else 0

    @property
    def stdev(self) -> float:
        return statistics.stdev(self.times) if len(self.times) > 1 else 0

    @property
    def min_time(self) -> float:
        return min(self.times) if self.times else 0

    @property
    def max_time(self) -> float:
        return max(self.times) if self.times else 0

    def __str__(self) -> str:
        return (
            f"{self.name}:\n"
            f"  Iterations: {self.iterations}\n"
            f"  Mean: {self.mean*1000:.2f}ms\n"
            f"  Median: {self.median*1000:.2f}ms\n"
            f"  Std Dev: {self.stdev*1000:.2f}ms\n"
            f"  Min: {self.min_time*1000:.2f}ms\n"
            f"  Max: {self.max_time*1000:.2f}ms"
        )


@dataclass
class APIBenchmarkResult:
    """Result of an API benchmark run with streaming metrics."""
    name: str
    iterations: int
    total_times: list[float] = field(default_factory=list)
    ttft_times: list[float] = field(default_factory=list)  # Time to first token
    tool_call_counts: list[int] = field(default_factory=list)
    response_lengths: list[int] = field(default_factory=list)

    @property
    def mean_total(self) -> float:
        return statistics.mean(self.total_times) if self.total_times else 0

    @property
    def mean_ttft(self) -> float:
        return statistics.mean(self.ttft_times) if self.ttft_times else 0

    @property
    def median_total(self) -> float:
        return statistics.median(self.total_times) if self.total_times else 0

    @property
    def median_ttft(self) -> float:
        return statistics.median(self.ttft_times) if self.ttft_times else 0

    @property
    def avg_tool_calls(self) -> float:
        return statistics.mean(self.tool_call_counts) if self.tool_call_counts else 0

    @property
    def avg_response_length(self) -> float:
        return statistics.mean(self.response_lengths) if self.response_lengths else 0

    def __str__(self) -> str:
        ttft_str = f"  TTFT Mean: {self.mean_ttft*1000:.2f}ms\n" if self.ttft_times else ""
        ttft_median_str = f"  TTFT Median: {self.median_ttft*1000:.2f}ms\n" if self.ttft_times else ""
        return (
            f"{self.name}:\n"
            f"  Iterations: {self.iterations}\n"
            f"  Total Mean: {self.mean_total*1000:.2f}ms\n"
            f"  Total Median: {self.median_total*1000:.2f}ms\n"
            f"{ttft_str}"
            f"{ttft_median_str}"
            f"  Avg Tool Calls: {self.avg_tool_calls:.1f}\n"
            f"  Avg Response Length: {self.avg_response_length:.0f} chars"
        )


class Benchmark:
    """Benchmark runner for v2.0 features."""

    def __init__(self, data_root: str = "./data", iterations: int = 5):
        self.data_root = Path(data_root).resolve()
        self.iterations = iterations
        self.results: list[BenchmarkResult] = []

        # Initialize components
        self.sandbox = SandboxExecutor(self.data_root)
        self.cached_sandbox = CachedSandboxExecutor(
            self.data_root,
            cache_enabled=True,
            cache_ttl=300,
            cache_max_size=100
        )
        self.orchestrator = ParallelToolOrchestrator(self.sandbox, max_concurrent=5)
        self.adaptive_reader = AdaptiveFileReader(self.sandbox)
        self.streaming_reader = StreamingFileReader()

    async def run_async(self, name: str, func: Callable[[], Any]) -> BenchmarkResult:
        """Run an asynchronous benchmark."""
        result = BenchmarkResult(name=name, iterations=self.iterations)

        # Warmup
        await func()

        for _ in range(self.iterations):
            start = time.perf_counter()
            await func()
            result.times.append(time.perf_counter() - start)

        self.results.append(result)
        return result

    # ==========================================================================
    # Benchmark 1: Parallel vs Sequential Tool Execution
    # ==========================================================================

    async def benchmark_parallel_vs_sequential(self):
        """Compare parallel vs sequential tool execution."""
        print("\n" + "="*60)
        print("BENCHMARK 1: Parallel vs Sequential Tool Execution")
        print("="*60)

        # Define multiple tool calls (grep across multiple files)
        tool_calls = [
            ToolCall(id="1", name="grep", arguments={"pattern": "learning", "path": "benchmark"}),
            ToolCall(id="2", name="grep", arguments={"pattern": "model", "path": "benchmark"}),
            ToolCall(id="3", name="grep", arguments={"pattern": "neural", "path": "benchmark"}),
            ToolCall(id="4", name="find", arguments={"path": "benchmark", "name_pattern": "*.json"}),
            ToolCall(id="5", name="find", arguments={"path": "benchmark", "name_pattern": "*.md"}),
        ]

        # Sequential execution
        async def run_sequential():
            results = []
            for tc in tool_calls:
                cmd = build_command(tc.name, tc.arguments)
                result = await self.sandbox.execute(cmd)
                results.append(result)
            return results

        # Parallel execution
        async def run_parallel():
            return await self.orchestrator.execute_with_strategy(tool_calls)

        seq_result = await self.run_async("Sequential (5 tools)", run_sequential)
        par_result = await self.run_async("Parallel (5 tools)", run_parallel)

        speedup = seq_result.mean / par_result.mean if par_result.mean > 0 else 0

        print(f"\n{seq_result}")
        print(f"\n{par_result}")
        print(f"\n>>> Speedup: {speedup:.2f}x faster with parallel execution")

        return speedup

    # ==========================================================================
    # Benchmark 2: Cache Performance
    # ==========================================================================

    async def benchmark_cache_performance(self):
        """Compare cached vs uncached execution."""
        print("\n" + "="*60)
        print("BENCHMARK 2: Cache Performance")
        print("="*60)

        # Clear cache first
        self.cached_sandbox.clear_cache()

        cmd = build_command("grep", {"pattern": "transformer", "path": "benchmark"})

        # First run - cache miss (use fresh executor each time)
        async def run_uncached():
            sandbox = SandboxExecutor(self.data_root)
            return await sandbox.execute(cmd)

        # Cached run - cache hit after first call
        async def run_cached_hit():
            # Don't clear cache - should hit
            return await self.cached_sandbox.execute(cmd)

        uncached_result = await self.run_async("Uncached grep", run_uncached)

        # Prime the cache
        self.cached_sandbox.clear_cache()
        await self.cached_sandbox.execute(cmd)

        cached_result = await self.run_async("Cached grep (hit)", run_cached_hit)

        speedup = uncached_result.mean / cached_result.mean if cached_result.mean > 0 else 0

        stats = self.cached_sandbox.cache_stats()

        print(f"\n{uncached_result}")
        print(f"\n{cached_result}")
        print(f"\nCache Stats: {stats}")
        print(f"\n>>> Speedup: {speedup:.2f}x faster with cache hit")

        return speedup

    # ==========================================================================
    # Benchmark 3: Adaptive File Reading
    # ==========================================================================

    async def benchmark_adaptive_reading(self):
        """Test adaptive file reading strategies."""
        print("\n" + "="*60)
        print("BENCHMARK 3: Adaptive File Reading Strategies")
        print("="*60)

        # Find different sized files
        small_file = self.data_root / "benchmark" / "report.md"
        medium_file = self.data_root / "benchmark" / "arxiv-100-papers" / "metadata.jsonl"

        if not small_file.exists():
            print(f"Warning: {small_file} not found, skipping")
            return

        # Small file - full read
        async def read_small():
            return await self.adaptive_reader.smart_read(Path("benchmark/report.md"))

        # Medium file with query - grep strategy
        async def read_medium_with_query():
            return await self.adaptive_reader.smart_read(
                Path("benchmark/arxiv-100-papers/metadata.jsonl"),
                query="learning"
            )

        small_result = await self.run_async("Small file (full_read)", read_small)

        if medium_file.exists():
            medium_result = await self.run_async("Medium file (grep)", read_medium_with_query)
            print(f"\n{small_result}")
            print(f"\n{medium_result}")
        else:
            print(f"\n{small_result}")
            print("Medium file not found, skipping grep benchmark")

        # Show file info
        info = await self.adaptive_reader.get_file_info(Path("benchmark/report.md"))
        print(f"\nFile info for report.md: {info}")

    # ==========================================================================
    # Benchmark 4: Streaming File Reader
    # ==========================================================================

    async def benchmark_streaming(self):
        """Test streaming file reader performance."""
        print("\n" + "="*60)
        print("BENCHMARK 4: Streaming File Reader")
        print("="*60)

        target_file = "benchmark/arxiv-100-papers/metadata.jsonl"
        full_path = self.data_root / target_file

        if not full_path.exists():
            print(f"Warning: {full_path} not found, skipping")
            return

        cmd = build_command("cat", {"path": target_file})

        # Full read with cat
        async def read_with_cat():
            return await self.sandbox.execute(cmd)

        # Streaming read
        async def read_with_streaming():
            content = []
            async for chunk in self.streaming_reader.read_chunks(full_path):
                content.append(chunk)
            return "".join(content)

        cat_result = await self.run_async("cat (full read)", read_with_cat)
        stream_result = await self.run_async("Streaming (8KB chunks)", read_with_streaming)

        print(f"\n{cat_result}")
        print(f"\n{stream_result}")

        # Test search in large file
        async def search_streaming():
            matches = await self.streaming_reader.search_in_large_file(full_path, "learning", max_matches=10)
            return matches

        search_result = await self.run_async("Streaming search", search_streaming)
        print(f"\n{search_result}")

    # ==========================================================================
    # Benchmark 5: Concurrent Operations at Scale
    # ==========================================================================

    async def benchmark_scale(self):
        """Test performance at scale with many concurrent operations."""
        print("\n" + "="*60)
        print("BENCHMARK 5: Concurrent Operations at Scale")
        print("="*60)

        # Create 10 tool calls
        patterns = ["learning", "model", "neural", "data", "training",
                   "network", "deep", "algorithm", "optimization", "loss"]

        tool_calls = [
            ToolCall(id=str(i), name="grep", arguments={"pattern": p, "path": "benchmark"})
            for i, p in enumerate(patterns)
        ]

        # Sequential
        async def run_10_sequential():
            results = []
            for tc in tool_calls:
                cmd = build_command(tc.name, tc.arguments)
                result = await self.sandbox.execute(cmd)
                results.append(result)
            return results

        # Parallel with different concurrency limits
        async def run_10_parallel_3():
            orch = ParallelToolOrchestrator(self.sandbox, max_concurrent=3)
            return await orch.execute_with_strategy(tool_calls)

        async def run_10_parallel_5():
            orch = ParallelToolOrchestrator(self.sandbox, max_concurrent=5)
            return await orch.execute_with_strategy(tool_calls)

        async def run_10_parallel_10():
            orch = ParallelToolOrchestrator(self.sandbox, max_concurrent=10)
            return await orch.execute_with_strategy(tool_calls)

        seq_result = await self.run_async("Sequential (10 greps)", run_10_sequential)
        par3_result = await self.run_async("Parallel max=3 (10 greps)", run_10_parallel_3)
        par5_result = await self.run_async("Parallel max=5 (10 greps)", run_10_parallel_5)
        par10_result = await self.run_async("Parallel max=10 (10 greps)", run_10_parallel_10)

        print(f"\n{seq_result}")
        print(f"\n{par3_result}")
        print(f"\n{par5_result}")
        print(f"\n{par10_result}")

        print(f"\n>>> Speedup (max=3): {seq_result.mean/par3_result.mean:.2f}x")
        print(f">>> Speedup (max=5): {seq_result.mean/par5_result.mean:.2f}x")
        print(f">>> Speedup (max=10): {seq_result.mean/par10_result.mean:.2f}x")

    # ==========================================================================
    # Benchmark 6: Chat API vs Chat Stream API
    # ==========================================================================

    async def benchmark_chat_api_comparison(self, base_url: str = "http://localhost:8000"):
        """Compare /api/chat vs /api/chat/stream endpoints."""
        if not HTTPX_AVAILABLE:
            print("\n" + "="*60)
            print("BENCHMARK 6: Chat API vs Chat Stream API")
            print("="*60)
            print("SKIPPED: httpx not installed. Run: pip install httpx")
            return None

        print("\n" + "="*60)
        print("BENCHMARK 6: Chat API vs Chat Stream API")
        print("="*60)

        # Test queries with different complexity
        test_queries = [
            ("Simple listing", "List files in projects folder"),
            ("Search pattern", "Find all markdown files"),
            ("Complex search", "Search for TODO comments in all files"),
            ("File read", "Show content of knowledge-base/faqs/developer-faq.md"),
            ("Multi-tool", "Find all JSON files and count how many there are"),
        ]

        api_results: list[APIBenchmarkResult] = []

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Check if server is running
            try:
                await client.get(f"{base_url}/health")
            except httpx.ConnectError:
                print(f"\nERROR: Cannot connect to {base_url}")
                print("Please start the server first: make dev")
                return None

            for query_name, query in test_queries:
                print(f"\n--- {query_name} ---")

                # Benchmark non-streaming endpoint
                chat_result = APIBenchmarkResult(
                    name=f"/api/chat - {query_name}",
                    iterations=self.iterations
                )

                # Benchmark streaming endpoint
                stream_result = APIBenchmarkResult(
                    name=f"/api/chat/stream - {query_name}",
                    iterations=self.iterations
                )

                for i in range(self.iterations):
                    # Test /api/chat (non-streaming)
                    start = time.perf_counter()
                    response = await client.post(
                        f"{base_url}/api/chat",
                        json={"message": query}
                    )
                    total_time = time.perf_counter() - start

                    if response.status_code == 200:
                        data = response.json()
                        chat_result.total_times.append(total_time)
                        chat_result.tool_call_counts.append(len(data.get("tool_calls", [])))
                        chat_result.response_lengths.append(len(data.get("response", "")))

                    # Test /api/chat/stream (streaming)
                    start = time.perf_counter()
                    ttft = None
                    tool_calls_count = 0
                    final_message = ""

                    async with client.stream(
                        "POST",
                        f"{base_url}/api/chat/stream",
                        json={"message": query}
                    ) as stream_response:
                        async for line in stream_response.aiter_lines():
                            if ttft is None and line.startswith("data:"):
                                ttft = time.perf_counter() - start

                            if line.startswith("data:"):
                                try:
                                    data_str = line[5:].strip()
                                    if data_str:
                                        event_data = json.loads(data_str)
                                        if "tool_calls_count" in event_data:
                                            tool_calls_count = event_data["tool_calls_count"]
                                            final_message = event_data.get("message", "")
                                except json.JSONDecodeError:
                                    pass

                    total_time = time.perf_counter() - start

                    stream_result.total_times.append(total_time)
                    if ttft:
                        stream_result.ttft_times.append(ttft)
                    stream_result.tool_call_counts.append(tool_calls_count)
                    stream_result.response_lengths.append(len(final_message))

                api_results.extend([chat_result, stream_result])

                print(f"\n{chat_result}")
                print(f"\n{stream_result}")

                # Comparison
                if chat_result.mean_total > 0 and stream_result.mean_total > 0:
                    total_diff = ((stream_result.mean_total - chat_result.mean_total) / chat_result.mean_total) * 100
                    print(f"\n>>> Total time difference: {total_diff:+.1f}%")
                    if stream_result.mean_ttft > 0:
                        ttft_vs_total = (stream_result.mean_ttft / chat_result.mean_total) * 100
                        print(f">>> TTFT is {ttft_vs_total:.1f}% of non-streaming total time")

        # Summary table
        print("\n" + "="*60)
        print("CHAT API COMPARISON SUMMARY")
        print("="*60)
        print(f"{'Query':<20} {'Chat (ms)':<12} {'Stream (ms)':<12} {'TTFT (ms)':<12} {'Diff %':<10}")
        print("-" * 66)

        for i in range(0, len(api_results), 2):
            chat_r = api_results[i]
            stream_r = api_results[i + 1]
            query_name = chat_r.name.replace("/api/chat - ", "")
            diff = ((stream_r.mean_total - chat_r.mean_total) / chat_r.mean_total * 100) if chat_r.mean_total > 0 else 0
            ttft_str = f"{stream_r.mean_ttft*1000:.0f}" if stream_r.mean_ttft > 0 else "N/A"
            print(f"{query_name:<20} {chat_r.mean_total*1000:<12.0f} {stream_r.mean_total*1000:<12.0f} {ttft_str:<12} {diff:+.1f}%")

        return api_results

    # ==========================================================================
    # Run All Benchmarks
    # ==========================================================================

    async def run_all(self, quick: bool = False, include_api: bool = False, api_url: str = "http://localhost:8000"):
        """Run all benchmarks."""
        if quick:
            self.iterations = 3

        print("\n" + "#"*60)
        print("# FILESYSTEM AGENT SHOWCASE v2.0 - BENCHMARK SUITE")
        print(f"# Data root: {self.data_root}")
        print(f"# Iterations: {self.iterations}")
        print("#"*60)

        await self.benchmark_parallel_vs_sequential()
        await self.benchmark_cache_performance()
        await self.benchmark_adaptive_reading()
        await self.benchmark_streaming()
        await self.benchmark_scale()

        if include_api:
            await self.benchmark_chat_api_comparison(api_url)

        # Summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        for result in self.results:
            print(f"  {result.name}: {result.mean*1000:.2f}ms (median: {result.median*1000:.2f}ms)")


def main():
    parser = argparse.ArgumentParser(description="Benchmark v2.0 features")
    parser.add_argument("--quick", action="store_true", help="Run quick benchmark (3 iterations)")
    parser.add_argument("--iterations", type=int, default=5, help="Number of iterations")
    parser.add_argument("--data-root", type=str, default="./data", help="Data root directory")
    parser.add_argument("--api", action="store_true", help="Include API endpoint benchmarks (requires running server)")
    parser.add_argument("--api-only", action="store_true", help="Only run API endpoint benchmarks")
    parser.add_argument("--api-url", type=str, default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()

    benchmark = Benchmark(
        data_root=args.data_root,
        iterations=args.iterations if not args.quick else 3
    )

    if args.api_only:
        # Only run API benchmarks
        asyncio.run(benchmark.benchmark_chat_api_comparison(args.api_url))
    else:
        asyncio.run(benchmark.run_all(
            quick=args.quick,
            include_api=args.api,
            api_url=args.api_url
        ))


if __name__ == "__main__":
    main()
