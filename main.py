"""Entry point.

The pyproject `[project.scripts]` table binds `rekordbox-converter = "main:app"`,
so `app` must live here. Everything else is in `cli.py` / `converter.py` /
`quality.py` / `models.py`.
"""

from cli import app

if __name__ == "__main__":
    app()
