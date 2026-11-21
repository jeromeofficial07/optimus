"""
The complete list of actions OPTIMUS can perform. To add a new capability later:
write the function, then register it here with a risk level. Nothing else can run.
"""
from app.agent.registry import Param, Risk, Tool, ToolError, ToolRegistry
from app.agent.workflows import WORKFLOWS
from app.config import WORKSPACES
from app.tools import apps, files, system, workspace


def _handled_by_controller(ctx, **kwargs):
    """run_workflow is intercepted by the ExecutionController and never reaches here."""
    raise ToolError("Workflows are run by the execution controller.")


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(Tool(
        name="open_application",
        description="Open an approved desktop application such as Notepad, Calculator, Paint, "
                    "Chrome, Edge, VS Code, Word or File Explorer.",
        func=apps.open_application,
        params=(Param("name", "string", "Name of the application, for example 'notepad'"),),
        status_text="Opening {name}...",
    ))
    registry.register(Tool(
        name="close_application",
        description="Close a running approved application. Unsaved work in it may be lost.",
        func=apps.close_application,
        params=(Param("name", "string", "Name of the application to close"),),
        risk=Risk.DESTRUCTIVE,
        status_text="Closing {name}...",
        confirm_text="Close {name}? Any unsaved work in it will be lost.",
    ))
    registry.register(Tool(
        name="list_supported_apps",
        description="List the applications OPTIMUS is allowed to open.",
        func=apps.list_supported_apps,
        status_text="Checking approved applications...",
    ))
    registry.register(Tool(
        name="search_files",
        description="Search the user's configured folders for files or folders by name.",
        func=files.search_files,
        params=(
            Param("query", "string", "Words that appear in the file or folder name", max_length=100),
            Param("kind", "string", "Search files, folders or both", required=False,
                  enum=("any", "file", "folder")),
        ),
        status_text="Searching for '{query}'...",
    ))
    registry.register(Tool(
        name="open_search_result",
        description="Open one item from the most recent file search, by its number in the list.",
        func=files.open_search_result,
        params=(Param("number", "integer", "The number of the search result", minimum=1, maximum=50),),
        status_text="Opening result {number}...",
    ))
    registry.register(Tool(
        name="open_path",
        description="Open a specific file or folder given its full path.",
        func=files.open_path,
        params=(Param("path", "string", "Full path of the file or folder", path=True, max_length=400),),
        status_text="Opening the item...",
    ))
    registry.register(Tool(
        name="take_screenshot",
        description="Take a screenshot of the screen and save it as an image file.",
        func=system.take_screenshot,
        status_text="Taking a screenshot...",
    ))
    registry.register(Tool(
        name="get_system_usage",
        description="Report current CPU usage, memory (RAM) usage and disk usage of this computer.",
        func=system.get_system_usage,
        status_text="Checking CPU and memory...",
    ))
    registry.register(Tool(
        name="get_battery_status",
        description="Report the battery level and whether the laptop is charging.",
        func=system.get_battery_status,
        status_text="Checking the battery...",
    ))
    registry.register(Tool(
        name="lock_computer",
        description="Lock the Windows session so a password or PIN is needed to continue.",
        func=system.lock_computer,
        risk=Risk.SENSITIVE,
        status_text="Locking the computer...",
        confirm_text="Lock this computer now? You will need your password or PIN to unlock it.",
    ))

    # ---- Phase 6: workspace tools and approved workflows
    registry.register(Tool(
        name="get_workspace",
        description="Identify the configured project workspace folder, for example the Python workspace.",
        func=workspace.get_workspace,
        params=(Param("kind", "string", "Kind of workspace, for example 'python'",
                      enum=tuple(WORKSPACES)),),
        status_text="Identifying the {kind} workspace...",
    ))
    registry.register(Tool(
        name="open_in_vscode",
        description="Open a project folder in Visual Studio Code.",
        func=workspace.open_in_vscode,
        params=(Param("path", "string", "Full path of the project folder", path=True, max_length=400),),
        status_text="Opening the project in VS Code...",
    ))
    registry.register(Tool(
        name="check_python_environment",
        description="Inspect a Python project folder: virtual environment, Python version and "
                    "whether the packages in requirements.txt are installed.",
        func=workspace.check_python_environment,
        params=(Param("path", "string", "Full path of the project folder", path=True, max_length=400),),
        status_text="Checking the project environment...",
    ))
    registry.register(Tool(
        name="run_workflow",
        description="Run an approved multi-step workflow. Available: "
                    + "; ".join(f"{w.name} ({w.description})" for w in WORKFLOWS.values()),
        func=_handled_by_controller,
        params=(Param("name", "string", "Name of the workflow", enum=tuple(WORKFLOWS)),),
        status_text="Starting the workflow...",
    ))
    return registry