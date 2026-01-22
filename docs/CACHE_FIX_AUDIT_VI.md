# Audit Document: Cache Fix Plan

**Ngày audit:** 2026-01-22
**Tài liệu được audit:** `docs/CACHE_FIX_PLAN.md`
**Version:** v3.0 Cache System

---

## 1. Technical Architect - Kiến trúc sư kỹ thuật

### Đánh giá tổng quan

**Điểm mạnh:**
- Design decisions được document rõ ràng với rationale hợp lý
- Phương pháp hybrid approach cho F2 (search invalidation) là lựa chọn đúng đắn - cân bằng giữa correctness và performance
- Việc cache full content và slice sau (F1) tuân theo nguyên tắc DRY và giảm disk I/O

**Quan ngại:**

1. **F2 - Scalability concern:**
   - `scope.rglob("*")` với 1000+ files sẽ gây blocking I/O
   - Đề xuất: Thêm file count threshold (ví dụ: 500 files) và fallback về directory-level invalidation khi vượt ngưỡng
   - Cân nhắc async file enumeration với `aiofiles` hoặc `anyio`

2. **Memory footprint của ScopedSearchResult:**
   ```python
   file_states: Dict[str, tuple]  # path -> (mtime, size, hash)
   ```
   - Với 1000 files, mỗi entry ~200 bytes → ~200KB per search result
   - Nếu có 100 search queries cached → 20MB chỉ cho metadata
   - Đề xuất: Dùng `__slots__` cho FileState hoặc compact binary format

3. **F4 - Path comparison:**
   - `pathlib.relative_to()` có thể raise exception với symlinks
   - Đề xuất: Dùng `os.path.commonpath()` hoặc resolve symlinks trước

### Kiến trúc đề xuất bổ sung

```
┌─────────────────────────────────────────────────────────┐
│                    Cache Manager                         │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ ContentCache │  │ SearchCache  │  │  MetaCache   │  │
│  │  (full file) │  │ (+ states)   │  │ (file stats) │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                  │          │
│         └────────────┬────┴──────────────────┘          │
│                      ▼                                   │
│              ┌───────────────┐                          │
│              │  DiskCache    │                          │
│              │   (LRU)       │                          │
│              └───────────────┘                          │
└─────────────────────────────────────────────────────────┘
```

**Khuyến nghị thêm MetaCache layer** để tránh duplicate file stat operations giữa ContentCache và SearchCache.

### Verdict: ✅ APPROVED với điều kiện

- Thêm file count limit cho F2
- Document giới hạn scalability trong README

---

## 2. Senior Developer - Lập trình viên cao cấp

### Code Review Chi Tiết

**F1 - head/cat Cache Key Collision:**

✅ **Đồng ý với approach.** Tuy nhiên:

```python
# Vấn đề: Line splitting có thể khác với actual file
content = "\n".join(full_content.split("\n")[:lines])
```

Edge cases cần handle:
- File không kết thúc bằng newline
- Mixed line endings (`\r\n` vs `\n`)
- Binary files với null bytes

**Đề xuất cải tiến:**
```python
def _slice_lines(content: str, count: int, from_end: bool = False) -> str:
    """Slice content by lines, preserving original line endings."""
    # Detect line ending style
    if "\r\n" in content:
        sep = "\r\n"
    else:
        sep = "\n"

    lines = content.split(sep)
    if from_end:
        selected = lines[-count:] if count < len(lines) else lines
    else:
        selected = lines[:count]

    return sep.join(selected)
```

**F2 - Search Cache Stale:**

⚠️ **Concerns:**

1. **Race condition:**
   ```python
   # _collect_file_states và _is_scope_stale_detailed
   # có thể chạy lúc files đang được modify
   ```
   Đề xuất: Snapshot file states trong transaction-like manner

