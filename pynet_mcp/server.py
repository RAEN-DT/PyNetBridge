import asyncio
import json
import psutil
import ast
import threading
from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("PyNet Platform Bridge")

PIPE_PREFIX = r'\\.\pipe\tool_runner_'

SUPPORTED_PRODUCTS = {
    "roamer.exe":  "Navisworks",
    "revit.exe":   "Revit",
    "acad.exe":    "AutoCAD",
}

ALLOWED_REFERENCES = {
    # Common .NET
    "System",
    "System.Windows.Forms",
    "System.Drawing",
    "System.Collections.Generic",
    # Navisworks
    "Autodesk.Navisworks.Api",
    "Autodesk.Navisworks.ComApi",
    "Autodesk.Navisworks.Interop.ComApi",
    "Autodesk.Navisworks.Clash",
    # Revit
    "RevitAPI",
    "RevitAPIUI",
    # AutoCAD / Civil 3D / Map 3D
    "AcMgd",
    "AcCoreMgd",
    "AcDbMgd",
    "AecBaseMgd",
    "AecPropDataMgd",
    "AeccDbMgd",
    "ManagedMapApi",   # Autodesk.Gis.Map (Map 3D) — used by 03_AutoCAD/20_GIS
}

ALLOWED_REFERENCE_PREFIXES = (
    "Raen.Core.Pynet.",
    "Raen.Navisworks.Pynet.",
    "Raen.Revit.Pynet.",
    "Raen.Civil3D.Pynet.",
)

ALLOWED_PYTHON_IMPORTS = {
    "clr", "sys", "json", "re", "time", "datetime", "pathlib",
    "typing", "threading", "collections", "xml", "math",
    "pandas", "plotly", "matplotlib", "dash", "webbrowser",
    "psutil", "functools", "openpyxl",
    # stdlib (safe)
    "uuid", "zipfile", "io", "mimetypes", "difflib", "csv",
    # third-party
    "ifcopenshell",                 # IFC processing
    "qgis", "processing",           # PyQGIS + QGIS Processing (GIS workflows)
    # project-local shared modules (deployed under .../Pynet/Library/01_Scripts)
    "pynet_clash",
}

# Submodule-level whitelist: only http.server allowed (not http.client)
ALLOWED_PYTHON_SUBMODULES = {
    "http.server",
}

BLOCKED_PYTHON_IMPORTS = {
    "os", "subprocess", "shutil", "socket", "ctypes", "pickle",
    "importlib", "urllib", "signal", "multiprocessing",
    "tempfile", "glob", "inspect", "code", "codeop",
}

BLOCKED_CALLS = {
    "eval", "exec", "compile", "__import__",
    "getattr", "setattr", "delattr", "globals", "locals", "vars",
    "breakpoint",
}

ALLOWED_CLR_ROOTS = {ref.split(".")[0] for ref in ALLOWED_REFERENCES} | {p.split(".")[0] for p in ALLOWED_REFERENCE_PREFIXES}


class ScriptAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.clr_references = []
        self.python_imports = []
        self.calls = []
        self.dangerous_attrs = []

    def visit_Import(self, node):
        for alias in node.names:
            self.python_imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            self.python_imports.append(node.module)
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "AddReference":
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "clr":
                    if node.args and isinstance(node.args[0], ast.Constant):
                        self.clr_references.append(node.args[0].value)
            self.calls.append(node.func.attr)
        elif isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr in ("__builtins__", "__subclasses__", "__globals__", "__code__"):
            self.dangerous_attrs.append(node.attr)
        self.generic_visit(node)

def check_references(refs):
    for ref in refs:
        if ref in ALLOWED_REFERENCES:
            continue
        if ref.startswith(ALLOWED_REFERENCE_PREFIXES):
            continue
        return False, f"Non-whitelisted assembly: {ref}"
    return True, None

def check_imports(imports):
    for imp in imports:
        root = imp.split(".")[0]
        # Check blocked list (by root)
        if root in BLOCKED_PYTHON_IMPORTS:
            return False, f"Blocked import: {imp}"
        # Check allowed: exact root match
        if root in ALLOWED_PYTHON_IMPORTS or root in ALLOWED_CLR_ROOTS:
            continue
        # Check allowed: submodule match (e.g. "http.server" is allowed but "http.client" is not)
        if imp in ALLOWED_PYTHON_SUBMODULES:
            continue
        return False, f"Non-whitelisted import: {imp}"
    return True, None

def check_calls(calls):
    for call in calls:
        if call in BLOCKED_CALLS:
            return False, f"Forbidden call: {call}"
    return True, None

def validate_script(script: str):
    try:
        tree = ast.parse(script)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    analyzer = ScriptAnalyzer()
    analyzer.visit(tree)

    ok, msg = check_references(analyzer.clr_references)
    if not ok:
        return False, msg

    ok, msg = check_imports(analyzer.python_imports)
    if not ok:
        return False, msg

    ok, msg = check_calls(analyzer.calls)
    if not ok:
        return False, msg

    if analyzer.dangerous_attrs:
        return False, f"Dangerous attribute access: {analyzer.dangerous_attrs[0]}"

    return True, "OK"

