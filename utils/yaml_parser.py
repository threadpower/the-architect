"""
The Architect — YAML Task Parser
Parses task YAML files with security validation.
Tasks are loaded ONLY from the registered tasks directory.
"""
import yaml
from pathlib import Path
from architect.models.task import Task


# Tasks can ONLY be loaded from this directory
TASKS_DIR = Path("/forge/architect/tasks")


class TaskParseError(Exception):
    """Raised when a task YAML is invalid or insecure."""
    pass


def parse_task_yaml(content: str) -> Task:
    """
    Parse a YAML string into a validated Task object.
    
    Security: This parses content directly, not file paths.
    The caller is responsible for loading from a safe location.
    """
    try:
        raw = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise TaskParseError(f"Invalid YAML: {e}")

    if not isinstance(raw, dict):
        raise TaskParseError("Task YAML must be a mapping at top level")

    # Support both top-level and nested "task:" key
    if "task" in raw:
        raw = raw["task"]

    try:
        return Task(**raw)
    except Exception as e:
        raise TaskParseError(f"Task validation failed: {e}")


def load_task_file(task_id: str) -> Task:
    """
    Load a task from the registered tasks directory by ID or filename.
    
    Security: Only loads from TASKS_DIR. No path traversal.
    """
    # Sanitize: strip path separators and dots
    safe_name = task_id.replace("/", "").replace("\\", "").replace("..", "")
    
    # Try exact filename, then with .yaml extension
    candidates = [
        TASKS_DIR / safe_name,
        TASKS_DIR / f"{safe_name}.yaml",
        TASKS_DIR / f"{safe_name}.yml",
    ]

    for path in candidates:
        # Extra safety: resolve and verify it's still under TASKS_DIR
        resolved = path.resolve()
        if not str(resolved).startswith(str(TASKS_DIR.resolve())):
            raise TaskParseError(f"Path traversal detected: {task_id}")
        
        if resolved.is_file():
            return parse_task_yaml(resolved.read_text())

    raise TaskParseError(
        f"Task not found: {task_id} (searched in {TASKS_DIR})"
    )