2. **Hash computation blocking:**
   ```python
   state = FileState.from_path(file_path, hash_content=True)
   ```
   Hash content cho mỗi file trong `rglob` sẽ **rất chậm** với directory lớn.

   Đề xuất optimization:
   ```python
   async def _collect_file_states(self, scope: Path) -> Dict[str, tuple]:
       # First pass: collect mtime/size only (fast)
       # Second pass: hash only changed files
       quick_states = {}
       for file_path in scope.rglob("*"):
           if file_path.is_file():
               stat = file_path.stat()
               quick_states[str(file_path)] = (stat.st_mtime, stat.st_size, None)

       # Only compute hash if mtime/size changed from cached
       # ...
   ```

3. **Exception handling:**
   ```python
   except (OSError, IOError):
       pass  # Skip inaccessible files
   ```
   Silent `pass` là **anti-pattern**. Nên log warning hoặc track skipped files.

**F3 - TTL Settings:**

✅ **Straightforward fix.** Không có concerns lớn.

Nhỏ: Verify `expire=None` behavior của DiskCache (có thể default là 0 hoặc infinite).

**F4 - Path-Segment Boundary:**

✅ **Good use of pathlib.relative_to().**

Nhưng cần handle edge case:
```python
# Nếu dir_resolved là symlink pointing outside data_root?
try:
    cached_path.relative_to(dir_resolved)
except ValueError:
    pass
```

Thêm check:
```python
if not dir_resolved.is_relative_to(self._data_root):
    raise ValueError(f"Directory outside sandbox: {directory}")
```

### Code Style Observations

- Cần thêm type hints cho tất cả parameters
- Docstrings nên follow Google style đã dùng trong project
- Magic numbers (500MB, 1000 files) nên là configurable constants

### Verdict: ✅ APPROVED với revisions

- Fix race condition trong F2
- Optimize hash computation
- Replace silent exception handling

---

## 3. DevOps Engineer - Kỹ sư vận hành

### Deployment Considerations

**Cache Directory Management:**

```yaml
# docker-compose.yml - cần thêm volume
volumes:
  - cache_data:/app/tmp/cache

# Hoặc với bind mount cho debugging
volumes:
  - ./tmp/cache:/app/tmp/cache
```

**Monitoring Recommendations:**

1. **Metrics cần expose:**
   ```python
   # Prometheus metrics
   cache_hit_total{cache_type="content|search"}
   cache_miss_total{cache_type="content|search"}
   cache_size_bytes
   cache_eviction_total
   file_state_check_duration_seconds
   ```

2. **Alerts đề xuất:**
   - Cache hit rate < 50% trong 5 phút → Warning
   - Cache size > 80% limit → Warning
   - File state check > 1s → Warning

3. **Health check endpoint:**
   ```python
   @router.get("/health/cache")
   async def cache_health():
       return {
           "content_cache": {"size": ..., "hit_rate": ...},
           "search_cache": {"size": ..., "entries": ...},
           "disk_usage": {"used": ..., "limit": ...}
       }
   ```

**Backup & Recovery:**

- Cache là ephemeral, không cần backup
- Tuy nhiên, warm-cache script cần chạy after deployment
- Đề xuất: Add to deployment pipeline

```yaml
# Kubernetes post-deploy hook
lifecycle:
  postStart:
    exec:
      command: ["python", "-m", "app.cli", "warm-cache", "--async"]
```

**Resource Planning:**

| Component | Memory Impact | Disk Impact |
|-----------|---------------|-------------|
| F1 (full content cache) | +10-20% | Same |
| F2 (file state tracking) | +50-100MB | +20-50MB |
| F3 (TTL) | Negligible | Negligible |
| F4 (path matching) | Negligible | Negligible |

Đề xuất: Tăng container memory limit từ 512MB lên 768MB sau khi deploy fixes.

### Rollback Plan

```bash
# Nếu cache issues sau deploy:
1. Set env: CACHE_ENABLED=false (nếu có flag)
2. Hoặc: clear-cache && restart
3. Rollback to previous image nếu cần
```

