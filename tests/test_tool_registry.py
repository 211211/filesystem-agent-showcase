"""Tests for ToolRegistry and ToolDefinition."""

import pytest
from app.repositories.tool_registry import (
    ToolParameter,
    ToolDefinition,
    ToolRegistry,
    create_default_registry,
)


class TestToolParameter:
    """Test ToolParameter dataclass"""

    def test_create_required_parameter(self):
        """Test creating a required parameter"""
        param = ToolParameter(
            name="path",
            type="string",
            description="File path",
            required=True
        )

        assert param.name == "path"
        assert param.type == "string"
        assert param.description == "File path"
        assert param.required is True
        assert param.default is None
        assert param.enum is None

    def test_create_optional_parameter_with_default(self):
        """Test creating optional parameter with default value"""
        param = ToolParameter(
            name="lines",
            type="integer",
            description="Number of lines",
            required=False,
            default=10
        )

        assert param.name == "lines"
        assert param.type == "integer"
        assert param.required is False
        assert param.default == 10

    def test_create_parameter_with_enum(self):
        """Test creating parameter with enum values"""
        param = ToolParameter(
            name="type",
            type="string",
            description="File type",
            required=False,
            default="f",
            enum=["f", "d"]
        )

        assert param.enum == ["f", "d"]
        assert param.default == "f"


class TestToolDefinition:
    """Test ToolDefinition dataclass"""

    def test_create_tool_definition(self):
        """Test creating a basic tool definition"""
        builder = lambda args: ["cat", args["path"]]
        tool = ToolDefinition(
            name="cat",
            description="Read file contents",
            parameters=[
                ToolParameter("path", "string", "File path to read")
            ],
            builder=builder,
            cacheable=True,
            cache_ttl=300
        )

        assert tool.name == "cat"
        assert tool.description == "Read file contents"
        assert len(tool.parameters) == 1
        assert tool.cacheable is True
        assert tool.cache_ttl == 300

    def test_to_openai_format_simple(self):
        """Test converting simple tool to OpenAI format"""
        builder = lambda args: ["cat", args["path"]]
        tool = ToolDefinition(
            name="cat",
            description="Read file contents",
            parameters=[
                ToolParameter("path", "string", "File path to read")
            ],
            builder=builder
        )

        openai_format = tool.to_openai_format()

        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "cat"
        assert openai_format["function"]["description"] == "Read file contents"

        params = openai_format["function"]["parameters"]
        assert params["type"] == "object"
        assert "path" in params["properties"]
        assert params["properties"]["path"]["type"] == "string"
        assert params["required"] == ["path"]

    def test_to_openai_format_with_optional_params(self):
        """Test converting tool with optional parameters to OpenAI format"""
        builder = lambda args: ["head", "-n", str(args.get("lines", 10)), args["path"]]
        tool = ToolDefinition(
            name="head",
            description="Read first N lines",
            parameters=[
                ToolParameter("path", "string", "File path", required=True),
                ToolParameter("lines", "integer", "Number of lines", required=False, default=10),
            ],
            builder=builder
        )

        openai_format = tool.to_openai_format()
        params = openai_format["function"]["parameters"]

        assert "path" in params["required"]
        assert "lines" not in params["required"]
        assert params["properties"]["lines"]["default"] == 10

    def test_to_openai_format_with_enum(self):
        """Test converting tool with enum parameter to OpenAI format"""
        builder = lambda args: ["find", args["path"], "-type", args.get("type", "f")]
        tool = ToolDefinition(
            name="find",
            description="Find files",
            parameters=[
                ToolParameter("path", "string", "Directory path"),
                ToolParameter("type", "string", "File type", False, "f", ["f", "d"]),
            ],
            builder=builder
        )

        openai_format = tool.to_openai_format()
        type_prop = openai_format["function"]["parameters"]["properties"]["type"]

        assert type_prop["enum"] == ["f", "d"]
        assert type_prop["default"] == "f"


