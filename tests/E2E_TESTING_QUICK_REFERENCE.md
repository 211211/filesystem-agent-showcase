# E2E Testing Quick Reference

## Running Tests

### Run All E2E Tests
```bash
# Run all E2E complex query tests (53 tests)
poetry run pytest tests/test_e2e_complex_queries.py -v

# Run all integration tests (98 tests)
poetry run pytest tests/test_e2e_complex_queries.py tests/test_vercel_optimizations_integration.py -v
```

### Run Specific Test Categories
```bash
# Multi-folder search operations
poetry run pytest tests/test_e2e_complex_queries.py::TestMultiFolderSearchOperations -v

# Large file handling
poetry run pytest tests/test_e2e_complex_queries.py::TestLargeFileHandling -v

# Output truncation
poetry run pytest tests/test_e2e_complex_queries.py::TestOutputTruncationAdvanced -v

# Lazy tool loading
poetry run pytest tests/test_e2e_complex_queries.py::TestLazyToolLoadingComplex -v

# Smart cat modes
poetry run pytest tests/test_e2e_complex_queries.py::TestSmartCatModes -v

# Complex grep patterns
poetry run pytest tests/test_e2e_complex_queries.py::TestComplexGrepPatterns -v

# Combined operations
poetry run pytest tests/test_e2e_complex_queries.py::TestCombinedOperations -v

# Token efficiency and performance
poetry run pytest tests/test_e2e_complex_queries.py::TestTokenEfficiencyAndPerformance -v

# Edge cases
poetry run pytest tests/test_e2e_complex_queries.py::TestEdgeCasesComplexQueries -v

# Real-world patterns
poetry run pytest tests/test_e2e_complex_queries.py::TestRealWorldQueryPatterns -v
```

### Run Specific Test
```bash
poetry run pytest tests/test_e2e_complex_queries.py::TestMultiFolderSearchOperations::test_find_json_files_across_all_folders -v
```

### Run with Coverage
```bash
# Coverage report in terminal
poetry run pytest tests/test_e2e_complex_queries.py --cov=app --cov-report=term-missing

# Generate HTML coverage report
poetry run pytest tests/test_e2e_complex_queries.py --cov=app --cov-report=html

# View HTML report
open htmlcov/index.html
```

## Test Categories Overview

| Category | Tests | Focus |
|----------|-------|-------|
| Multi-Folder Search | 5 | Cross-folder file discovery |
| Large File Handling | 4 | Head-first pattern efficiency |
| Output Truncation | 4 | Preventing token overflow |
| Lazy Tool Loading | 6 | Intent-based tool selection |
| Smart Cat Modes | 8 | Flexible file reading |
| Complex Grep | 4 | Pattern matching across files |
| Combined Operations | 5 | Multi-step workflows |
| Token Efficiency | 6 | Performance and savings |
| Edge Cases | 6 | Error handling |
| Real-World Patterns | 5 | User workflow validation |

## Common Test Patterns

### 1. Testing Command Building
```python
def test_command_building(self):
    cmd = build_command("grep", {
        "pattern": "search_term",
        "path": "benchmark",
        "recursive": True
    })
    assert cmd == ["grep", "-n", "-r", "search_term", "benchmark"]
```

### 2. Testing Command Execution
```python
@pytest.mark.asyncio
async def test_command_execution(self, sandbox_executor):
    cmd = build_command("find", {
        "path": ".",
        "name_pattern": "*.json"
    })
    result = await sandbox_executor.execute(cmd)
    assert result.success
    assert len(result.stdout) > 0
```

### 3. Testing Tool Selection
```python
def test_tool_selection(self):
    tools = ToolSelector.select_tools(
        "find Python files",
        include_all_on_unknown=False
    )
    tool_names = {t["function"]["name"] for t in tools}
    assert "find" in tool_names
```

### 4. Testing Output Truncation
```python
def test_truncation(self, output_processor):
    long_output = "\n".join([f"line{i}" for i in range(200)])
    result = output_processor.truncate(long_output)
    assert result.was_truncated
    assert result.original_lines == 200
```

### 5. Testing Multi-Step Workflows
```python
@pytest.mark.asyncio
async def test_workflow(self, sandbox_executor):
    # Step 1: Find files
    result1 = await sandbox_executor.execute(find_cmd)
    files = result1.stdout.strip().split('\n')

    # Step 2: Read first file
    result2 = await sandbox_executor.execute(read_cmd)
    assert result2.success
```

## Key Fixtures

### sandbox_executor
```python
@pytest.fixture
def sandbox_executor():
    """Provides SandboxExecutor instance for command execution."""
    return SandboxExecutor(
        root_path=DATA_ROOT,
        timeout=30,
        max_file_size=10 * 1024 * 1024,
        max_output_size=1 * 1024 * 1024,
    )
```