### Verdict: ✅ APPROVED

- Đã có cache-stats, clear-cache CLI commands
- Cần thêm monitoring metrics (Phase 2)

---

## 4. QA Engineer - Kỹ sư kiểm thử

### Test Coverage Analysis

**Existing test plan trong document:** Tốt nhưng chưa đủ.

### Additional Test Cases Required

**F1 - head/cat collision:**

```python
# Test cases bổ sung
async def test_head_then_cat_same_file():
    """Head followed by cat returns correct content."""

async def test_cat_then_head_same_file():
    """Cat followed by head returns correct content."""

async def test_concurrent_head_cat():
    """Concurrent head and cat requests work correctly."""

async def test_head_negative_lines():
    """Head with invalid line count handles gracefully."""

async def test_head_exceeds_file_lines():
    """Head requesting more lines than file has."""

async def test_empty_file_head_cat():
    """Empty file returns empty string for both operations."""

async def test_binary_file_handling():
    """Binary file with null bytes handled correctly."""

async def test_file_with_no_final_newline():
    """File without trailing newline preserves content."""
```

**F2 - Search scope staleness:**

```python
async def test_search_stale_on_file_content_change():
    """Content change within scope invalidates cache."""

async def test_search_stale_on_new_file():
    """New file in scope invalidates cache."""

async def test_search_stale_on_deleted_file():
    """Deleted file in scope invalidates cache."""

async def test_search_stale_on_renamed_file():
    """Renamed file invalidates cache."""

async def test_search_not_stale_outside_scope():
    """Changes outside scope don't invalidate cache."""

async def test_search_large_scope_performance():
    """Search with 1000+ files completes in reasonable time."""

async def test_search_scope_with_symlinks():
    """Symlinked files in scope handled correctly."""

async def test_search_concurrent_modifications():
    """Files modified during search operation."""
```

**F3 - TTL application:**

```python
async def test_content_ttl_zero():
    """TTL=0 means no expiry, rely on file state."""

async def test_content_ttl_expiry():
    """Content expires after TTL seconds."""

async def test_search_ttl_periodic_refresh():
    """Search results refresh after TTL even without changes."""
```

**F4 - Path boundary:**

```python
async def test_invalidate_exact_path():
    """/data invalidates /data/file.txt."""

async def test_invalidate_nested_path():
    """/data invalidates /data/sub/deep/file.txt."""

async def test_no_invalidate_similar_prefix():
    """/data does NOT invalidate /data2/file.txt."""

async def test_no_invalidate_suffix():
    """/data does NOT invalidate /mydata/file.txt."""

async def test_invalidate_with_trailing_slash():
    """/data/ and /data behave identically."""
```

### Regression Test Requirements

Sau khi implement fixes, chạy:
- Full test suite (300+ tests)
- Performance benchmark so với baseline
- Memory usage profiling

### Edge Cases Checklist

| Scenario | F1 | F2 | F3 | F4 |
|----------|----|----|----|----|
| Empty file | ⚠️ | N/A | N/A | N/A |
| Binary file | ⚠️ | ⚠️ | N/A | N/A |
| Symlinks | N/A | ⚠️ | N/A | ⚠️ |
| Unicode paths | ✅ | ✅ | N/A | ⚠️ |
| Very large file (>10MB) | N/A | N/A | N/A | N/A |
| Permission denied | ✅ | ⚠️ | N/A | N/A |
| Concurrent access | ⚠️ | ⚠️ | N/A | N/A |

Legend: ✅ Covered | ⚠️ Needs test | N/A Not applicable

### Verdict: ⚠️ CONDITIONALLY APPROVED

- Test plan trong document là minimum
- Cần thêm ~30 test cases trước khi merge
- Performance tests bắt buộc cho F2

---

## 5. Product Owner - Quản lý sản phẩm

