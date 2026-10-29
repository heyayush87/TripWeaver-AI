"""Local development launcher: `uv run app.py`."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "tripweaver.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
