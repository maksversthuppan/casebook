"""The PyInstaller-frozen desktop build (docs/desktop-app-roadmap.md Phase B).

Nothing here is imported by the normal ASGI app - `uv run uvicorn app.main:app`
never touches this package. Only `casebook.spec` points PyInstaller at
`entrypoint.py`.
"""