### Business Impact Assessment

**Tại sao fixes này quan trọng:**

1. **F1 (HIGH) - Cache poisoning:**
   - User impact: Nhận dữ liệu sai → mất tin tưởng
   - Risk: Data integrity issues
   - **Ưu tiên:** CRITICAL - phải fix trước release

2. **F2 (HIGH) - Stale search results:**
   - User impact: Tìm kiếm trả về kết quả cũ
   - Risk: Business decisions based on outdated data
   - **Ưu tiên:** CRITICAL - phải fix trước release

3. **F3 (MEDIUM) - TTL not applied:**
   - User impact: Không có refresh tự động
   - Risk: Minor, covered by file state detection
   - **Ưu tiên:** SHOULD HAVE

4. **F4 (MEDIUM) - Path matching bug:**
   - User impact: Có thể invalidate sai cache
   - Risk: Performance degradation, not data corruption
   - **Ưu tiên:** SHOULD HAVE

### Release Strategy

**Đề xuất:** Chia thành 2 releases

**Release 3.1 (Urgent):**
- F1: head/cat collision fix
- F2: Search stale detection
- Timeline: Sprint này

**Release 3.2 (Planned):**
- F3: TTL application
- F4: Path boundary matching
- Timeline: Sprint sau

### Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Cache hit rate | 85% | >80% (acceptable drop due to stricter validation) |
| Data correctness | 95% | 100% |
| P95 response time | 50ms | <100ms (acceptable increase for F2) |
| Bug reports (cache-related) | 5/month | 0/month |

### Acceptance Criteria

**F1:**
- [ ] `head -n 10` sau đó `cat` cùng file trả về đúng nội dung
- [ ] Không có regression trong existing functionality

**F2:**
- [ ] File thay đổi trong scope → search result được invalidate
- [ ] File mới/xóa trong scope → search result được invalidate
- [ ] Performance acceptable với directories <500 files

**F3:**
- [ ] TTL config được áp dụng theo documentation
- [ ] Default behavior unchanged nếu TTL=0

**F4:**
- [ ] `/data` không invalidate `/data2`
- [ ] `/data` invalidate `/data/subdir/file`

### Stakeholder Communication

Draft release notes:
```
## v3.1 Release Notes

### Bug Fixes
- Fixed: File content caching now correctly handles partial reads
- Fixed: Search results now properly invalidate when files change

### Impact
- Improved data accuracy for file operations
- Slightly increased validation overhead for large directory searches

### Known Limitations
- Search caching may be slower for directories with >500 files
```

### Verdict: ✅ APPROVED for Release 3.1

- F1 và F2 là blockers cho production
- F3 và F4 có thể defer nếu cần

---

## Tổng kết Audit

| Role | Verdict | Key Concerns |
|------|---------|--------------|
| Technical Architect | ✅ Approved | Scalability của F2 với large directories |
| Senior Developer | ✅ Approved | Race conditions, hash performance |
| DevOps | ✅ Approved | Monitoring metrics cần bổ sung |
| QA | ⚠️ Conditional | Cần thêm ~30 test cases |
| Product Owner | ✅ Approved | Split into 2 releases |

### Final Recommendation

**✅ PROCEED WITH IMPLEMENTATION**

Với các điều kiện:
1. Thêm file count limit (500) cho F2
2. Implement performance optimization cho hash computation
3. Bổ sung test cases theo QA checklist
4. Setup monitoring trước deploy

### Action Items

| Item | Owner | Priority |
|------|-------|----------|
| Implement F1 fix | Dev | P0 |
| Implement F2 fix with file limit | Dev | P0 |
| Add 30+ test cases | QA | P0 |
| Setup cache metrics | DevOps | P1 |
| Implement F3, F4 | Dev | P2 |
| Update user documentation | Tech Writer | P2 |

---

*Audit completed by: Multi-role Review Team*
*Date: 2026-01-22*