def send_to_pipe(pid: int, payload: dict, timeout: float = 10.0) -> str:
    pipe_path = f"{PIPE_PREFIX}{pid}"
    result = [None]
    error = [None]

    def _open_and_communicate():
        try:
            pipe = open(pipe_path, 'r+b')
            message = json.dumps(payload).encode('utf-8') + b'\n'
            pipe.write(message)
            pipe.flush()
            response = pipe.readline()
            if response:
                result[0] = response.decode('utf-8').strip()
        except FileNotFoundError:
            error[0] = FileNotFoundError(f"PyNet Instance (PID {pid}) not found.")
        except Exception as e:
            error[0] = e

    worker = threading.Thread(target=_open_and_communicate, daemon=True)
    worker.start()
    worker.join(timeout=timeout)

    if worker.is_alive():
        return f"Timeout: No response from PID {pid} after {timeout}s."
    if error[0]:
        if isinstance(error[0], FileNotFoundError):
            return f"Error: {error[0]}"
        return f"IPC Error: {str(error[0])}"
    return result[0] or f"Success: Action {payload['Action']} executed on PID {pid}."


async def _send_with_heartbeat(pid: int, payload: dict, timeout: float, ctx: Context) -> str:
    pipe_path = f"{PIPE_PREFIX}{pid}"
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _communicate():
        try:
            pipe = open(pipe_path, 'r+b')
            pipe.write(json.dumps(payload).encode('utf-8') + b'\n')
            pipe.flush()
            while True:
                raw = pipe.readline()
                if not raw:
                    loop.call_soon_threadsafe(queue.put_nowait, (None, None))
                    break
                text = raw.decode('utf-8-sig').strip()
                if not text:
                    continue
                try:
                    parsed = json.loads(text)
                except Exception:
                    parsed = {}
                loop.call_soon_threadsafe(queue.put_nowait, (text, parsed))
                if parsed.get("type") != "heartbeat":
                    break
        except FileNotFoundError:
            loop.call_soon_threadsafe(
                queue.put_nowait, (f"Error: PyNet Instance (PID {pid}) not found.", None)
            )
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, (f"IPC Error: {e}", None))

    threading.Thread(target=_communicate, daemon=True).start()

    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return f"Timeout: No response from PID {pid} after {timeout}s."
        try:
            text, parsed = await asyncio.wait_for(queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            return f"Timeout: No response from PID {pid} after {timeout}s."

        if text is None:
            return f"Error: Connection closed unexpectedly by PID {pid}."
        if parsed is None or parsed.get("type") != "heartbeat":
            return text

        beat = parsed.get("beat", "?")
        elapsed = parsed.get("elapsed", "?")
        await ctx.report_progress(beat, None, f"Executing script... {elapsed} elapsed")


# ─── System & Connection ───

@mcp.tool(annotations={"title": "List Active Instances", "readOnlyHint": True})
def list_active_instances() -> str:
    """Scans the system for running Autodesk processes with an active PyNet IPC pipe."""
    instances = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            name = proc.info['name'].lower()
            product = SUPPORTED_PRODUCTS.get(name)
            if not product:
                continue
            pid = proc.info['pid']
            pipe_path = f"\\\\.\\pipe\\tool_runner_{pid}"
            try:
                with open(pipe_path, 'r+b'):
                    instances.append(f"{product} (PID {pid})")
            except OSError:
                continue
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return f"Active instances: {', '.join(instances)}" if instances else "No active instances found."

@mcp.tool(annotations={"title": "Check Plugin Status", "readOnlyHint": True})
def check_plugin_status(pid: int) -> str:
    """Handshake ping to verify the plugin listener is responsive."""
    payload = {
        "Action": "Ping",
        "Metadata": {"TargetPid": pid},
        "Content": ""
    }
    return send_to_pipe(pid, payload, timeout=5.0)


# ─── Execution & Console Control ───

@mcp.tool(annotations={"title": "Send Command", "destructiveHint": True})
async def send_command(pid: int, script_name: str, content: str, timeout: float, ctx: Context) -> str:
    """Direct script execution in the PyNet engine (Target PID, Script Name, Content)."""
    valid, message = validate_script(content)

    if not valid:
        return f"Script rejected: {message}"

    payload = {
        "Action": "Execute",
        "Metadata": {
            "TargetPid": pid,
            "ScriptName": script_name
        },
        "Content": content
    }

    return await _send_with_heartbeat(pid, payload, timeout, ctx)

@mcp.tool(annotations={"title": "Send Command By Path", "destructiveHint": True})
async def send_command_by_path(pid: int, script_name: str, file_path: str, timeout: float, ctx: Context) -> str:
    """Executes a script file directly by path in the PyNet engine, without sending content inline."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return f"Script rejected: file not found: {file_path}"
    except Exception as e:
        return f"Script rejected: could not read file: {e}"

    valid, message = validate_script(content)
    if not valid:
        return f"Script rejected: {message}"

    payload = {
        "Action": "Execute",
        "Metadata": {
            "TargetPid": pid,
            "ScriptName": script_name
        },
        "Content": content
    }

    return await _send_with_heartbeat(pid, payload, timeout, ctx)

@mcp.tool(annotations={"title": "Get Output Window Status", "readOnlyHint": True})
def get_output_window_status(pid: int) -> str:
    """Checks if the output window is currently available/visible."""
    payload = {
        "Action": "GetOutputWindowStatus",
        "Metadata": {"TargetPid": pid},
        "Content": ""
    }
    return send_to_pipe(pid, payload, timeout=30.0)

@mcp.tool(annotations={"title": "Configure Output Window", "destructiveHint": True})
def configure_output_window(pid: int, is_available: bool) -> str:
    """Toggles the visibility of the PyNet log/output window."""
    payload = {
        "Action": "ConfigureOutputWindow",
        "Metadata": {"TargetPid": pid},
        "Content": str(is_available).lower()
    }
    return send_to_pipe(pid, payload, timeout=30.0)


# ─── Module (Tab) Management ───

@mcp.tool(annotations={"title": "Get PyNet UI Layout", "readOnlyHint": True})
def get_pynet_ui_layout(pid: int) -> str:
    """Fetches the full UI structure (ButtonsModules and ScriptButtons)."""
    payload = {
        "Action": "GetButtonsModules",
        "Metadata": {"TargetPid": pid},
        "Content": ""
    }
    return send_to_pipe(pid, payload, timeout=30.0)

@mcp.tool(annotations={"title": "Create PyNet Module", "destructiveHint": True})
def create_pynet_module(pid: int, name: str) -> str:
    """Creates a new custom Tab (ButtonsModule) in the Ribbon."""
    payload = {
        "Action": "CreateModule",
        "Metadata": {"TargetPid": pid},
        "Content": name
    }
    return send_to_pipe(pid, payload, timeout=30.0)

@mcp.tool(annotations={"title": "Delete PyNet Module", "destructiveHint": True})
def delete_pynet_module(pid: int, module_id: str) -> str:
    """Permanently deletes a module and all its contents."""
    payload = {
        "Action": "DeleteModule",
        "Metadata": {
            "TargetPid": pid,
            "ModuleId": module_id
        },
        "Content": ""
    }
    return send_to_pipe(pid, payload, timeout=30.0)


# ─── Button Management ───

@mcp.tool(annotations={"title": "Get Buttons Data", "readOnlyHint": True})
def get_buttons_data(pid: int, module_id: str) -> str:
    """Lists all script buttons for a specific module ID."""
    payload = {
        "Action": "GetButtonsData",
        "Metadata": {
            "TargetPid": pid,
            "ModuleId": module_id
        },
        "Content": ""
    }
    return send_to_pipe(pid, payload, timeout=30.0)

@mcp.tool(annotations={"title": "Deploy Script Button", "destructiveHint": True})
def deploy_script_button(
    pid: int,
    module_id: str,
    name: str,
    script_Path: str,
    icon_name: str = "Default",
    tooltip: str = ""
) -> str:
    """Installs a new ScriptButton into a specific module (Name, Script, Icon, Tooltip)."""
    button_data = {
        "Name": name,
        "ScriptPath": script_Path,
        "IconName": icon_name,
        "Tooltip": tooltip
    }

    payload = {
        "Action": "CreateButtonData",
        "Metadata": {
            "TargetPid": pid,
            "ModuleId": module_id
        },
        "Content": json.dumps(button_data)
    }
    return send_to_pipe(pid, payload, timeout=30.0)

@mcp.tool(annotations={"title": "Update Script Button", "destructiveHint": True})
def update_script_button(
    pid: int,
    module_id: str,
    button_id: str,
    name: str,
    script_Path: str,
    icon_name: str,
    tooltip: str,
    dest_module_id: str = None
) -> str:
    """Updates metadata for an existing ScriptButton or moves it to another module."""
    button_data = {
        "Id": button_id,
        "Name": name,
        "ScriptPath": script_Path,
        "IconName": icon_name,
        "Tooltip": tooltip
    }

    payload = {
        "Action": "UpdateButtonData",
        "Metadata": {
            "TargetPid": pid,
            "ModuleId": module_id,
            "ButtonId": button_id,
            "DestModuleId": dest_module_id if dest_module_id else module_id
        },
        "Content": json.dumps(button_data)
    }
    return send_to_pipe(pid, payload, timeout=30.0)

@mcp.tool(annotations={"title": "Delete Script Button", "destructiveHint": True})
def delete_script_button(pid: int, module_id: str, button_id: str) -> str:
    """Permanently removes a ScriptButton from a module by Id."""
    payload = {
        "Action": "DeleteButtonData",
        "Metadata": {
            "TargetPid": pid,
            "ModuleId": module_id,
            "ButtonId": button_id
        },
        "Content": ""
    }
    return send_to_pipe(pid, payload, timeout=30.0)


def main():
    mcp.run()

if __name__ == "__main__":
    main()
