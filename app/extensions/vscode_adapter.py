"""
VS Code Application Adapter - Stage 32 Phase 6
Uses existing Desktop/Windows automation architecture (pywinauto) where appropriate.

Capabilities exposed:
- vscode.detect
- vscode.open_file
- vscode.open_folder
- vscode.read_file
- vscode.write_file
- vscode.create_file
- vscode.focus
- vscode.close_file
- vscode.get_active_file
"""

import os
import subprocess
import time
import uuid
from typing import Any, Dict, List, Optional

from app.extensions.application_adapter import (
    ApplicationAdapterInterface,
    BaseApplicationAdapter,
    AdapterMetadata,
    AdapterState,
)
from app.tools.capabilities import CapabilityCategory, ToolCapability, SideEffectLevel


class VSCodeAdapter(BaseApplicationAdapter):
    """
    VS Code application adapter using the existing Desktop automation pattern.
    Integrates with workspace security boundaries.
    """

    # Class-level launch guard: shared across ALL adapter instances
    _global_recently_launched = set()
    _launch_guard_max_size = 50

    def __init__(
        self,
        adapter_id: str = "vscode_adapter",
        workspace_root: Optional[str] = None,
        instance_id: Optional[str] = None
    ):
        display_name = "VS Code Adapter"
        super().__init__(adapter_id, "vscode", display_name)
        
        self._instance_id = instance_id or str(uuid.uuid4())[:8]
        self._workspace_root = workspace_root or os.getcwd()
        self._vscode_executable = self._find_vscode_executable()
        self._window_handle = None
        self._process_id = None
        self._initialized = False
        self._available = False

    
    def _find_vscode_executable(self) -> Optional[str]:
            """Find VS Code native executable only.

            SECURITY REMEDIATION (Stage 32 follow-up): previously invoked each
            candidate with shell=True (required for the bare 'code' PATH name,
            which cannot launch via CreateProcess without a shell). Then it accepted
            .cmd wrappers with shell=False, but CreateProcess still invokes cmd.exe
            for batch files, allowing metacharacter interpretation by the batch
            parser. DISCOVERY CORRECTION: the runtime `Code.exe --version` probe
            timed out on this machine (GUI executable defers to running instance).
            Now: only native Code.exe executables are accepted, verified by
            filesystem existence + .exe extension — no process invocation in
            discovery. PATH resolution is filtered to native executables only.
            """
            import shutil

            # Native executable candidates ONLY - common installation layouts
            exe_candidates = [
                os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\Microsoft VS Code\Code.exe"),
                r"C:\Program Files\Microsoft VS Code\Code.exe",
                r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
            ]

            # PATH resolution: only accept native executable names
            for name in ("Code.exe",):
                resolved = shutil.which(name)
                if resolved and resolved.lower().endswith(".exe") and resolved not in exe_candidates:
                    exe_candidates.append(resolved)

            # Accept native executables that exist on disk - no process invocation
            for candidate in exe_candidates:
                if not candidate or not candidate.strip():
                    continue
                # Safety: reject non-.exe extensions explicitly
                if not candidate.lower().endswith(".exe"):
                    continue
                # Filesystem check only - no subprocess.run, no version probe
                if os.path.isfile(candidate):
                    return candidate
            return None
    
    def get_capabilities(self) -> List[str]:
        return [
            "vscode.detect",
            "vscode.open_file",
            "vscode.open_folder",
            "vscode.read_file",
            "vscode.write_file",
            "vscode.create_file",
            "vscode.focus",
            "vscode.close_file",
            "vscode.get_active_file",
        ]
    
    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=self._adapter_id,
            application_id=self.application_id,
            display_name=self._display_name,
            version="1.0.0",
            supported_capabilities=self.get_capabilities(),
            availability_requirements=["vscode"],
            environment_requirements=["windows", "vscode"],
            lifecycle_requirements=["vscode_process"],
            security_metadata={
                "side_effect_level": "write",
                "risk_level": "medium",
                "requires_verification": True,
                "permission_required": "filesystem.write",
            },
            side_effect_level="write",
            risk_level="medium",
            requires_verification=True,
            initialization_timeout=30.0,
            execution_timeout=30.0,
            cleanup_timeout=10.0,
        )
    
    def _do_initialize(self) -> bool:
        """Initialize VS Code adapter - detect VS Code and optionally launch."""
        try:
            if not self._vscode_executable:
                self._set_error("VS Code executable not found")
                return False
            
            # Check if VS Code is already running (via process list, works without pywinauto)
            if self._is_vscode_running():
                # Try to find the window handle
                self._find_vscode_window()
                self._mark_initialized()
                return True
            else:
                # VS Code not running, still mark as initialized (available when launched)
                self._mark_initialized()
                return True
        except Exception as e:
            self._set_error(f"Initialization failed: {e}")
            return False
    
    def _find_vscode_window(self) -> bool:
        """Find existing VS Code window using pywinauto if available."""
        try:
            import pywinauto
            from pywinauto import Desktop
            
            desktop = Desktop(backend="uia")
            windows = desktop.windows()
            
            for w in windows:
                try:
                    title = w.window_text()
                    if "Visual Studio Code" in title or "VS Code" in title:
                        self._window_handle = w.handle
                        self._process_id = w.process_id()
                        return True
                except Exception:
                    continue
        except ImportError:
            pass  # pywinauto not available
        except Exception:
            pass
        return False
    
    def _is_vscode_running(self) -> bool:
        """Check if VS Code is running via process list."""
        try:
            result = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=5)
            return "Code.exe" in result.stdout
        except Exception:
            return False
    
    def _launch_vscode(self, path: str) -> bool:
        """Launch VS Code with the given path (file or folder).

        SECURITY REMEDIATION (Stage 32 follow-up): previously interpolated the
        path into a shell command string (f'"exe" "{path}"') and executed it
        with Popen(shell=True). cmd.exe parses that construction unsafely:
        legal Windows filename characters (&, %, ^, !) in an existing
        workspace-contained filename split the command, enabling secondary
        command execution (verified by harmless echo probes during review).
        Now: only native Code.exe executables are used. The executable and
        path are passed as separate literal argv elements with shell=False -
        no shell or batch parser interprets any argument.

        LAUNCH GUARD: prevents duplicate VS Code windows for the same path
        across ALL adapter instances (class-level). Different paths are always launched.

        TEST MOCK: if VSCODE_MOCK_LAUNCH=1 is set, skip actual process launch
        after executable validation and return success (for automated testing
        without opening real windows).
        """
        # Safety: verify executable is a native .exe (defense in depth) before
        # mock mode or launch guard can report success.
        if not self._vscode_executable or not self._vscode_executable.lower().endswith(".exe"):
            self._set_error(f"VS Code native executable not available: {self._vscode_executable}")
            return False

        # TEST MOCK: skip actual launch if environment variable is set
        if os.environ.get("VSCODE_MOCK_LAUNCH") == "1":
            norm_path = os.path.normpath(path)
            VSCodeAdapter._global_recently_launched.add(norm_path)
            return True

        # Launch guard: prevent duplicate windows for same path
        norm_path = os.path.normpath(path)
        if norm_path in VSCodeAdapter._global_recently_launched:
            # Path already launched recently - return success without re-launching
            return True

        try:
            # shell=False: executable is a full path to a native .exe; path is a literal argv element.
            result = subprocess.Popen([self._vscode_executable, path],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     shell=False)

            # Wait for VS Code process to appear, up to 10 seconds
            for _ in range(10):
                time.sleep(1)
                if self._is_vscode_running():
                    # Record successful launch
                    VSCodeAdapter._global_recently_launched.add(norm_path)
                    if len(VSCodeAdapter._global_recently_launched) > VSCodeAdapter._launch_guard_max_size:
                        # Remove oldest entry (set is unordered, pop arbitrary)
                        VSCodeAdapter._global_recently_launched.pop()
                    return True
            return False
        except Exception as e:
            self._set_error(f"Failed to launch VS Code: {e}")
            return False
    
    def _validate_workspace_path(self, path: str) -> bool:
        """Validate that path is within workspace boundaries."""
        try:
            # Resolve both paths
            workspace = os.path.abspath(self._workspace_root)
            target = os.path.abspath(path)
            
            # Check if target is within workspace
            common = os.path.commonpath([workspace, target])
            return common == workspace
        except Exception:
            return False
    
    def _do_execute(self, action: str, arguments: Dict[str, Any]) -> Any:
        """Execute a VS Code action."""
        if action == "vscode.detect":
            return self._execute_detect()
        elif action == "vscode.open_file":
            return self._execute_open_file(arguments)
        elif action == "vscode.open_folder":
            return self._execute_open_folder(arguments)
        elif action == "vscode.read_file":
            return self._execute_read_file(arguments)
        elif action == "vscode.write_file":
            return self._execute_write_file(arguments)
        elif action == "vscode.create_file":
            return self._execute_create_file(arguments)
        elif action == "vscode.focus":
            return self._execute_focus(arguments)
        elif action == "vscode.close_file":
            return self._execute_close_file(arguments)
        elif action == "vscode.get_active_file":
            return self._execute_get_active_file(arguments)
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
    
    def _execute_detect(self) -> Dict[str, Any]:
        """Detect VS Code installation and availability."""
        detected = self._vscode_executable is not None
        window_found = self._find_vscode_window()
        
        return {
            "success": True,
            "detected": detected,
            "executable": self._vscode_executable,
            "window_found": window_found,
            "process_id": self._process_id,
            "workspace_root": self._workspace_root,
        }
    
    def _execute_open_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Open a file in VS Code."""
        filepath = arguments.get("path", "")
        
        if not filepath:
            return {"success": False, "error": "Missing required argument: path"}
        
        # Security: Validate path is within workspace
        if not self._validate_workspace_path(filepath):
            return {
                "success": False, 
                "error": f"Path '{filepath}' is outside workspace boundary"
            }
        
        # Check if file exists
        if not os.path.exists(filepath):
            return {"success": False, "error": f"File not found: {filepath}"}
        
        # Open in VS Code
        if self._launch_vscode(filepath):
            return {
                "success": True,
                "opened": filepath,
                "action": "open_file",
            }
        else:
            return {"success": False, "error": "Failed to open file in VS Code"}
    
    def _execute_open_folder(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Open a folder in VS Code."""
        folderpath = arguments.get("path", "")
        
        if not folderpath:
            return {"success": False, "error": "Missing required argument: path"}
        
        # Security: Validate path is within workspace
        if not self._validate_workspace_path(folderpath):
            return {
                "success": False, 
                "error": f"Path '{folderpath}' is outside workspace boundary"
            }
        
        # Check if folder exists
        if not os.path.isdir(folderpath):
            return {"success": False, "error": f"Folder not found: {folderpath}"}
        
        # Open in VS Code
        if self._launch_vscode(folderpath):
            return {
                "success": True,
                "opened": folderpath,
                "action": "open_folder",
            }
        else:
            return {"success": False, "error": "Failed to open folder in VS Code"}
    
    def _execute_read_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Read a file through VS Code (using filesystem tool internally)."""
        filepath = arguments.get("path", "")
        
        if not filepath:
            return {"success": False, "error": "Missing required argument: path"}
        
        # Security: Validate path is within workspace
        if not self._validate_workspace_path(filepath):
            return {
                "success": False, 
                "error": f"Path '{filepath}' is outside workspace boundary"
            }
        
        # Check if file exists
        if not os.path.exists(filepath):
            return {"success": False, "error": f"File not found: {filepath}"}
        
        # Read file
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                "success": True,
                "path": filepath,
                "content": content,
                "size": len(content),
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to read file: {e}"}
    
    def _execute_write_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Write a file through VS Code (using filesystem tool internally)."""
        filepath = arguments.get("path", "")
        content = arguments.get("content", "")
        
        if not filepath:
            return {"success": False, "error": "Missing required argument: path"}
        
        # Security: Validate path is within workspace
        if not self._validate_workspace_path(filepath):
            return {
                "success": False, 
                "error": f"Path '{filepath}' is outside workspace boundary"
            }
        
        # Create directory if needed
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Write file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "written": filepath,
                "size": len(content),
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to write file: {e}"}
    
    def _execute_create_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new file in VS Code."""
        filepath = arguments.get("path", "")
        content = arguments.get("content", "")
        
        if not filepath:
            return {"success": False, "error": "Missing required argument: path"}
        
        # Security: Validate path is within workspace
        if not self._validate_workspace_path(filepath):
            return {
                "success": False, 
                "error": f"Path '{filepath}' is outside workspace boundary"
            }
        
        # Check if file already exists
        if os.path.exists(filepath):
            return {"success": False, "error": f"File already exists: {filepath}"}
        
        # Create directory if needed
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Create file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "created": filepath,
                "size": len(content),
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to create file: {e}"}
    
    def _execute_focus(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Focus the VS Code window."""
        try:
            import pywinauto
            from pywinauto import Application
            
            if not self._window_handle:
                if not self._find_vscode_window():
                    return {"success": False, "error": "No VS Code window found"}
            
            app = Application(backend="uia").connect(process=self._process_id)
            window = app.window(handle=self._window_handle)
            window.set_focus()
            
            return {
                "success": True,
                "focused": True,
                "window_handle": self._window_handle,
            }
        except ImportError:
            return {"success": False, "error": "pywinauto not available for focus operation"}
        except Exception as e:
            return {"success": False, "error": f"Failed to focus VS Code: {e}"}
    
    def _execute_close_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Close a file in VS Code (using Ctrl+W)."""
        try:
            import pywinauto
            from pywinauto import Application
            
            if not self._window_handle:
                if not self._find_vscode_window():
                    return {"success": False, "error": "No VS Code window found"}
            
            app = Application(backend="uia").connect(process=self._process_id)
            window = app.window(handle=self._window_handle)
            window.set_focus()
            window.type_keys("^w")  # Ctrl+W to close tab
            
            return {
                "success": True,
                "closed": True,
            }
        except ImportError:
            return {"success": False, "error": "pywinauto not available for close operation"}
        except Exception as e:
            return {"success": False, "error": f"Failed to close file: {e}"}
    
    def _execute_get_active_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get the active file in VS Code (limited - requires UI automation)."""
        # This is a best-effort attempt using UI automation
        try:
            import pywinauto
            from pywinauto import Application
            
            if not self._window_handle:
                if not self._find_vscode_window():
                    return {"success": False, "error": "No VS Code window found"}
            
            # In a real implementation, we'd inspect the tab control
            # For now, return metadata
            return {
                "success": True,
                "active_file": "unknown",  # Would require deep UI inspection
                "window_handle": self._window_handle,
            }
        except ImportError:
            return {"success": False, "error": "pywinauto not available"}
        except Exception as e:
            return {"success": False, "error": f"Failed to get active file: {e}"}
    
    def _do_cleanup(self) -> None:
        """Clean up VS Code adapter resources."""
        # Note: We don't close VS Code itself - just clear our references
        self._window_handle = None
        self._process_id = None
        self._initialized = False
        self._available = False


