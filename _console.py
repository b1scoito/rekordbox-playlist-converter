"""Shared Rich console instance.

Every module that prints user-facing output imports the same Console so that
styling, width detection, and capture behave coherently. Lives at the package
root with a leading underscore to mark it as an internal detail.
"""

from rich.console import Console

console = Console()
