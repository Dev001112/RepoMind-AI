"""Convenience entrypoint: `python app.py` starts the dev server (same app as
`uvicorn app.main:app --reload`, just without needing to remember/type that).
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        # Without this, --reload watches the ENTIRE working directory by default --
        # including backend/repositories/, where `git clone` writes hundreds of files
        # per analysis run. Every one of those file-creation events queues a reload,
        # which kills and restarts the whole server MID-BACKGROUND-TASK, silently
        # corrupting whatever analysis pipeline run was in flight. Only app/ contains
        # source code that should ever trigger a reload.
        reload_dirs=["app"],
    )
