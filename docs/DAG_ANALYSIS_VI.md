# Phân Tích Directed Acyclic Graph (DAG) Cho Dự Án Filesystem Agent

## 📋 Mục Lục

1. [Tổng Quan Về DAG](#1-tổng-quan-về-dag)
2. [DAG Trong Hệ Thống AI Agent](#2-dag-trong-hệ-thống-ai-agent)
3. [Phân Tích Kiến Trúc Hiện Tại](#3-phân-tích-kiến-trúc-hiện-tại)
4. [Cơ Hội Áp Dụng DAG](#4-cơ-hội-áp-dụng-dag)
5. [Đề Xuất Kiến Trúc DAG](#5-đề-xuất-kiến-trúc-dag)
6. [Roadmap Triển Khai](#6-roadmap-triển-khai)
7. [So Sánh Với LangGraph](#7-so-sánh-với-langgraph)

---

## 1. Tổng Quan Về DAG

### 1.1 Định Nghĩa

**Directed Acyclic Graph (Đồ Thị Có Hướng Không Chu Trình)** là một cấu trúc dữ liệu đồ thị với các đặc điểm:

- **Directed (Có hướng)**: Các cạnh có hướng từ node này sang node khác (A → B)
- **Acyclic (Không chu trình)**: Không tồn tại đường đi quay trở lại chính nó
- **Graph (Đồ thị)**: Tập hợp các nodes (đỉnh) và edges (cạnh)

```
        A
       ↙ ↘
      B   C
       ↘ ↙
        D
```

### 1.2 Ưu Điểm Của DAG

#### a) Tính Xác Định (Deterministic)
- Không có vòng lặp vô hạn
- Luôn có thể sắp xếp thứ tự thực thi (topological sort)
- Dễ debug và trace execution flow

#### b) Tối Ưu Hóa
- **Parallel Execution**: Các node độc lập có thể chạy song song
- **Dependency Management**: Quản lý dependencies rõ ràng
- **Caching**: Cache kết quả của từng node, tái sử dụng khi dependencies không đổi

#### c) Khả Năng Mở Rộng
- Dễ thêm/xóa nodes mà không ảnh hưởng toàn bộ hệ thống
- Có thể visualize workflow một cách trực quan
- Hỗ trợ conditional branching và error handling

### 1.3 Ứng Dụng Thực Tế

| Lĩnh Vực | Ví Dụ |
|----------|-------|
| **Data Engineering** | Apache Airflow, Luigi, Prefect - Quản lý data pipelines |
| **Build Systems** | Makefile, Gradle, Bazel - Quản lý build dependencies |
| **Blockchain** | Bitcoin, Ethereum - Transaction ordering |
| **AI/ML** | TensorFlow, PyTorch - Computational graphs |
| **Package Management** | npm, pip, apt - Dependency resolution |
| **CI/CD** | GitHub Actions, GitLab CI - Pipeline execution |

---

## 2. DAG Trong Hệ Thống AI Agent

### 2.1 Xu Hướng Năm 2025-2026

Theo nghiên cứu mới nhất (2026), DAG đang trở thành **backbone** của các hệ thống Multi-Agent AI:

#### a) LangGraph (LangChain Ecosystem)
```python
from langgraph.graph import Graph

# Define workflow as DAG
workflow = Graph()
workflow.add_node("research", research_agent)
workflow.add_node("analyze", analysis_agent)
workflow.add_node("synthesize", synthesis_agent)

# Define edges (dependencies)
workflow.add_edge("research", "analyze")
workflow.add_edge("analyze", "synthesize")
workflow.set_entry_point("research")
```

**Đặc điểm:**
- Hỗ trợ **cycles** (khác với DAG thuần túy) để tạo agent-like behaviors
- Lowest latency trong các agentic frameworks (benchmark 2026)
- Declarative architecture với static tool assignments

#### b) DAGent Framework
```python
from dagent import DAGAgent, Task

# Define tasks as nodes
task1 = Task("search", search_tool)
task2 = Task("analyze", analyze_tool, dependencies=[task1])
task3 = Task("report", report_tool, dependencies=[task2])

# Create DAG
agent = DAGAgent([task1, task2, task3])
result = await agent.execute()
```

**Đặc điểm:**
- Pure DAG approach (không có cycles)
- Support parallel và conditional execution
- DAG visualization built-in

#### c) Adaptive Multi-Agent Systems (2025+)
- **Dynamic DAG Restructuring**: DAG tự động thay đổi dựa trên runtime information
- **Resilience**: Xử lý unpredictable scenarios bằng cách thay đổi graph structure
- **Real-time Optimization**: Điều chỉnh execution path dựa trên performance metrics

### 2.2 Lợi Ích Của DAG Cho AI Agents

#### a) Tránh Infinite Loops
```
❌ Without DAG:
Agent → Tool A → Agent → Tool A → Agent → Tool A ... (infinite loop)

✅ With DAG:
Agent → [Tool A → Tool B → Tool C] → Final Response (max depth enforced)
```

#### b) Optimized Execution
```python
# Sequential (current approach)
result1 = await execute_tool("grep pattern1 file1")  # 2s
result2 = await execute_tool("grep pattern2 file2")  # 2s
result3 = await execute_tool("grep pattern3 file3")  # 2s
# Total: 6s

# DAG Parallel (proposed)
results = await execute_dag_parallel([
    Node("grep1", depends_on=[]),
    Node("grep2", depends_on=[]),
    Node("grep3", depends_on=[]),
])
# Total: 2s (3x faster)
```

#### c) Dependency Management
```
find_files → grep_in_files → count_matches → generate_report
     ↓
  cat_file
```

---

## 3. Phân Tích Kiến Trúc Hiện Tại

### 3.1 Agent Execution Flow

**File**: `app/agent/filesystem_agent.py`

```
┌─────────────────────────────────────────────────────────────┐
│                      FilesystemAgent                         │
│                                                              │
│  chat() method - Agent Loop (max 10 iterations):            │
│                                                              │
│  1. User Message → LLM                                       │
│  2. LLM returns tool_calls                                   │
│  3. Execute tools (sequential or parallel)                   │
│  4. Feed results back to LLM                                 │
│  5. Repeat until LLM returns final response                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              ParallelToolOrchestrator                        │
│                                                              │
│  - analyze_dependencies(): Phân loại READ vs WRITE tools    │
│  - execute_parallel(): Chạy read-only tools đồng thời       │
│  - execute_sequential(): Chạy write tools tuần tự           │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                   SandboxExecutor                            │
│                                                              │
│  - Whitelist commands (grep, find, cat, head, tail, ls, wc) │
│  - Path confinement (security)                               │
│  - Timeout protection                                        │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Current Limitations

#### a) Limited Dependency Awareness
```python
# orchestrator.py:197
def analyze_dependencies(self, tool_calls):
    # Chỉ phân biệt READ vs WRITE
    # Không hiểu dependencies giữa các tools
    if tc.name in READ_ONLY_TOOLS:
        read_only_calls.append(tc)
    elif tc.name in WRITE_TOOLS:
        write_calls.append(tc)
```

**Vấn đề:**
- Tool B cần kết quả của Tool A nhưng vẫn chạy parallel
- Không tối ưu cho workflows phức tạp

**Ví dụ:**
```python
# Scenario: Find Python files then grep them
tool_calls = [
    ToolCall("find", {"path": ".", "name_pattern": "*.py"}),
    ToolCall("grep", {"pattern": "import", "path": "result_from_find"})  # ❌ Depends on find!
]
# Hiện tại: Chạy song song → grep fails vì chưa có result
# Lý tưởng: Chạy find trước, sau đó grep
```

#### b) No Built-in Workflow Visualization
- Khó debug khi có nhiều tool calls
- Không thể visualize execution flow
- Hard to explain to users what the agent is doing

#### c) Fixed Iteration Limit
```python
# filesystem_agent.py:466
for iteration in range(self.max_tool_iterations):  # max 10 iterations
```

**Vấn đề:**
- Có thể dừng giữa chừng nếu workflow phức tạp
- Không có dynamic adjustment based on complexity

### 3.3 Existing Parallelization

**File**: `app/agent/orchestrator.py`

```python
class ParallelToolOrchestrator:
    async def execute_parallel(self, tool_calls):
        """Execute multiple tool calls in parallel using asyncio.gather."""
        tasks = [self.execute_tool_with_semaphore(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
```

**Ưu điểm hiện tại:**
- ✅ Semaphore limiting (max_concurrent=5)
- ✅ Exception handling
- ✅ Read-only tool detection

**Hạn chế:**
- ❌ No fine-grained dependency tracking
- ❌ All-or-nothing parallelization (either all parallel or all sequential)
- ❌ No partial ordering

---

## 4. Cơ Hội Áp Dụng DAG

### 4.1 Use Case 1: Tool Execution DAG

#### Vấn Đề Hiện Tại
```python
# Agent receives complex query:
"Find all Python files, count lines in each, and list files with > 100 lines"

# LLM generates tool calls:
[
    find(".", "*.py"),        # Must run first
    cat("file1.py"),          # Depends on find result
    wc("file1.py"),           # Depends on find result
    cat("file2.py"),          # Depends on find result
    wc("file2.py"),           # Depends on find result
    grep(">100", "wc_results") # Depends on all wc results
]

# Current execution: Sequential or all-parallel (not optimal)
```

#### Giải Pháp DAG
```
                   find(*.py)
                       ↓
        ┌──────────────┼──────────────┐
        ↓              ↓               ↓
    wc(file1)      wc(file2)      wc(file3)    ← Parallel layer
        ↓              ↓               ↓
        └──────────────┼───────────────┘
                       ↓
                 aggregate_results            ← Final node
```

**Performance gain:**
- Sequential: `T_find + 3*(T_wc) = 0.5s + 3*1s = 3.5s`
- DAG: `T_find + max(T_wc) = 0.5s + 1s = 1.5s` **(2.3x faster)**

### 4.2 Use Case 2: Cache Invalidation DAG

#### Vấn Đề Hiện Tại

**File**: `app/cache/cache_manager.py`

```python
# When file changes:
# 1. ContentCache invalidation
# 2. SearchCache invalidation (if file is in scope)
# 3. FileStateTracker update

# But: No explicit dependency graph!
```

**Vấn đề:**
- Khi `data/project/module.py` thay đổi:
  - Invalidate content cache cho `module.py` ✓
  - Invalidate search cache cho `grep "import" data/project/` ✓
  - Nhưng có cần invalidate `grep "import" data/`? → **Dependency graph unclear**

#### Giải Pháp DAG

```python
# Cache Invalidation DAG
class CacheInvalidationDAG:
    """
    Track cache dependencies as a DAG.

    Example:
        search_cache("grep import data/")
            ↓ depends_on
        [content("data/a.py"), content("data/b.py"), content("data/sub/c.py")]
            ↓ depends_on
        [file_state("data/a.py"), file_state("data/b.py"), ...]
    """
```

**Khi file thay đổi:**
```
file_state("data/a.py") changed
    ↓ invalidates
content_cache("data/a.py")
    ↓ invalidates
search_cache("grep import data/")
    ↓ invalidates
search_cache("grep import data/project/")
```

**Benefits:**
- **Precise invalidation**: Chỉ invalidate những gì cần thiết
- **Dependency tracking**: Biết search nào phụ thuộc vào file nào
- **Performance**: Tránh over-invalidation

### 4.3 Use Case 3: Multi-Stage Agent Workflow

#### Scenario: Complex Analysis Task

```
User: "Analyze this codebase: find all TODO comments, categorize by severity,
       and generate a priority report"
```

**Traditional approach (current):**
```python
# 10 iterations of LLM back-and-forth
iter1: LLM decides to grep "TODO"
iter2: LLM sees results, decides to categorize
iter3: LLM asks for more context
...
iter10: Finally generates report (or hits limit)
```

**DAG approach:**
```
                    Analyze Request
                          ↓
                ┌─────────┴─────────┐
                ↓                   ↓
        Find TODOs            Extract Context
           (grep)                (cat files)
                ↓                   ↓
                └─────────┬─────────┘
                          ↓
                  Categorize by Pattern
                    (regex + LLM)
                          ↓
                    ┌─────┴─────┐
                    ↓           ↓
            High Priority   Low Priority
                    ↓           ↓
                    └─────┬─────┘
                          ↓
                  Generate Report
```

**Benefits:**
- **Fewer LLM calls**: 3-4 instead of 10 (cost reduction)
- **Faster execution**: Parallel branches
- **More predictable**: Pre-defined workflow structure

### 4.4 Use Case 4: Dynamic Tool Planning

#### Concept: LLM-Generated DAG

```python
class DynamicDAGPlanner:
    """
    Ask LLM to generate a DAG plan before executing tools.

    Flow:
    1. User query → LLM
    2. LLM generates DAG plan (JSON)
    3. Validate DAG (acyclic, tools exist)
    4. Execute DAG with optimal parallelization
    5. Return results
    """

    async def plan(self, query: str) -> DAG:
        response = await self.llm.chat(f"""
        Create an execution plan as a DAG for this query: {query}

        Return JSON:
        {{
            "nodes": [
                {{"id": "1", "tool": "find", "args": {{"pattern": "*.py"}}}},
                {{"id": "2", "tool": "grep", "args": {{"pattern": "TODO"}}, "depends_on": ["1"]}}
            ]
        }}
        """)
        return DAG.from_json(response)
```

**Example:**

```json
{
  "query": "Find large Python files and analyze imports",
  "dag": {
    "nodes": [
      {
        "id": "find_files",
        "tool": "find",
        "args": {"path": ".", "name_pattern": "*.py"}
      },
      {
        "id": "check_size",
        "tool": "wc",
        "args": {"files": "$find_files.output"},
        "depends_on": ["find_files"]
      },
      {
        "id": "filter_large",
        "tool": "filter",
        "args": {"threshold": 100},
        "depends_on": ["check_size"]
      },
      {
        "id": "analyze_imports",
        "tool": "grep",
        "args": {"pattern": "^import|^from", "files": "$filter_large.output"},
        "depends_on": ["filter_large"]
      }
    ]
  }
}
```

---

## 5. Đề Xuất Kiến Trúc DAG

### 5.1 Core Components

```
┌────────────────────────────────────────────────────────────────┐
│                      FilesystemAgent                            │
│                                                                 │
│  - chat(): Entry point                                          │
│  - chat_stream(): Streaming variant                            │
│  - get_cache_stats(): Monitoring                               │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                       DAGPlanner (NEW)                          │
│                                                                 │
│  - analyze_query(): Understand user intent                     │
│  - generate_dag(): Create execution plan as DAG               │
│  - optimize_dag(): Apply optimizations (merge, prune)         │
│  - validate_dag(): Check for cycles, invalid tools            │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                       DAGExecutor (NEW)                         │
│                                                                 │
│  - topological_sort(): Order nodes for execution              │
│  - execute_dag(): Run DAG with optimal parallelization        │
│  - handle_errors(): Error recovery and retries                │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                 ParallelToolOrchestrator (Enhanced)            │
│                                                                 │
│  - execute_layer(): Execute one layer of DAG in parallel      │
│  - dependency_check(): Verify dependencies satisfied          │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                      CacheManager (Enhanced)                    │
│                                                                 │
│  - dag_aware_cache: Cache with DAG dependencies               │
│  - invalidate_dag(): Propagate invalidation through DAG       │
└────────────────────────────────────────────────────────────────┘
```

### 5.2 DAG Data Structure

```python
# app/agent/dag.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum

class NodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class DAGNode:
    """
    A node in the execution DAG.

    Attributes:
        id: Unique identifier for the node
        tool_name: Name of the tool to execute (grep, find, cat, etc.)
        arguments: Arguments to pass to the tool
        depends_on: List of node IDs that must complete before this node
        status: Current execution status
        result: Execution result (populated after completion)
        error: Error information (if failed)
    """
    id: str
    tool_name: str
    arguments: Dict[str, Any]
    depends_on: List[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None

    def is_ready(self, completed_nodes: set[str]) -> bool:
        """Check if all dependencies are satisfied."""
        return all(dep in completed_nodes for dep in self.depends_on)

    def can_run_parallel_with(self, other: "DAGNode") -> bool:
        """Check if this node can run in parallel with another node."""
        # Can't run parallel if there's a dependency relationship
        if other.id in self.depends_on or self.id in other.depends_on:
            return False

        # Can't run parallel if they share a dependency that modifies state
        # (current implementation assumes all tools are read-only)
        return True

@dataclass
class ExecutionDAG:
    """
    Directed Acyclic Graph for tool execution.

    Attributes:
        nodes: Dictionary of node_id -> DAGNode
        entry_points: Nodes with no dependencies (start here)
        exit_points: Nodes with no dependents (final results)
    """
    nodes: Dict[str, DAGNode] = field(default_factory=dict)
    entry_points: List[str] = field(default_factory=list)
    exit_points: List[str] = field(default_factory=list)

    def add_node(self, node: DAGNode) -> None:
        """Add a node to the DAG."""
        self.nodes[node.id] = node

        # Update entry/exit points
        if not node.depends_on:
            self.entry_points.append(node.id)

        # Update exit points (nodes with no dependents)
        self._update_exit_points()

    def add_edge(self, from_id: str, to_id: str) -> None:
        """Add a dependency edge from one node to another."""
        if to_id not in self.nodes:
            raise ValueError(f"Node {to_id} not found")

        self.nodes[to_id].depends_on.append(from_id)
        self._update_exit_points()

    def validate(self) -> tuple[bool, Optional[str]]:
        """
        Validate the DAG structure.

        Returns:
            (is_valid, error_message)
        """
        # Check for cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)

            # Check all dependencies
            node = self.nodes[node_id]
            for dep_id in node.depends_on:
                if dep_id not in self.nodes:
                    return True  # Invalid dependency

                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    return True  # Cycle detected

            rec_stack.remove(node_id)
            return False

        for node_id in self.nodes:
            if node_id not in visited:
                if has_cycle(node_id):
                    return False, f"Cycle detected involving node {node_id}"

        return True, None

    def topological_sort(self) -> List[List[str]]:
        """
        Return nodes in topological order, grouped by execution layers.

        Nodes in the same layer can be executed in parallel.

        Returns:
            List of layers, where each layer is a list of node IDs

        Example:
            [
                ["find_files"],                    # Layer 0: entry points
                ["wc_file1", "wc_file2", "wc_file3"],  # Layer 1: parallel
                ["aggregate_results"]              # Layer 2: final
            ]
        """
        # Calculate in-degree for each node
        in_degree = {node_id: len(node.depends_on) for node_id, node in self.nodes.items()}

        layers = []
        completed = set()

        while len(completed) < len(self.nodes):
            # Find all nodes with in-degree 0 (ready to execute)
            current_layer = [
                node_id for node_id, degree in in_degree.items()
                if degree == 0 and node_id not in completed
            ]

            if not current_layer:
                # No nodes ready -> there must be a cycle (shouldn't happen after validation)
                raise ValueError("DAG has a cycle or is invalid")

            layers.append(current_layer)

            # Mark nodes as completed and update in-degrees
            for node_id in current_layer:
                completed.add(node_id)

                # Decrease in-degree for dependent nodes
                for other_id, other_node in self.nodes.items():
                    if node_id in other_node.depends_on:
                        in_degree[other_id] -= 1

        return layers

    def get_execution_plan(self) -> Dict[str, Any]:
        """
        Generate a human-readable execution plan.

        Returns:
            Dictionary with execution plan details
        """
        layers = self.topological_sort()

        return {
            "total_nodes": len(self.nodes),
            "total_layers": len(layers),
            "max_parallelism": max(len(layer) for layer in layers),
            "layers": [
                {
                    "layer_id": i,
                    "node_count": len(layer),
                    "nodes": [
                        {
                            "id": node_id,
                            "tool": self.nodes[node_id].tool_name,
                            "depends_on": self.nodes[node_id].depends_on,
                        }
                        for node_id in layer
                    ]
                }
                for i, layer in enumerate(layers)
            ]
        }

    def _update_exit_points(self) -> None:
        """Update the list of exit points (nodes with no dependents)."""
        dependents = set()
        for node in self.nodes.values():
            dependents.update(node.depends_on)

        self.exit_points = [
            node_id for node_id in self.nodes
            if node_id not in dependents
        ]

    def visualize(self) -> str:
        """
        Generate a text-based visualization of the DAG.

        Returns:
            ASCII art representation of the DAG
        """
        layers = self.topological_sort()

        lines = []
        lines.append("Execution DAG:")
        lines.append("=" * 60)

        for i, layer in enumerate(layers):
            lines.append(f"\nLayer {i} (parallel group):")
            for node_id in layer:
                node = self.nodes[node_id]
                deps = ", ".join(node.depends_on) if node.depends_on else "none"
                lines.append(f"  • {node_id}: {node.tool_name}()")
                lines.append(f"    depends_on: {deps}")

        return "\n".join(lines)
```

### 5.3 DAG Executor

```python
# app/agent/dag_executor.py
import asyncio
import logging
from typing import Dict, List, Optional
from app.agent.dag import ExecutionDAG, DAGNode, NodeStatus
from app.agent.filesystem_agent import ToolCall
from app.sandbox.executor import ExecutionResult

logger = logging.getLogger(__name__)

class DAGExecutor:
    """
    Executes a DAG of tool calls with optimal parallelization.

    This executor:
    1. Validates the DAG structure
    2. Performs topological sort to determine execution order
    3. Executes nodes layer-by-layer, parallelizing within each layer
    4. Handles errors and propagates results
    """

    def __init__(
        self,
        orchestrator,  # ParallelToolOrchestrator
        max_concurrent: int = 5,
    ):
        self.orchestrator = orchestrator
        self.max_concurrent = max_concurrent

    async def execute(self, dag: ExecutionDAG) -> Dict[str, ExecutionResult]:
        """
        Execute the DAG and return results.

        Args:
            dag: The ExecutionDAG to execute

        Returns:
            Dictionary mapping node_id to ExecutionResult

        Raises:
            ValueError: If DAG is invalid
        """
        # Validate DAG
        is_valid, error = dag.validate()
        if not is_valid:
            raise ValueError(f"Invalid DAG: {error}")

        logger.info(f"Executing DAG with {len(dag.nodes)} nodes")
        logger.debug(f"Execution plan:\n{dag.visualize()}")

        # Get execution layers
        layers = dag.topological_sort()
        logger.info(f"DAG has {len(layers)} execution layers")

        results: Dict[str, ExecutionResult] = {}

        # Execute layer by layer
        for layer_idx, layer_nodes in enumerate(layers):
            logger.info(f"Executing layer {layer_idx} with {len(layer_nodes)} nodes")

            # Execute all nodes in this layer in parallel
            layer_results = await self._execute_layer(dag, layer_nodes, results)
            results.update(layer_results)

            # Check for failures
            failed_nodes = [
                node_id for node_id in layer_nodes
                if not results[node_id].success
            ]

            if failed_nodes:
                logger.warning(f"Layer {layer_idx} had {len(failed_nodes)} failures")
                # Mark dependent nodes as skipped
                self._mark_dependents_skipped(dag, failed_nodes)

        logger.info(f"DAG execution completed. {len(results)} nodes executed.")
        return results

    async def _execute_layer(
        self,
        dag: ExecutionDAG,
        node_ids: List[str],
        previous_results: Dict[str, ExecutionResult],
    ) -> Dict[str, ExecutionResult]:
        """
        Execute a single layer of nodes in parallel.

        Args:
            dag: The execution DAG
            node_ids: List of node IDs to execute in this layer
            previous_results: Results from previously executed nodes

        Returns:
            Dictionary mapping node_id to ExecutionResult for this layer
        """
        # Create ToolCall objects for the orchestrator
        tool_calls = []
        node_map = {}  # Map ToolCall.id -> node_id

        for node_id in node_ids:
            node = dag.nodes[node_id]

            # Resolve arguments (substitute results from dependencies)
            resolved_args = self._resolve_arguments(node, previous_results)

            # Create ToolCall
            tool_call = ToolCall(
                id=node_id,  # Use node_id as tool_call_id
                name=node.tool_name,
                arguments=resolved_args,
            )
            tool_calls.append(tool_call)
            node_map[node_id] = node

        # Execute tools in parallel using orchestrator
        execution_results = await self.orchestrator.execute_parallel(tool_calls)

        # Map results back to nodes
        results = {}
        for tool_call, result in execution_results:
            node_id = tool_call.id
            node = node_map[node_id]

            # Update node status
            if result.success:
                node.status = NodeStatus.COMPLETED
                node.result = result
            else:
                node.status = NodeStatus.FAILED
                node.error = result.stderr

            results[node_id] = result

        return results

    def _resolve_arguments(
        self,
        node: DAGNode,
        previous_results: Dict[str, ExecutionResult],
    ) -> Dict[str, any]:
        """
        Resolve node arguments, substituting references to previous results.

        Example:
            node.arguments = {"files": "$find_files.output"}
            previous_results = {"find_files": ExecutionResult(stdout="a.py\nb.py")}

            returns: {"files": "a.py\nb.py"}
        """
        resolved = {}

        for key, value in node.arguments.items():
            if isinstance(value, str) and value.startswith("$"):
                # Reference to another node's output
                ref_node_id = value[1:].split(".")[0]

                if ref_node_id not in previous_results:
                    raise ValueError(f"Unresolved dependency: {ref_node_id}")

                # Get the output from the referenced node
                resolved[key] = previous_results[ref_node_id].stdout
            else:
                resolved[key] = value

        return resolved

    def _mark_dependents_skipped(
        self,
        dag: ExecutionDAG,
        failed_nodes: List[str],
    ) -> None:
        """
        Mark all nodes dependent on failed nodes as SKIPPED.

        This prevents wasting time executing nodes that depend on failed operations.
        """
        to_skip = set(failed_nodes)

        # Iteratively find all dependents
        changed = True
        while changed:
            changed = False
            for node_id, node in dag.nodes.items():
                if node.status == NodeStatus.PENDING:
                    if any(dep in to_skip for dep in node.depends_on):
                        node.status = NodeStatus.SKIPPED
                        to_skip.add(node_id)
                        changed = True

        if len(to_skip) > len(failed_nodes):
            logger.info(f"Marked {len(to_skip) - len(failed_nodes)} dependent nodes as skipped")
```

### 5.4 DAG Planner (LLM-based)

```python
# app/agent/dag_planner.py
import json
import logging
from typing import Optional
from openai import AsyncAzureOpenAI
from app.agent.dag import ExecutionDAG, DAGNode

logger = logging.getLogger(__name__)

PLANNING_PROMPT = """
You are a task planning assistant. Given a user query, create an execution plan as a Directed Acyclic Graph (DAG).

Available tools:
- grep(pattern, path, recursive=true, ignore_case=false): Search for pattern in files
- find(path, name_pattern, type="f"): Find files by name pattern
- cat(path): Read file contents
- head(path, lines=10): Read first N lines
- tail(path, lines=10): Read last N lines
- ls(path): List directory contents
- wc(path): Count lines/words/chars in file

Rules:
1. Each node must have: id, tool, args
2. Add "depends_on" field if a node needs another node's output
3. Use variable syntax "$node_id.output" to reference another node's result
4. Minimize LLM calls - create a complete plan upfront
5. Maximize parallelization - only add dependencies when truly needed

Return JSON format:
{
  "nodes": [
    {"id": "step1", "tool": "find", "args": {"path": ".", "name_pattern": "*.py"}},
    {"id": "step2", "tool": "grep", "args": {"pattern": "TODO", "path": "$step1.output"}, "depends_on": ["step1"]}
  ]
}

User query: {query}

Return ONLY the JSON, no explanation.
"""

class DAGPlanner:
    """
    Generate execution DAGs from user queries using LLM.

    This planner uses the LLM to understand the user's intent and create
    an optimal execution plan as a DAG. The DAG can then be executed
    by DAGExecutor with automatic parallelization.
    """

    def __init__(self, client: AsyncAzureOpenAI, deployment_name: str):
        self.client = client
        self.deployment_name = deployment_name

    async def plan(self, query: str) -> Optional[ExecutionDAG]:
        """
        Generate a DAG execution plan for the given query.

        Args:
            query: User's query/request

        Returns:
            ExecutionDAG if successful, None if planning fails
        """
        try:
            # Ask LLM to create a plan
            response = await self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are a task planning expert."},
                    {"role": "user", "content": PLANNING_PROMPT.format(query=query)}
                ],
                temperature=0.1,  # Low temperature for consistent planning
            )

            plan_json = response.choices[0].message.content
            logger.debug(f"LLM generated plan: {plan_json}")

            # Parse JSON
            plan_data = json.loads(plan_json)

            # Convert to ExecutionDAG
            dag = self._build_dag_from_json(plan_data)

            # Validate
            is_valid, error = dag.validate()
            if not is_valid:
                logger.error(f"Invalid DAG generated: {error}")
                return None

            logger.info(f"Successfully generated DAG with {len(dag.nodes)} nodes")
            return dag

        except Exception as e:
            logger.exception(f"Error in DAG planning: {e}")
            return None

    def _build_dag_from_json(self, plan_data: dict) -> ExecutionDAG:
        """Convert JSON plan to ExecutionDAG."""
        dag = ExecutionDAG()

        for node_data in plan_data["nodes"]:
            node = DAGNode(
                id=node_data["id"],
                tool_name=node_data["tool"],
                arguments=node_data["args"],
                depends_on=node_data.get("depends_on", []),
            )
            dag.add_node(node)

        return dag
```

### 5.5 Integration với FilesystemAgent

```python
# app/agent/filesystem_agent.py (modified)

class FilesystemAgent:
    def __init__(
        self,
        # ... existing params ...
        use_dag_planner: bool = False,  # NEW: Enable DAG-based execution
        dag_planner: Optional[DAGPlanner] = None,  # NEW
        dag_executor: Optional[DAGExecutor] = None,  # NEW
    ):
        # ... existing code ...
        self.use_dag_planner = use_dag_planner
        self.dag_planner = dag_planner
        self.dag_executor = dag_executor

    async def chat(
        self,
        user_message: str,
        history: Optional[list[dict]] = None,
    ) -> AgentResponse:
        """
        Process a user message and return a response.

        If use_dag_planner=True:
            1. Generate DAG plan from query
            2. Execute DAG with optimal parallelization
            3. Return results

        Otherwise: Use existing iterative approach
        """

        # NEW: DAG-based execution path
        if self.use_dag_planner and self.dag_planner and self.dag_executor:
            return await self._chat_with_dag(user_message, history)

        # Existing iterative execution path
        return await self._chat_iterative(user_message, history)

    async def _chat_with_dag(
        self,
        user_message: str,
        history: Optional[list[dict]] = None,
    ) -> AgentResponse:
        """
        DAG-based execution flow.

        Advantages:
        - Fewer LLM calls (1 planning call vs N iterations)
        - Better parallelization (layer-based vs simple parallel)
        - Clearer execution flow (visualizable DAG)
        """
        logger.info("Using DAG-based execution")

        # Step 1: Generate DAG plan
        dag = await self.dag_planner.plan(user_message)

        if dag is None:
            logger.warning("DAG planning failed, falling back to iterative approach")
            return await self._chat_iterative(user_message, history)

        # Step 2: Log execution plan
        plan = dag.get_execution_plan()
        logger.info(f"Execution plan: {plan['total_layers']} layers, "
                   f"max {plan['max_parallelism']} parallel operations")
        logger.debug(f"DAG visualization:\n{dag.visualize()}")

        # Step 3: Execute DAG
        results = await self.dag_executor.execute(dag)

        # Step 4: Synthesize final response with LLM
        synthesis_prompt = self._build_synthesis_prompt(user_message, dag, results)
        final_response = await self.client.chat.completions.create(
            model=self.deployment_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": synthesis_prompt},
            ],
        )

        # Step 5: Format response
        tool_calls = [
            ToolCall(
                id=node_id,
                name=dag.nodes[node_id].tool_name,
                arguments=dag.nodes[node_id].arguments,
            )
            for node_id in dag.nodes
        ]

        tool_results = [
            {
                "tool_call_id": node_id,
                "tool_name": dag.nodes[node_id].tool_name,
                "result": result.to_dict() if result else None,
            }
            for node_id, result in results.items()
        ]

        return AgentResponse(
            message=final_response.choices[0].message.content,
            tool_calls=tool_calls,
            tool_results=tool_results,
        )

    def _build_synthesis_prompt(
        self,
        user_message: str,
        dag: ExecutionDAG,
        results: Dict[str, ExecutionResult],
    ) -> str:
        """Build prompt for final response synthesis."""

        # Format results for LLM
        results_text = []
        for node_id, result in results.items():
            node = dag.nodes[node_id]
            status = "✓" if result.success else "✗"
            output = result.stdout[:500] if result.success else result.stderr[:500]
            results_text.append(
                f"{status} {node.tool_name}({node.arguments})\n"
                f"  Output: {output}"
            )

        return f"""
User asked: {user_message}

I executed the following operations:
{chr(10).join(results_text)}

Please synthesize these results into a helpful, natural language response to the user.
"""

    async def _chat_iterative(self, user_message, history):
        """Existing iterative approach (unchanged)."""
        # ... existing code from current chat() method ...
        pass
```

---

## 6. Roadmap Triển Khai

### 6.1 Phase 1: Foundation (Week 1-2)

#### Deliverables:
- [ ] DAG data structures (`app/agent/dag.py`)
- [ ] Basic DAGExecutor với topological sort
- [ ] Unit tests cho DAG validation và execution
- [ ] Documentation

#### Tasks:
```python
# Week 1
- Implement DAGNode, ExecutionDAG classes
- Write validate() method với cycle detection
- Write topological_sort() method
- Add visualization utilities

# Week 2
- Implement DAGExecutor.execute()
- Implement layer-by-layer parallel execution
- Handle error propagation
- Write comprehensive tests
```

#### Success Metrics:
- [ ] All tests pass (>90% coverage)
- [ ] Can execute simple 3-node DAG
- [ ] Cycle detection works correctly
- [ ] Visualization outputs readable ASCII art

### 6.2 Phase 2: LLM Integration (Week 3-4)

#### Deliverables:
- [ ] DAGPlanner với LLM-based planning
- [ ] Integration với FilesystemAgent
- [ ] A/B testing framework (DAG vs iterative)
- [ ] Performance benchmarks

#### Tasks:
```python
# Week 3
- Implement DAGPlanner.plan()
- Design planning prompt template
- Add JSON parsing và error handling
- Test with various query types

# Week 4
- Integrate into FilesystemAgent.chat()
- Add use_dag_planner flag
- Implement fallback mechanism
- Write integration tests
```

#### Success Metrics:
- [ ] DAG planner success rate >80%
- [ ] Performance improvement 2-3x for complex queries
- [ ] Fewer LLM calls (30-50% reduction)
- [ ] User-facing API unchanged (backward compatible)

### 6.3 Phase 3: Cache Integration (Week 5-6)

#### Deliverables:
- [ ] DAG-aware cache invalidation
- [ ] Cache dependency tracking
- [ ] Persistent DAG cache
- [ ] Cache visualization tools

#### Tasks:
```python
# Week 5
- Extend CacheManager với DAG support
- Implement dependency graph tracking
- Add invalidate_dag() method
- Test cache correctness

# Week 6
- Integrate với FileStateTracker
- Add cache key generation based on DAG structure
- Implement intelligent pre-fetching
- Performance optimization
```

#### Success Metrics:
- [ ] Cache hit rate improvement 20-30%
- [ ] Precise invalidation (no over-invalidation)
- [ ] Dependency graph correctly maintained
- [ ] Cache performance tests pass

### 6.4 Phase 4: Advanced Features (Week 7-8)

#### Deliverables:
- [ ] Dynamic DAG restructuring
- [ ] Conditional branching
- [ ] Error recovery strategies
- [ ] DAG visualization UI

#### Tasks:
```python
# Week 7
- Implement conditional nodes (if-then-else)
- Add dynamic node insertion
- Implement retry mechanism
- Add circuit breaker pattern

# Week 8
- Build web UI for DAG visualization
- Add real-time execution monitoring
- Implement DAG optimization passes
- Create example notebooks
```

#### Success Metrics:
- [ ] Support conditional workflows
- [ ] Error recovery rate >90%
- [ ] UI displays real-time DAG execution
- [ ] Complete documentation và examples

---

## 7. So Sánh Với LangGraph

### 7.1 Feature Comparison

| Feature | LangGraph | Proposed DAG System | Notes |
|---------|-----------|---------------------|-------|
| **DAG Support** | ✅ Native | ✅ Native | Both support DAG workflows |
| **Cycles** | ✅ Supported | ❌ Pure DAG | LangGraph allows cycles for agent loops |
| **Parallel Execution** | ✅ Built-in | ✅ Built-in | Both optimize parallelization |
| **LLM Planning** | ❌ Manual | ✅ Dynamic | Our system can generate DAGs via LLM |
| **Tool Integration** | ✅ Extensive | ✅ Custom | LangGraph has more pre-built tools |
| **Cache System** | ⚠️ Basic | ✅ Advanced | Our multi-tier cache is more sophisticated |
| **Filesystem Focus** | ❌ General | ✅ Specialized | Optimized for file operations |
| **Security Sandbox** | ❌ None | ✅ Built-in | Path confinement, whitelisting |
| **Learning Curve** | ⚠️ Steep | ✅ Moderate | Simpler API for our use case |

### 7.2 When to Use Each

#### Use LangGraph if:
- Need complex multi-agent coordination
- Require cycles (e.g., agent self-reflection loops)
- Want extensive pre-built integrations
- Building general-purpose agent system

#### Use Proposed DAG System if:
- Focus on filesystem/bash operations
- Need high security (sandboxing)
- Want sophisticated caching
- Prefer simple, focused API
- Already using this codebase

### 7.3 Hybrid Approach

Có thể kết hợp cả hai:

```python
# Use LangGraph for high-level workflow
from langgraph.graph import Graph

workflow = Graph()
workflow.add_node("research", research_agent)  # Uses LangGraph
workflow.add_node("filesystem_analysis", filesystem_dag_agent)  # Uses our DAG
workflow.add_node("report", report_agent)  # Uses LangGraph

workflow.add_edge("research", "filesystem_analysis")
workflow.add_edge("filesystem_analysis", "report")
```

---

## 8. Kết Luận

### 8.1 Tóm Tắt Lợi Ích

#### Performance
- **2-3x faster** cho complex queries nhờ better parallelization
- **30-50% fewer LLM calls** nhờ upfront planning
- **Cache hit rate improvement** 20-30% với DAG-aware invalidation

#### Developer Experience
- **Clear execution flow** - Có thể visualize và debug dễ dàng
- **Predictable behavior** - DAG structure rõ ràng hơn N iterations
- **Better testability** - Test từng node độc lập

#### User Experience
- **Faster responses** - Reduced latency
- **More reliable** - Better error handling
- **Explainable** - User có thể thấy execution plan

### 8.2 Rủi Ro và Mitigations

| Rủi Ro | Impact | Mitigation |
|--------|--------|------------|
| LLM planning sai | High | Fallback to iterative approach |
| Over-engineering | Medium | Start simple, iterate based on metrics |
| Breaking changes | Low | Feature flag, backward compatibility |
| Increased complexity | Medium | Good documentation, examples |

### 8.3 Next Steps

1. **Review và Feedback** (Week 0)
   - Team review document này
   - Gather feedback và requirements
   - Prioritize features

2. **Prototype** (Week 1-2)
   - Build Phase 1 foundation
   - Test với real queries
   - Measure performance gains

3. **Iterate** (Week 3-8)
   - Follow roadmap phases
   - Continuous testing và optimization
   - Collect user feedback

4. **Production** (Week 9+)
   - Enable by default (sau khi validated)
   - Monitor metrics
   - Continuous improvement

---

## Appendix A: Code Examples

### Example 1: Simple DAG Execution

```python
from app.agent.dag import ExecutionDAG, DAGNode
from app.agent.dag_executor import DAGExecutor

# Create DAG
dag = ExecutionDAG()

# Add nodes
dag.add_node(DAGNode(
    id="find_python",
    tool_name="find",
    arguments={"path": ".", "name_pattern": "*.py"}
))

dag.add_node(DAGNode(
    id="count_lines",
    tool_name="wc",
    arguments={"files": "$find_python.output"},
    depends_on=["find_python"]
))

# Execute
executor = DAGExecutor(orchestrator)
results = await executor.execute(dag)

print(results["count_lines"].stdout)
```

### Example 2: Complex Multi-Branch DAG

```python
# Query: "Find TODO and FIXME comments, categorize by priority"

dag = ExecutionDAG()

# Branch 1: TODO comments
dag.add_node(DAGNode(
    id="find_todos",
    tool_name="grep",
    arguments={"pattern": "TODO", "path": ".", "recursive": True}
))

# Branch 2: FIXME comments
dag.add_node(DAGNode(
    id="find_fixmes",
    tool_name="grep",
    arguments={"pattern": "FIXME", "path": ".", "recursive": True}
))

# Merge branches
dag.add_node(DAGNode(
    id="categorize",
    tool_name="process",  # Custom tool
    arguments={
        "todos": "$find_todos.output",
        "fixmes": "$find_fixmes.output"
    },
    depends_on=["find_todos", "find_fixmes"]
))

# Execution flow:
#      find_todos  ─┐
#                   ├─→ categorize
#     find_fixmes  ─┘
```

---

## Appendix B: References

### Academic Papers
- "Directed Acyclic Graphs: The Backbone of Modern Multi-Agent AI" (2025)
- "Agentic AI workflows in Directed Acyclic Graphs (DAGs)" (2025)

### Frameworks
- [LangGraph](https://github.com/langchain-ai/langgraph) - DAG-based agent framework from LangChain
- [DAGent](https://github.com/dagent/dagent) - Open-source DAG AI agent library
- [Apache Airflow](https://airflow.apache.org/) - DAG-based workflow orchestration

### Blog Posts
- [Vercel: How to Build Agents with Filesystems and Bash](https://vercel.com/blog/how-to-build-agents-with-filesystems-and-bash)
- [Getting Started with LangGraph](https://doggydish.com/getting-started-with-langgraph-build-your-first-dag-based-agent-flow/)

### Internal Documentation
- [CLAUDE.md](../CLAUDE.md) - Project overview
- [CACHE_INTEGRATION_GUIDE.md](./CACHE_INTEGRATION_GUIDE.md) - Cache system documentation

---

**Document Version**: 1.0
**Last Updated**: 2026-01-23
**Author**: AI Analysis based on codebase review
**Status**: Proposal - Awaiting Review
