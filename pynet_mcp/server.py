import asyncio
import json
import psutil
import ast
import threading
import urllib.request
import urllib.error
from pathlib import Path
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
    "numpy", "shapely",             # numerics + 2D computational geometry (generative design)
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


# ─── BIM Viewer control ───
# Attaches to a PyNet BIM Viewer already open in VS Code (does not launch one). Discovery is via
# the endpoint file the viewer's pnt_server publishes. Two planes:
#   • DATA  — read the .pnt JSONs (clashes.json/…) from the endpoint's dataDir. The IFC carries
#             only identifiers (pnt_id ≈ GlobalId), so all real info comes from these JSONs.
#   • CONTROL — drive the viewer (highlight/fit/clear) via POST /api/control (fanned out over SSE).

_VIEWER_ENDPOINT = Path.home() / ".pynet_viewer" / "endpoint.json"


def _read_viewer_endpoint():
    try:
        if not _VIEWER_ENDPOINT.is_file():
            return None
        return json.loads(_VIEWER_ENDPOINT.read_text("utf-8"))
    except Exception:
        return None


def _viewer_http(method: str, path: str, payload: dict = None, timeout: float = 8.0):
    """Call the running viewer's HTTP API. Returns (json_or_dict, error_string)."""
    ep = _read_viewer_endpoint()
    if not ep or not ep.get("port"):
        return None, "No viewer is running. Open the PyNet BIM Viewer in VS Code first."
    url = f"http://127.0.0.1:{ep['port']}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return (json.loads(body) if body else {}), None
    except urllib.error.URLError as e:
        return None, f"Viewer not reachable on port {ep['port']}: {e}"
    except Exception as e:
        return None, f"Viewer request failed: {e}"


@mcp.tool(annotations={"title": "Viewer Status", "readOnlyHint": True})
def viewer_status() -> str:
    """Reports whether a PyNet BIM Viewer is open in VS Code (port, package, data dir)."""
    ep = _read_viewer_endpoint()
    if not ep:
        return "No viewer is running. Open the PyNet BIM Viewer in VS Code."
    _, err = _viewer_http("POST", "/api/control", {"action": "get_state"})
    return json.dumps({
        "running": err is None,
        "port": ep.get("port"),
        "package": ep.get("package"),
        "dataDir": ep.get("dataDir"),
        "error": err,
    })


@mcp.tool(annotations={"title": "Viewer List Clashes", "readOnlyHint": True})
def viewer_list_clashes() -> str:
    """Reads the loaded package's clashes.json — the data source, NOT the viewer/IFC.

    Returns each clash with the pnt_id identifiers needed to highlight it."""
    ep = _read_viewer_endpoint()
    if not ep or not ep.get("dataDir"):
        return "No package loaded. Open a .pnt in the viewer or use viewer_load_package."
    f = Path(ep["dataDir"]) / "clashes.json"
    if not f.is_file():
        return f"clashes.json not found in {ep['dataDir']}"
    data = json.loads(f.read_text("utf-8"))
    clashes = data.get("clashes", [])
    out = [{
        "clash": c.get("Clash"), "test": c.get("Test"), "status": c.get("Status"),
        "elementA": c.get("Element A"), "elementB": c.get("Element B"),
        "pnt_id_a": c.get("pnt_id_a"), "pnt_id_b": c.get("pnt_id_b"),
    } for c in clashes]
    return json.dumps({"project": data.get("project"), "count": len(out), "clashes": out})


