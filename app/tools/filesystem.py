import os
import shutil
from typing import Any

from app.core.state.action import Action
from app.core.state.observation import Observation
from app.tools.base_tool_pc import Tool


class ReadFileTool(Tool):
    @property
    def name(self) -> str:
        return "fs.read"

    def prepare(self, action: Action) -> Any:
        return None

    def execute(self, action: Action, context: Any) -> Observation:
        args = action.arguments
        path = args.get("path")
        if not path:
            return Observation.error("Missing 'path' argument for fs.read")

        fs_root = action.sandbox.fs_root
        if not os.path.isabs(path):
            if fs_root:
                base = fs_root
            else:
                base = os.getcwd()
            abs_path = os.path.abspath(os.path.join(base, path))
        else:
            abs_path = os.path.abspath(path)

        if fs_root:
            fs_root = os.path.abspath(fs_root)
            if not os.path.commonpath([abs_path, fs_root]) == fs_root:
                return Observation.error(f"Access denied: path '{path}' is outside allowed sandbox")

        try:
            if not os.path.isfile(abs_path):
                return Observation.error(f"File not found: '{path}'")
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return Observation.success(
                payload=content,
                metadata={"size": len(content), "path": abs_path},
                side_effects={}
            )
        except Exception as e:
            return Observation.error(f"Error reading file: {e}")

    def validate_arguments(self, arguments: dict[str, Any]) -> tuple[bool, str]:
        path = arguments.get("path")
        if path is None:
            return False, "Missing 'path' argument"
        if not isinstance(path, str):
            return False, "'path' must be a string"
        return True, ""

    def cleanup(self, action: Action, context: Any) -> None:
        pass


class WriteFileTool(Tool):
    @property
    def name(self) -> str:
        return "fs.write"

    def prepare(self, action: Action) -> Any:
        return None

    def execute(self, action: Action, context: Any) -> Observation:
        args = action.arguments
        path = args.get("path")
        content = args.get("content", "")
        if not path:
            return Observation.error("Missing 'path' argument for fs.write")

        fs_root = action.sandbox.fs_root
        if not os.path.isabs(path):
            if fs_root:
                base = fs_root
            else:
                base = os.getcwd()
            abs_path = os.path.abspath(os.path.join(base, path))
        else:
            abs_path = os.path.abspath(path)

        if fs_root:
            fs_root = os.path.abspath(fs_root)
            if not os.path.commonpath([abs_path, fs_root]) == fs_root:
                return Observation.error(f"Access denied: path '{path}' is outside allowed sandbox")

        try:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return Observation.success(
                payload={"bytes_written": len(content.encode('utf-8'))},
                metadata={"path": abs_path},
                side_effects={"files_written": [abs_path]}
            )
        except Exception as e:
            return Observation.error(f"Error writing file: {e}")

    def validate_arguments(self, arguments: dict[str, Any]) -> tuple[bool, str]:
        path = arguments.get("path")
        if path is None:
            return False, "Missing 'path' argument"
        if not isinstance(path, str):
            return False, "'path' must be a string"
        content = arguments.get("content")
        if content is not None and not isinstance(content, str):
            return False, "'content' must be a string if provided"
        return True, ""

    def cleanup(self, action: Action, context: Any) -> None:
        pass