class TestToolRegistry:
    """Test ToolRegistry class"""

    @pytest.fixture
    def registry(self):
        """Create empty registry for testing"""
        return ToolRegistry()

    @pytest.fixture
    def sample_tool(self):
        """Create a sample tool definition"""
        return ToolDefinition(
            name="cat",
            description="Read file contents",
            parameters=[
                ToolParameter("path", "string", "File path to read")
            ],
            builder=lambda args: ["cat", args["path"]],
            cacheable=True,
            cache_ttl=300
        )

    def test_register_tool(self, registry, sample_tool):
        """Test registering a tool"""
        registry.register(sample_tool)

        assert len(registry) == 1
        assert "cat" in registry
        assert registry.get("cat") == sample_tool

    def test_unregister_existing_tool(self, registry, sample_tool):
        """Test unregistering an existing tool"""
        registry.register(sample_tool)
        result = registry.unregister("cat")

        assert result is True
        assert len(registry) == 0
        assert "cat" not in registry

    def test_unregister_nonexistent_tool(self, registry):
        """Test unregistering a tool that doesn't exist"""
        result = registry.unregister("nonexistent")

        assert result is False

    def test_get_existing_tool(self, registry, sample_tool):
        """Test getting an existing tool"""
        registry.register(sample_tool)
        tool = registry.get("cat")

        assert tool == sample_tool

    def test_get_nonexistent_tool(self, registry):
        """Test getting a tool that doesn't exist"""
        tool = registry.get("nonexistent")

        assert tool is None

    def test_list_all_tools(self, registry):
        """Test listing all tools"""
        tool1 = ToolDefinition(
            name="cat",
            description="Read file",
            parameters=[ToolParameter("path", "string", "File path")],
            builder=lambda args: ["cat", args["path"]]
        )
        tool2 = ToolDefinition(
            name="grep",
            description="Search file",
            parameters=[ToolParameter("pattern", "string", "Pattern")],
            builder=lambda args: ["grep", args["pattern"]]
        )

        registry.register(tool1)
        registry.register(tool2)

        all_tools = registry.list_all()

        assert len(all_tools) == 2
        assert tool1 in all_tools
        assert tool2 in all_tools

    def test_list_names(self, registry):
        """Test listing all tool names"""
        tool1 = ToolDefinition(
            name="cat",
            description="Read file",
            parameters=[],
            builder=lambda args: ["cat"]
        )
        tool2 = ToolDefinition(
            name="grep",
            description="Search file",
            parameters=[],
            builder=lambda args: ["grep"]
        )

        registry.register(tool1)
        registry.register(tool2)

        names = registry.list_names()

        assert len(names) == 2
        assert "cat" in names
        assert "grep" in names

    def test_to_openai_format(self, registry, sample_tool):
        """Test converting all tools to OpenAI format"""
        registry.register(sample_tool)
        openai_format = registry.to_openai_format()

        assert len(openai_format) == 1
        assert openai_format[0]["type"] == "function"
        assert openai_format[0]["function"]["name"] == "cat"

    def test_build_command_simple(self, registry):
        """Test building a simple command"""
        tool = ToolDefinition(
            name="cat",
            description="Read file",
            parameters=[ToolParameter("path", "string", "File path")],
            builder=lambda args: ["cat", args["path"]]
        )
        registry.register(tool)

        cmd = registry.build_command("cat", {"path": "test.txt"})

        assert cmd == ["cat", "test.txt"]

    def test_build_command_with_flags(self, registry):
        """Test building command with optional flags"""
        tool = ToolDefinition(
            name="ls",
            description="List files",
            parameters=[
                ToolParameter("path", "string", "Directory path"),
                ToolParameter("all", "boolean", "Show all", False, False),
            ],
            builder=lambda args: [
                "ls",
                "-a" if args.get("all", False) else "",
                args["path"]
            ]
        )
        registry.register(tool)

        # Test without flag
        cmd = registry.build_command("ls", {"path": "."})
        assert cmd == ["ls", "."]

        # Test with flag
        cmd = registry.build_command("ls", {"path": ".", "all": True})
        assert cmd == ["ls", "-a", "."]

    def test_build_command_filters_empty_strings(self, registry):
        """Test that build_command filters out empty strings"""
        tool = ToolDefinition(
            name="grep",
            description="Search",
            parameters=[
                ToolParameter("pattern", "string", "Pattern"),
                ToolParameter("path", "string", "Path"),
                ToolParameter("recursive", "boolean", "Recursive", False, False),
            ],
            builder=lambda args: [
                "grep",
                "-r" if args.get("recursive", False) else "",
                args["pattern"],
                args["path"]
            ]
        )
        registry.register(tool)

        cmd = registry.build_command("grep", {
            "pattern": "test",
            "path": ".",
            "recursive": False
        })

        # Empty string from "-r" condition should be filtered
        assert cmd == ["grep", "test", "."]
        assert "" not in cmd

    def test_build_command_unknown_tool(self, registry):
        """Test building command for unknown tool raises error"""
        with pytest.raises(ValueError, match="Unknown tool: nonexistent"):
            registry.build_command("nonexistent", {})

    def test_is_cacheable(self, registry):
        """Test checking if tool is cacheable"""
        cacheable_tool = ToolDefinition(
            name="cat",
            description="Read file",
            parameters=[],
            builder=lambda args: ["cat"],
            cacheable=True
        )
        non_cacheable_tool = ToolDefinition(
            name="ls",
            description="List files",
            parameters=[],
            builder=lambda args: ["ls"],
            cacheable=False
        )

        registry.register(cacheable_tool)
        registry.register(non_cacheable_tool)

        assert registry.is_cacheable("cat") is True
        assert registry.is_cacheable("ls") is False
        assert registry.is_cacheable("nonexistent") is False

    def test_get_cache_ttl(self, registry):
        """Test getting cache TTL for tool"""
        tool_with_ttl = ToolDefinition(
            name="grep",
            description="Search",
            parameters=[],
            builder=lambda args: ["grep"],
            cacheable=True,
            cache_ttl=300
        )
        tool_without_ttl = ToolDefinition(
            name="cat",
            description="Read file",
            parameters=[],
            builder=lambda args: ["cat"],
            cacheable=True,
            cache_ttl=0
        )

        registry.register(tool_with_ttl)
        registry.register(tool_without_ttl)

        assert registry.get_cache_ttl("grep") == 300
        assert registry.get_cache_ttl("cat") == 0
        assert registry.get_cache_ttl("nonexistent") is None

    def test_len(self, registry, sample_tool):
        """Test __len__ method"""
        assert len(registry) == 0

        registry.register(sample_tool)
        assert len(registry) == 1

    def test_contains(self, registry, sample_tool):
        """Test __contains__ method"""
        assert "cat" not in registry

        registry.register(sample_tool)
        assert "cat" in registry