class VSCodeAdapterFactory:
    """Factory for creating isolated VS Code adapter instances."""
    
    _instances: Dict[str, VSCodeAdapter] = {}
    
    @classmethod
    def create_adapter(cls, adapter_id: str = None, workspace_root: str = None) -> VSCodeAdapter:
        """Create a new isolated VS Code adapter instance."""
        if adapter_id is None:
            adapter_id = f"vscode_adapter_{str(uuid.uuid4())[:8]}"
        
        if adapter_id in cls._instances:
            return cls._instances[adapter_id]
        
        adapter = VSCodeAdapter(adapter_id=adapter_id, workspace_root=workspace_root)
        cls._instances[adapter_id] = adapter
        return adapter
    
    @classmethod
    def get_adapter(cls, adapter_id: str) -> Optional[VSCodeAdapter]:
        return cls._instances.get(adapter_id)
    
    @classmethod
    def remove_adapter(cls, adapter_id: str) -> bool:
        adapter = cls._instances.pop(adapter_id, None)
        if adapter:
            adapter.cleanup()
            return True
        return False
    
    @classmethod
    def list_instances(cls) -> List[str]:
        return list(cls._instances.keys())
    
    @classmethod
    def cleanup_all(cls) -> None:
        for adapter in cls._instances.values():
            try:
                adapter.cleanup()
            except Exception:
                pass
        cls._instances.clear()


def create_vscode_adapter(adapter_id: str = None, workspace_root: str = None) -> VSCodeAdapter:
    """Create and initialize a VS Code adapter."""
    adapter = VSCodeAdapterFactory.create_adapter(adapter_id, workspace_root)
    if adapter.initialize():
        return adapter
    else:
        VSCodeAdapterFactory.remove_adapter(adapter.adapter_id)
        raise RuntimeError(f"Failed to initialize VS Code adapter: {adapter.get_last_error()}")