@mcp.tool(annotations={"title": "Viewer Load Package", "destructiveHint": True})
def viewer_load_package(pnt_path: str) -> str:
    """Loads a .pnt into the open viewer and returns a summary read from clashes.json."""
    res, err = _viewer_http("POST", "/api/load-pnt-path", {"path": pnt_path})
    if err:
        return err
    if res.get("status") != "ok":
        return f"Load failed: {res.get('message')}"
    models = res.get("models", [])
    # Push the models to the (already-open) viewer so they render.
    for m in models:
        name = m if isinstance(m, str) else m.get("fileName")
        if name:
            _viewer_http("POST", "/api/control",
                         {"action": "load_model", "payload": {"url": f"/models/{name}", "name": name}})
    # Data plane: summarise from the JSON, not the viewer.
    summary = {"models": [m if isinstance(m, str) else m.get("fileName") for m in models]}
    ep = _read_viewer_endpoint() or {}
    if ep.get("dataDir"):
        cf = Path(ep["dataDir"]) / "clashes.json"
        if cf.is_file():
            try:
                data = json.loads(cf.read_text("utf-8"))
                clashes = data.get("clashes", [])
                summary["project"] = data.get("project")
                summary["clashCount"] = len(clashes)
                summary["tests"] = sorted({c.get("Test") for c in clashes if c.get("Test")})
            except Exception:
                pass
    return json.dumps(summary)


@mcp.tool(annotations={"title": "Viewer Highlight Clash", "destructiveHint": True})
def viewer_highlight_clash(pnt_id_a: str | list[str] = None, pnt_id_b: str | list[str] = None) -> str:
    """Highlights a clash (element(s) A red, element(s) B green) and isolates the rest away.

    Usually one pnt_id per side (a single clash pair), but either side accepts a list — e.g.
    one element (A) against every counterpart it clashes with (B), all shown at once."""
    res, err = _viewer_http("POST", "/api/control",
                            {"action": "select", "payload": {"pnt_id_a": pnt_id_a, "pnt_id_b": pnt_id_b}})
    if err:
        return err
    receivers = res.get("receivers", 0)
    if not receivers:
        return "Command sent, but no viewer is connected. Open/focus the viewer panel in VS Code."
    return f"Highlighted clash in {receivers} viewer(s)."


@mcp.tool(annotations={"title": "Viewer Fit", "readOnlyHint": True})
def viewer_fit() -> str:
    """Fits the camera to all models in the open viewer."""
    res, err = _viewer_http("POST", "/api/control", {"action": "fit"})
    return err or f"Fitted ({res.get('receivers', 0)} viewer(s))."


@mcp.tool(annotations={"title": "Viewer Clear", "readOnlyHint": True})
def viewer_clear() -> str:
    """Clears highlights and ghosting in the open viewer."""
    res, err = _viewer_http("POST", "/api/control", {"action": "clear"})
    return err or f"Cleared ({res.get('receivers', 0)} viewer(s))."


@mcp.tool(annotations={"title": "Viewer Select", "destructiveHint": True})
def viewer_select(pnt_ids: list[str] = None, pnt_ids_b: list[str] = None) -> str:
    """Highlights a set of elements in the open viewer by pnt_id, in neutral colours
    (yellow / blue) with nothing else hidden — a plain "look at these" pointer.

    Pass a list of pnt_ids in `pnt_ids` (group A). Optionally pass a second list in
    `pnt_ids_b` to highlight a second group in a distinct colour. Replaces any previous
    selection. Use viewer_list_clashes / viewer_get_properties to obtain pnt_ids.
    For a clash pair (red/green, with the rest of the model isolated away), use
    viewer_highlight_clash instead."""
    if not pnt_ids and not pnt_ids_b:
        return "Nothing to select: provide pnt_ids (and optionally pnt_ids_b)."
    res, err = _viewer_http("POST", "/api/control",
                            {"action": "select_ids",
                             "payload": {"pnt_id_a": pnt_ids or None, "pnt_id_b": pnt_ids_b or None}})
    if err:
        return err
    receivers = res.get("receivers", 0)
    if not receivers:
        return "Command sent, but no viewer is connected. Open/focus the viewer panel in VS Code."
    n = len(pnt_ids or []) + len(pnt_ids_b or [])
    return f"Selected {n} element(s) in {receivers} viewer(s)."


@mcp.tool(annotations={"title": "Viewer Isolate", "destructiveHint": True})
def viewer_isolate(pnt_ids: list[str] = None) -> str:
    """Isolates (hides everything except) the given pnt_ids in the open viewer."""
    if not pnt_ids:
        return "Nothing to isolate: provide pnt_ids."
    res, err = _viewer_http("POST", "/api/control",
                            {"action": "isolate", "payload": {"pnt_ids": pnt_ids}})
    if err:
        return err
    return f"Isolate command sent ({res.get('receivers', 0)} viewer(s))."


