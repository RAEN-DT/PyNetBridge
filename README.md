<p align="center">
  <img src="https://github.com/rafa2403nunez-droid/PyNetBridge/blob/main/Assets/PyNetBridge.png" width="300"/>
</p>


# 🐍 PyNet Platform Bridge

**PyNet Platform Bridge** is the execution layer that allows AI models to control Autodesk tools in real-time.

It connects Natural Language → Python → Autodesk desktop tools (Navisworks, Revit, AutoCAD), enabling AI to generate, execute, and refine BIM workflows autonomously.

Available integrations include **Navisworks Manage**, **Revit**, and **Civil 3D**.

This bridge acts as the connective tissue between AI logic and Autodesk desktop APIs, allowing for dynamic UI creation, script execution, and BIM process automation using natural language.


| Tutorial | Description | Video |
| :--- | :--- | :--- |
| **PyNET and Codex Integration** | How to configure PyNet bridge with Codex and query into Navisworks. | [🎬 Watch here](https://youtu.be/HdmbCO_pTN0)  |

## 🔄 How it works

1. The user describes a task in natural language.  
2. The AI generates a Python script.
3. PyNet Bridge validates and sends the script.
4. The PyNet plugin executes it inside Autodesk.
5. Results are returned back to the AI.

This is what turns AI from a chatbot into an execution engine for BIM.

---

## 🚀 What makes PyNet Bridge powerful

* **AI → Action:** Turns AI-generated code into real actions inside Navisworks/Revit  
* **Real-time Execution:** Run scripts instantly without leaving the BIM environment  
* **Dynamic UI Creation:** Let AI create tools, buttons and workflows on the fly  
* **Reliable Communication:** Fast and stable local IPC  
* **Model-Aware Automation:** Operates directly on live BIM models  

---

## 🛠️ Installation

### ✅ Option A — Automatic installer (recommended)

Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/rafa2403nunez-droid/PyNetBridge/main/install.ps1 | iex
```

This will automatically:
1. Check Python 3.10+ is installed
2. Install `pynet-mcp-bridge` from PyPI (via `uv` or `pip`)
3. Auto-detect and configure all installed AI clients:
   - **Claude Desktop** (standard and Microsoft Store versions)
   - **Claude Code** (VS Code extension / CLI)
   - **Cline** (VS Code extension)
   - **Roo Code** (VS Code extension)
   - **Codex CLI** (`~/.codex/config.toml`)

The `pynet-mcp-bridge` package includes:
| Package | Purpose |
| :--- | :--- |
| **pynet-mcp-bridge** | MCP server that connects AI models with Autodesk tools via PyNET |
| **mcp[cli]** | Model Context Protocol SDK and CLI tools |
| **fastmcp** | High-level MCP server framework |
| **psutil** | System process detection (finds running Autodesk instances) |

> Restart your AI client(s) after installation to apply changes.

### 📦 Python Libraries Starter Pack (optional)

Install the recommended Python libraries for Navisworks, Revit and Civil 3D scripting with PyNET:

```powershell
irm https://raw.githubusercontent.com/rafa2403nunez-droid/PyNetBridge/main/install-libraries.ps1 | iex
```

This installs:
| Library | Purpose |
| :--- | :--- |
| **pandas** | Data analysis and manipulation |
| **plotly** | Interactive charts and visualizations |
| **matplotlib** | Static plots and graphs |
| **dash** | Web dashboards from Python |

> These are the third-party libraries listed under [Allowed Python Imports](#allowed-python-imports). Standard library modules (`json`, `sys`, `re`, etc.) are already included with Python.

### Prerequisites
* **PyNet Platform** plugin installed in Navisworks/Revit.
* Python 3.10 or higher → [python.org](https://www.python.org/downloads/)
  > ⚠️ **Python 3.14 is not yet supported.** The `pythonnet` runtime currently supports Python 3.7 through 3.13. If you encounter a `System.NotSupportedException` mentioning an unsupported ABI version, install Python 3.12 or 3.13 and configure PyNet to use it.
* **uv** → [docs.astral.sh/uv](https://docs.astral.sh/uv/)
* **Git** → [git-scm.com](https://git-scm.com/downloads) — required for VS Code extensions (Claude Code, Cline, Roo Code) to function correctly.
* For Cline / Roo Code: **VS Code** → [code.visualstudio.com](https://code.visualstudio.com/)

---

### 🔧 Option B — Manual installation

**1. Install the package:**

```bash
uv tool install pynet-mcp-bridge
```

Or with pip:

```bash
pip install pynet-mcp-bridge
```

**2. Configure Claude Desktop:**

Add the following to your `claude_desktop_config.json`:
- Standard: `%APPDATA%\Claude\claude_desktop_config.json`
- Microsoft Store: `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "pynet-bridge": {
      "command": "pynet-bridge",
      "args": []
    }
  }
}
```

**3. Configure Claude Code (VS Code extension):**

Add to `%USERPROFILE%\.claude.json`:

```json
{
  "mcpServers": {
    "pynet-bridge": {
      "type": "stdio",
      "command": "pynet-bridge",
      "args": []
    }
  }
}
```

**4. Configure Cline:**

Add to `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`:

```json
{
  "mcpServers": {
    "pynet-bridge": {
      "type": "stdio",
      "command": "pynet-bridge",
      "args": []
    }
  }
}
```

**5. Configure Roo Code:**

Add to `%APPDATA%\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\mcp_settings.json`:

```json
{
  "mcpServers": {
    "pynet-bridge": {
      "type": "stdio",
      "command": "pynet-bridge",
      "args": []
    }
  }
}
```

**6. Configure Codex CLI:**

Add to `%USERPROFILE%\.codex\config.toml`:

```toml
[mcp_servers.pynet-bridge]
command = "C:/Users/<user>/.local/bin/pynet-bridge.exe"
args = []
```

---

## 🛠️ Available MCP Tools

These tools allow AI to fully control the PyNet environment, from UI creation to script execution and system monitoring.
Once connected, the AI will have access to the full suite of PyNet tools:

### 🧠 Core capabilities exposed to AI

### 🔍 System & Connection
* **list_active_instances**: Scans the system for running Autodesk processes with an active PyNet connection.
* **check_plugin_status**: Handshake ping to verify the plugin listener is responsive.

### 🏗️ Module (Tab) Management
* **get_pynet_ui_layout**: Fetches the full UI structure (ButtonsModules and ScriptButtons).
* **create_pynet_module**: Creates a new custom Tab (ButtonsModule) in the Ribbon.
* **delete_pynet_module**: Permanently deletes a module and all its contents.

### 🔘 Button Management
* **get_buttons_data**: Lists all script buttons for a specific module ID.
* **deploy_script_button**: Installs a new ScriptButton into a specific module (Name, Script, Icon, Tooltip).
* **update_script_button**: Updates metadata for an existing ScriptButton or moves it to another module.
* **delete_script_button**: Permanently removes a ScriptButton from a module by Id.

### 💻 Execution & Console Control
* **send_command**: Direct script execution in the PyNet engine (Target PID, Script Name, Content).
* **get_output_window_status**: Checks if the output window is currently available/visible.
* **configure_output_window**: Toggles the visibility of the PyNet log/output window.

---

## 🛡️ Safe AI Execution

PyNet Bridge includes a built-in validation layer that ensures all AI-generated scripts are safe and controlled before execution.

✔ Prevents unsafe operations  
✔ Blocks unauthorized system access  
✔ Guarantees controlled interaction with BIM models  

**AI remains powerful**, but within safe boundaries

Starting from **v1.1.1**, the MCP server includes a built-in static analyzer that validates every script before it reaches the Autodesk host. All scripts are parsed and inspected at the bridge level — **rejected scripts never leave the MCP server**.

### Allowed CLR Assemblies
Only these .NET references are permitted via `clr.AddReference`:
- **Common:** `System`, `System.Windows.Forms`, `System.Drawing`, `System.Collections.Generic`
- **Navisworks:** `Autodesk.Navisworks.Api`, `.ComApi`, `.Interop.ComApi`, `.Clash`
- **Revit:** `RevitAPI`, `RevitAPIUI`
- **AutoCAD / Civil 3D:** `AcMgd`, `AcCoreMgd`, `AcDbMgd`, `AecBaseMgd`, `AecPropDataMgd`, `AeccDbMgd`
- **PyNet plugins:** `Raen.Core.Pynet.*`, `Raen.{Product}.Pynet.*` (any version — e.g. `Raen.Core.Pynet.Resources`, `Raen.Navisworks.Pynet.2024`, `Raen.Civil3D.Pynet.2026`)

### Allowed Python Imports
`clr`, `sys`, `json`, `re`, `time`, `datetime`, `pathlib`, `typing`, `threading`, `collections`, `xml`, `math`, `pandas`, `plotly`, `matplotlib`, `dash`, `webbrowser`, `psutil`, `functools`

### Allowed Python Submodules
Some modules are allowed at the submodule level only, preventing access to dangerous siblings:

| Allowed | Blocked | Reason |
| :--- | :--- | :--- |
| `http.server` | `http.client`, `http.cookiejar` | Allow local HTTP serving, block outbound requests |

### Blocked Python Imports
`os`, `subprocess`, `shutil`, `socket`, `ctypes`, `pickle`, `importlib`, `urllib`, `signal`, `multiprocessing`, `tempfile`, `glob`, `inspect`, `code`, `codeop`

### Blocked Calls
`eval`, `exec`, `compile`, `__import__`, `getattr`, `setattr`, `delattr`, `globals`, `locals`, `vars`, `breakpoint`, `open`

### Blocked Attribute Access
`__builtins__`, `__subclasses__`, `__globals__`, `__code__`

> Any script that violates these rules is immediately rejected with a descriptive error message, without ever being sent to the plugin.

---

## 📂 Project Structure

* **pynet_mcp/**: Core MCP server logic (FastMCP).
* **pyproject.toml**: Package configuration and dependency management.

---

## 📥 Getting Started

Start building autonomous BIM workflows in minutes.

Install the bridge, connect your AI client, and turn natural language into real actions inside your models.

---

## ❓ FAQs

Have questions about installation, configuration, or usage? Check the full FAQ page:

👉 [PyNet FAQs](https://github.com/rafa2403nunez-droid/PyNet/wiki/PyNET-FAQs)

---

## 🔗 How This MCP Fits Into the Ecosystem

This MCP is part of a modular system designed to enable AI-driven BIM automation across Autodesk tools.

This repository is designed to work alongside:

- PyNet Platform → Executes scripts inside Navisworks, Revit & Civil 3D via Python.NET  
- PyNet Library → Gives the AI context with a Python scripts library 

Together, these components enable:

Natural Language → AI → Python Script → PyNet → Autodesk → BIM Action

| Component | Repository | Purpose |
| :--- | :--- | :--- |
| **PyNet Platform** | [rafa2403nunez-droid/PyNet](https://github.com/rafa2403nunez-droid/PyNet) | Navisworks, Revit & Civil 3D plugin — hosts the Python.NET engine |
| **PyNet Bridge (MCP)** | This repo | MCP server - connects AI models to PyNET with including secure scripts validation|
| **PyNet Library** | [rafa2403nunez-droid/PyNetLibrary](https://github.com/rafa2403nunez-droid/PyNetLibrary) | Script reference library and AI context |


## 📄 License

This project is licensed under the MIT License.

---

mcp-name: io.github.rafa2403nunez-droid/pynet-mcp-bridge

© 2026 RAEN Digital Tools. Todos los derechos reservados.
Obra inscrita en el Registro de la Propiedad Intelectual de la Comunidad de Madrid.

<p align="center">
  <img src="https://github.com/rafa2403nunez-droid/PyNetBridge/blob/main/Assets/RAENDigitalTools.png" alt="RAEN Digital Tools" width="200">
</p>