class TestCreateDefaultRegistry:
    """Test create_default_registry function"""

    def test_creates_registry_with_all_tools(self):
        """Test that default registry contains all expected tools"""
        registry = create_default_registry()

        expected_tools = ["grep", "find", "cat", "head", "tail", "preview", "ls", "wc"]

        assert len(registry) == 8
        for tool_name in expected_tools:
            assert tool_name in registry

    def test_grep_tool(self):
        """Test grep tool configuration"""
        registry = create_default_registry()
        grep_tool = registry.get("grep")

        assert grep_tool is not None
        assert grep_tool.name == "grep"
        assert grep_tool.cacheable is True
        assert grep_tool.cache_ttl == 300

        # Test command building
        cmd = registry.build_command("grep", {
            "pattern": "test",
            "path": ".",
            "recursive": True,
            "ignore_case": False
        })

        assert "grep" in cmd
        assert "-n" in cmd  # line numbers
        assert "-r" in cmd  # recursive
        assert "test" in cmd
        assert "." in cmd
        assert "-i" not in cmd  # not case insensitive

    def test_find_tool(self):
        """Test find tool configuration"""
        registry = create_default_registry()
        find_tool = registry.get("find")

        assert find_tool is not None
        assert find_tool.cacheable is True
        assert find_tool.cache_ttl == 300

        # Test command building
        cmd = registry.build_command("find", {
            "path": ".",
            "name": "*.py",
            "type": "f"
        })

        assert cmd == ["find", ".", "-type", "f", "-name", "*.py"]

    def test_cat_tool(self):
        """Test cat tool configuration"""
        registry = create_default_registry()
        cat_tool = registry.get("cat")

        assert cat_tool is not None
        assert cat_tool.cacheable is True
        assert cat_tool.cache_ttl == 0  # Invalidate on file change

        # Test command building
        cmd = registry.build_command("cat", {"path": "test.txt"})
        assert cmd == ["cat", "test.txt"]

    def test_head_tool(self):
        """Test head tool configuration"""
        registry = create_default_registry()
        head_tool = registry.get("head")

        assert head_tool is not None
        assert head_tool.cacheable is True

        # Test command building with default lines
        cmd = registry.build_command("head", {"path": "test.txt"})
        assert cmd == ["head", "-n", "10", "test.txt"]

        # Test command building with custom lines
        cmd = registry.build_command("head", {"path": "test.txt", "lines": 20})
        assert cmd == ["head", "-n", "20", "test.txt"]

    def test_tail_tool(self):
        """Test tail tool configuration"""
        registry = create_default_registry()
        tail_tool = registry.get("tail")

        assert tail_tool is not None
        assert tail_tool.cacheable is True

        # Test command building
        cmd = registry.build_command("tail", {"path": "test.txt", "lines": 15})
        assert cmd == ["tail", "-n", "15", "test.txt"]

    def test_ls_tool(self):
        """Test ls tool configuration"""
        registry = create_default_registry()
        ls_tool = registry.get("ls")

        assert ls_tool is not None
        assert ls_tool.cacheable is False  # Frequently changing
        assert ls_tool.cache_ttl is None

        # Test command building without flags
        cmd = registry.build_command("ls", {"path": "."})
        assert cmd == ["ls", "."]

        # Test command building with flags
        cmd = registry.build_command("ls", {"path": ".", "all": True, "long": True})
        assert cmd == ["ls", "-a", "-l", "."]

    def test_wc_tool(self):
        """Test wc tool configuration"""
        registry = create_default_registry()
        wc_tool = registry.get("wc")

        assert wc_tool is not None
        assert wc_tool.cacheable is False

        # Test command building
        cmd = registry.build_command("wc", {"path": "test.txt", "lines": True})
        assert cmd == ["wc", "-l", "test.txt"]

        cmd = registry.build_command("wc", {"path": "test.txt"})
        assert cmd == ["wc", "test.txt"]

    def test_all_tools_have_valid_openai_format(self):
        """Test that all default tools have valid OpenAI format"""
        registry = create_default_registry()
        openai_format = registry.to_openai_format()

        assert len(openai_format) == 8  # Including preview tool

        for tool_def in openai_format:
            # Check basic structure
            assert tool_def["type"] == "function"
            assert "function" in tool_def

            function = tool_def["function"]
            assert "name" in function
            assert "description" in function
            assert "parameters" in function

            params = function["parameters"]
            assert params["type"] == "object"
            assert "properties" in params
            assert "required" in params

    def test_cache_properties(self):
        """Test cache properties of all tools"""
        registry = create_default_registry()

        # Tools that should be cacheable
        cacheable_tools = ["grep", "find", "cat", "head", "tail"]
        for tool_name in cacheable_tools:
            assert registry.is_cacheable(tool_name) is True

        # Tools that should not be cacheable
        non_cacheable_tools = ["ls", "wc"]
        for tool_name in non_cacheable_tools:
            assert registry.is_cacheable(tool_name) is False

        # Check specific TTLs
        assert registry.get_cache_ttl("grep") == 300
        assert registry.get_cache_ttl("find") == 300
        assert registry.get_cache_ttl("cat") == 0  # File change based
        assert registry.get_cache_ttl("ls") is None