@mcp.tool(annotations={"title": "Viewer Isolate Models", "destructiveHint": True})
def viewer_isolate_models(models: list[str] = None) -> str:
    """Shows only the given model(s)/discipline(s) (by exact name, e.g. "Snowdon Towers Sample
    HVAC"), hiding every other loaded model. Cheaper than viewer_isolate for "just show me this
    discipline" requests — no need to resolve every element's pnt_id first. Get the exact model
    names from viewer_get_state's "models" list. Undo with viewer_clear."""
    if not models:
        return "Nothing to isolate: provide one or more model names (see viewer_get_state)."
    res, err = _viewer_http("POST", "/api/control",
                            {"action": "isolate_models", "payload": {"models": models}})
    if err:
        return err
    receivers = res.get("receivers", 0)
    if not receivers:
        return "Command sent, but no viewer is connected. Open/focus the viewer panel in VS Code."
    return f"Isolated {len(models)} model(s) in {receivers} viewer(s)."


@mcp.tool(annotations={"title": "Viewer Get State", "readOnlyHint": True})
def viewer_get_state() -> str:
    """Reads the viewer's last reported state: loaded models and the pnt_id of whatever the
    user currently has selected (click in the 3D view or the tree panel — null if nothing is
    selected). Use the returned pnt_id with viewer_get_properties for its details, or feed it
    into a clashes.json lookup to find what it clashes with."""
    res, err = _viewer_http("POST", "/api/control", {"action": "get_state"})
    if err:
        return err
    return json.dumps(res.get("state", {}))


@mcp.tool(annotations={"title": "Viewer Get Properties", "readOnlyHint": True})
def viewer_get_properties(
    pnt_ids: list[str] = None,
    model: str = None,
    search: str = None,
    limit: int = 200,
    offset: int = 0,
) -> str:
    """Reads element properties (name, model, psets) from the loaded package's properties.json.

    Pass one or more pnt_ids to get their full properties (including psets) directly.

    Called with no pnt_ids, returns a paginated lightweight index (pnt_id, name, model) instead
    of every element — narrow it with `model` (exact model/discipline name, e.g. "Snowdon Towers
    Sample HVAC") and/or `search` (case-insensitive substring of the element name), and page
    through with `limit`/`offset` (default 200 per page, capped at 500). On a federated model
    the unfiltered index can have tens of thousands of entries — always pass `model` or `search`
    when you can, and use `offset` to page through the rest.

    The data source is the .pnt's properties.json, NOT the viewer or IFC."""
    ep = _read_viewer_endpoint()
    if not ep or not ep.get("dataDir"):
        return "No package loaded. Open a .pnt in the viewer or use viewer_load_package."
    f = Path(ep["dataDir"]) / "properties.json"
    if not f.is_file():
        return f"properties.json not found in {ep['dataDir']}"
    try:
        props = json.loads(f.read_text("utf-8"))
    except Exception as e:
        return f"Failed to read properties.json: {e}"

    if pnt_ids:
        out = {pid: props.get(pid, {"error": "pnt_id not found in properties.json"}) for pid in pnt_ids}
        return json.dumps(out, ensure_ascii=False)

    search_l = search.lower() if search else None
    matches = []
    for k, v in props.items():
        if k.startswith("__"):
            continue
        if model and v.get("model") != model:
            continue
        if search_l and search_l not in (v.get("name") or "").lower():
            continue
        matches.append({"pnt_id": k, "name": v.get("name"), "model": v.get("model")})

    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    page = matches[offset: offset + limit]
    return json.dumps({
        "total": len(matches),
        "offset": offset,
        "limit": limit,
        "returned": len(page),
        "elements": page,
    }, ensure_ascii=False)


def main():
    mcp.run()

if __name__ == "__main__":
    main()
