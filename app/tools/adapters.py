"""Adapter tools that wrap pc_agent tools to work with our BaseTool interface."""

import os
import shutil
from typing import Any, Dict, List, Optional, Tuple

from app.tools.base import BaseTool
from app.core.state.action import Action, SandboxSpec
from app.core.state.observation import Observation, ToolStatus


# Import pc_agent tools
from app.tools.filesystem import ReadFileTool as PCReadFileTool
from app.tools.filesystem import WriteFileTool as PCWriteFileTool
from app.tools.filesystem import MoveFileTool as PCMoveFileTool
from app.tools.filesystem import ListFileTool as PCListFileTool
from app.tools.terminal_tools import RunCommandTool as PCTerminalTool


class FSReadTool(BaseTool):
    """Adapter for pc_agent ReadFileTool."""
    
    name = "fs.read"
    description = "Read the contents of a text file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read"},
        },
        "required": ["path"]
    }
    selection_phrases = ["read file", "read the file", "cat file", "show file", "view file", "open file"]

    def __init__(self):
        self.pc_tool = PCReadFileTool()
    
    def execute(self, **kwargs) -> Any:
        action = Action.create(
            tool_name=self.name,
            arguments=kwargs,
            sandbox=SandboxSpec(fs_root=os.getenv("HERMES_WORKSPACE", os.getcwd()))
        )
        result = self.pc_tool.execute(action, None)
        
        if result.status == ToolStatus.SUCCESS:
            return result.payload
        elif result.status == ToolStatus.ERROR:
            raise RuntimeError(result.metadata.get("error", "Tool execution failed"))
        elif result.status == ToolStatus.TIMEOUT:
            raise TimeoutError("Tool execution timed out")
        elif result.status == ToolStatus.PERMISSION_DENIED:
            raise PermissionError("Permission denied")
        else:
            raise RuntimeError(f"Tool failed with status: {result.status}")
    
    def validate_arguments(self, arguments: dict) -> None:
        valid, error = self.pc_tool.validate_arguments(arguments)
        if not valid:
            raise ValueError(error)


class FSWriteTool(BaseTool):
    """Adapter for pc_agent WriteFileTool."""
    
    name = "fs.write"
    description = "Write content to a file, creating directories as needed"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to write"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"]
    }
    selection_phrases = ["write file", "create file", "save file", "write to file", "put file"]

    def __init__(self):
        self.pc_tool = PCWriteFileTool()
    
    def execute(self, **kwargs) -> Any:
        action = Action.create(
            tool_name=self.name,
            arguments=kwargs,
            sandbox=SandboxSpec(fs_root=os.getenv("HERMES_WORKSPACE", os.getcwd()))
        )
        result = self.pc_tool.execute(action, None)
        
        if result.status == ToolStatus.SUCCESS:
            return result.payload
        elif result.status == ToolStatus.ERROR:
            raise RuntimeError(result.metadata.get("error", "Tool execution failed"))
        elif result.status == ToolStatus.TIMEOUT:
            raise TimeoutError("Tool execution timed out")
        elif result.status == ToolStatus.PERMISSION_DENIED:
            raise PermissionError("Permission denied")
        else:
            raise RuntimeError(f"Tool failed with status: {result.status}")
    
    def validate_arguments(self, arguments: dict) -> None:
        valid, error = self.pc_tool.validate_arguments(arguments)
        if not valid:
            raise ValueError(error)