class MoveFileTool(Tool):
    @property
    def name(self) -> str:
        return "fs.move"

    def prepare(self, action: Action) -> Any:
        return None

    def execute(self, action: Action, context: Any) -> Observation:
        args = action.arguments
        src = args.get("src")
        dst = args.get("dst")
        if not src:
            return Observation.error("Missing 'src' argument for fs.move")
        if not dst:
            return Observation.error("Missing 'dst' argument for fs.move")

        fs_root = action.sandbox.fs_root
        def resolve_path(p: str) -> str:
            if not os.path.isabs(p):
                if fs_root:
                    base = fs_root
                else:
                    base = os.getcwd()
                return os.path.abspath(os.path.join(base, p))
            else:
                return os.path.abspath(p)

        abs_src = resolve_path(src)
        abs_dst = resolve_path(dst)

        if fs_root:
            fs_root = os.path.abspath(fs_root)
            if not os.path.commonpath([abs_src, fs_root]) == fs_root:
                return Observation.error(f"Access denied: source path '{src}' is outside allowed sandbox")
            if not os.path.commonpath([abs_dst, fs_root]) == fs_root:
                return Observation.error(f"Access denied: destination path '{dst}' is outside allowed sandbox")

        try:
            if not os.path.isfile(abs_src):
                return Observation.error(f"Source file not found: '{src}'")
            os.makedirs(os.path.dirname(abs_dst), exist_ok=True)
            shutil.move(abs_src, abs_dst)
            return Observation.success(
                payload=True,
                metadata={"source": abs_src, "destination": abs_dst},
                side_effects={"files_moved": [{"from": abs_src, "to": abs_dst}]}
            )
        except Exception as e:
            return Observation.error(f"Error moving file: {e}")

    def validate_arguments(self, arguments: dict[str, Any]) -> tuple[bool, str]:
        src = arguments.get("src")
        if src is None:
            return False, "Missing 'src' argument"
        if not isinstance(src, str):
            return False, "'src' must be a string"
        dst = arguments.get("dst")
        if dst is None:
            return False, "Missing 'dst' argument"
        if not isinstance(dst, str):
            return False, "'dst' must be a string"
        return True, ""

    def cleanup(self, action: Action, context: Any) -> None:
        pass


class ListFileTool(Tool):
    @property
    def name(self) -> str:
        return "fs.list"

    def prepare(self, action: Action) -> Any:
        return None

    def execute(self, action: Action, context: Any) -> Observation:
        args = action.arguments
        path = args.get("path")
        if not path:
            return Observation.error("Missing 'path' argument for fs.list")

        fs_root = action.sandbox.fs_root
        if not os.path.isabs(path):
            if fs_root:
                base = fs_root
            else:
                base = os.getcwd()
            abs_path = os.path.abspath(os.path.join(base, path))
        else:
            abs_path = os.path.abspath(path)

        if fs_root:
            fs_root = os.path.abspath(fs_root)
            if not os.path.commonpath([abs_path, fs_root]) == fs_root:
                return Observation.error(f"Access denied: path '{path}' is outside allowed sandbox")

        try:
            if not os.path.isdir(abs_path):
                return Observation.error(f"Path is not a directory: '{path}'")
            entries = []
            for entry in os.scandir(abs_path):
                info = {
                    "name": entry.name,
                    "path": entry.path,
                    "is_file": entry.is_file(),
                    "is_dir": entry.is_dir(),
                }
                try:
                    stat = entry.stat()
                    info["size"] = stat.st_size
                except Exception:
                    info["size"] = None
                entries.append(info)
            return Observation.success(
                payload=entries,
                metadata={"path": abs_path, "count": len(entries)},
                side_effects={}
            )
        except Exception as e:
            return Observation.error(f"Error listing directory: {e}")

    def validate_arguments(self, arguments: dict[str, Any]) -> tuple[bool, str]:
        path = arguments.get("path")
        if path is None:
            return False, "Missing 'path' argument"
        if not isinstance(path, str):
            return False, "'path' must be a string"
        return True, ""

    def cleanup(self, action: Action, context: Any) -> None:
        pass


def register_filesystem_tools(executor):
    """Register all filesystem tools with the executor."""
    from app.tools.executor import ToolExecutor
    
    if not isinstance(executor, ToolExecutor):
        raise TypeError("executor must be a ToolExecutor")
    
    tools = [
        ReadFileTool(),
        WriteFileTool(),
        MoveFileTool(),
        ListFileTool(),
    ]
    for tool in tools:
        executor.registry.register(tool)