class TestToolRegistryIntegration:
    """Integration tests for tool registry"""

    def test_register_and_use_custom_tool(self):
        """Test registering and using a custom tool"""
        registry = ToolRegistry()

        # Create a custom tool
        custom_tool = ToolDefinition(
            name="custom",
            description="Custom command",
            parameters=[
                ToolParameter("arg1", "string", "First arg"),
                ToolParameter("arg2", "integer", "Second arg", False, 0),
            ],
            builder=lambda args: ["custom", args["arg1"], str(args.get("arg2", 0))],
            cacheable=True,
            cache_ttl=600
        )

        registry.register(custom_tool)

        # Test it's registered
        assert "custom" in registry
        assert registry.is_cacheable("custom") is True
        assert registry.get_cache_ttl("custom") == 600

        # Test command building
        cmd = registry.build_command("custom", {"arg1": "test", "arg2": 42})
        assert cmd == ["custom", "test", "42"]

        # Test OpenAI format
        openai_format = registry.to_openai_format()
        assert len(openai_format) == 1
        assert openai_format[0]["function"]["name"] == "custom"

    def test_override_default_tool(self):
        """Test that registering with same name overrides existing tool"""
        registry = create_default_registry()

        original_cat = registry.get("cat")

        # Register new cat tool
        new_cat = ToolDefinition(
            name="cat",
            description="New cat implementation",
            parameters=[ToolParameter("path", "string", "Path")],
            builder=lambda args: ["new_cat", args["path"]],
            cacheable=False
        )

        registry.register(new_cat)

        # Check it was replaced
        current_cat = registry.get("cat")
        assert current_cat != original_cat
        assert current_cat == new_cat
        assert current_cat.description == "New cat implementation"
        assert registry.is_cacheable("cat") is False