class FSMoveTool(BaseTool):
    """Adapter for pc_agent MoveFileTool."""
    
    name = "fs.move"
    description = "Move or rename a file or directory"
    parameters = {
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "Source path"},
            "dst": {"type": "string", "description": "Destination path"},
        },
        "required": ["src", "dst"]
    }
    selection_phrases = ["move file", "rename file", "mv", "move directory"]

    def __init__(self):
        self.pc_tool = PCMoveFileTool()
    
    def execute(self, **kwargs) -> Any:
        action = Action.create(
            tool_name=self.name,
            arguments=kwargs,
            sandbox=SandboxSpec(fs_root=os.getenv("HERMES_WORKSPACE", os.getcwd()))
        )
        result = self.pc_tool.execute(action, None)
        
        if result.status == ToolStatus.SUCCESS:
            return result.payload
        elif result.status == ToolStatus.ERROR:
            raise RuntimeError(result.metadata.get("error", "Tool execution failed"))
        elif result.status == ToolStatus.TIMEOUT:
            raise TimeoutError("Tool execution timed out")
        elif result.status == ToolStatus.PERMISSION_DENIED:
            raise PermissionError("Permission denied")
        else:
            raise RuntimeError(f"Tool failed with status: {result.status}")
    
    def validate_arguments(self, arguments: dict) -> None:
        valid, error = self.pc_tool.validate_arguments(arguments)
        if not valid:
            raise ValueError(error)


class FSListTool(BaseTool):
    """Adapter for pc_agent ListFileTool."""
    
    name = "fs.list"
    description = "List files and directories in a path"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to list", "default": "."},
        },
        "required": []
    }
    selection_phrases = ["list directory", "list files", "ls", "dir", "show directory", "what files"]

    def __init__(self):
        self.pc_tool = PCListFileTool()
    
    def execute(self, **kwargs) -> Any:
        # Provide default path if not specified
        if "path" not in kwargs or not kwargs["path"]:
            kwargs = dict(kwargs)
            kwargs["path"] = "."
        
        action = Action.create(
            tool_name=self.name,
            arguments=kwargs,
            sandbox=SandboxSpec(fs_root=os.getenv("HERMES_WORKSPACE", os.getcwd()))
        )
        result = self.pc_tool.execute(action, None)
        
        if result.status == ToolStatus.SUCCESS:
            return result.payload
        elif result.status == ToolStatus.ERROR:
            raise RuntimeError(result.metadata.get("error", "Tool execution failed"))
        elif result.status == ToolStatus.TIMEOUT:
            raise TimeoutError("Tool execution timed out")
        elif result.status == ToolStatus.PERMISSION_DENIED:
            raise PermissionError("Permission denied")
        else:
            raise RuntimeError(f"Tool failed with status: {result.status}")
    
    def validate_arguments(self, arguments: dict) -> None:
        # path is optional for fs.list - provide default if missing
        valid, error = self.pc_tool.validate_arguments(arguments)
        if not valid and "path" in str(error).lower():
            # If the error is about missing path, it's OK - we'll provide default
            return
        if not valid:
            raise ValueError(error)


class TerminalRunTool(BaseTool):
    """Adapter for pc_agent RunCommandTool."""
    
    name = "terminal.run"
    description = "Run a shell command"
    parameters = {
        "type": "object",
        "properties": {
            "cmd": {"type": ["string", "array"], "description": "Command to run (string or list of args)"},
            "timeout": {"type": "number", "description": "Timeout in seconds", "default": 30},
        },
        "required": ["cmd"]
    }
    selection_phrases = ["run command", "execute command", "shell", "terminal", "run shell"]

    def __init__(self):
        self.pc_tool = PCTerminalTool()
    
    def execute(self, **kwargs) -> Any:
        action = Action.create(
            tool_name=self.name,
            arguments=kwargs,
            sandbox=SandboxSpec(fs_root=os.getenv("HERMES_WORKSPACE", os.getcwd()))
        )
        result = self.pc_tool.execute(action, None)
        
        if result.status == ToolStatus.SUCCESS:
            return result.payload
        elif result.status == ToolStatus.ERROR:
            raise RuntimeError(result.metadata.get("error", "Tool execution failed"))
        elif result.status == ToolStatus.TIMEOUT:
            raise TimeoutError("Tool execution timed out")
        elif result.status == ToolStatus.PERMISSION_DENIED:
            raise PermissionError("Permission denied")
        else:
            raise RuntimeError(f"Tool failed with status: {result.status}")
    
    def validate_arguments(self, arguments: dict) -> None:
        valid, error = self.pc_tool.validate_arguments(arguments)
        if not valid:
            raise ValueError(error)