### output_processor
```python
@pytest.fixture
def output_processor():
    """Provides OutputProcessor instance for truncation testing."""
    return OutputProcessor(max_lines=50, max_chars=10000)
```

## Data Directory Structure

Tests use the actual `data/` directory:

```
data/
├── benchmark/
│   ├── arxiv-100-papers/    # 100 paper dataset
│   ├── arxiv-1000-papers/   # 1000 paper dataset
│   └── report.md
├── projects/
│   ├── project-alpha/
│   └── project-beta/
├── knowledge-base/
│   ├── procedures/
│   ├── policies/
│   └── faqs/
├── notes/
└── example.txt
```

## Debugging Failed Tests

### Run with verbose output
```bash
poetry run pytest tests/test_e2e_complex_queries.py -vv
```

### Run with traceback
```bash
poetry run pytest tests/test_e2e_complex_queries.py --tb=long
```

### Run with print statements
```bash
poetry run pytest tests/test_e2e_complex_queries.py -s
```

### Run specific failed test
```bash
poetry run pytest tests/test_e2e_complex_queries.py::TestClass::test_name -vv --tb=long
```

## Performance Benchmarks

Expected performance metrics:

- **Total test execution**: < 2 seconds for all 53 tests
- **Individual test**: < 100ms average
- **Tool selection**: < 0.5s for 100 operations
- **Command execution**: < 1s for simple commands

## Key Metrics Tested

### Token Savings
- Head-first pattern: 50-90% savings on large files
- Lazy tool loading: 30-50% reduction in tool count (~2000-3000 tokens)
- Output truncation: Limits to 50 lines / 10,000 chars

### Coverage
- `bash_tools.py`: 95%
- `tool_selector.py`: 93%
- `output_processor.py`: 91%
- `sandbox/executor.py`: 69%

## Test Markers

Tests use standard pytest async marker:

```python
@pytest.mark.asyncio
async def test_name(self, fixture):
    """Test description."""
    # Test code
```

## Skipping Tests

Some tests skip if required files don't exist:

```python
if not (DATA_ROOT / "example.txt").exists():
    pytest.skip("example.txt not found")
```

## Adding New Tests

### Template for new test
```python
@pytest.mark.asyncio
async def test_new_feature(self, sandbox_executor):
    """Test description of what this validates."""
    # Arrange
    cmd = build_command("tool_name", {"param": "value"})

    # Act
    result = await sandbox_executor.execute(cmd)

    # Assert
    assert result.success
    assert "expected" in result.stdout
```

### Checklist for new tests
- [ ] Add descriptive docstring
- [ ] Use appropriate fixtures
- [ ] Test both success and failure cases
- [ ] Verify output format/content
- [ ] Add to appropriate test class
- [ ] Update this reference if adding new category

## CI/CD Integration

These tests are suitable for CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Run E2E Tests
  run: poetry run pytest tests/test_e2e_complex_queries.py -v --tb=short

- name: Run with Coverage
  run: poetry run pytest tests/test_e2e_complex_queries.py --cov=app --cov-report=xml
```

## Related Documentation

- [E2E Testing Summary](E2E_TESTING_SUMMARY.md) - Comprehensive overview
- [Vercel Optimizations Tests](test_vercel_optimizations_integration.py) - Original integration tests
- [Project README](../README.md) - Project setup and overview
- [CLAUDE.md](../CLAUDE.md) - Development guidelines

## Quick Tips

1. **Run tests before committing**: `poetry run pytest tests/test_e2e_complex_queries.py`
2. **Check coverage**: `poetry run pytest tests/test_e2e_complex_queries.py --cov=app`
3. **Focus on failures**: Use `-x` flag to stop at first failure
4. **Parallel execution**: Use `-n auto` with pytest-xdist (not installed by default)
5. **Watch mode**: Use `pytest-watch` for continuous testing during development

## Troubleshooting

### Test times out
- Check `COMMAND_TIMEOUT` setting in executor
- Verify data files exist
- Check for infinite loops in test logic

### Test fails on file not found
- Verify `DATA_ROOT` path is correct
- Check if test data exists in `data/` directory
- Review skip conditions in test

### Async test errors
- Ensure `@pytest.mark.asyncio` decorator is present
- Check pytest-asyncio plugin is installed
- Verify fixture is marked as async if needed

### Coverage not showing expected results
- Check which files are included in coverage
- Review coverage configuration in `pyproject.toml`
- Use `--cov-report=term-missing` to see uncovered lines

## Contact

For questions or issues with tests:
1. Check [E2E Testing Summary](E2E_TESTING_SUMMARY.md) for details
2. Review existing test patterns in the file
3. See [CLAUDE.md](../CLAUDE.md) for project guidelines
