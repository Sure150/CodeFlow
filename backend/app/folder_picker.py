import json
import subprocess
import sys
from pathlib import Path


def choose_folder() -> str | None:
    # Tk needs the main thread. Keep its event loop separate from the API server.
    result = subprocess.run(
        [sys.executable, "-m", "app.folder_picker"],
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=180,
    )
    return json.loads(result.stdout)


def show_dialog() -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    window = tk.Tk()
    try:
        window.withdraw()
        window.attributes("-topmost", True)
        path = filedialog.askdirectory(
            parent=window,
            title="请选择 CodeFlow 项目文件夹",
            initialdir=str(Path.cwd()),
            mustexist=True,
        )
        return str(Path(path).absolute()) if path else None
    finally:
        window.destroy()


if __name__ == "__main__":
    # ASCII JSON keeps paths with non-ASCII characters independent of the console encoding.
    print(json.dumps(show_dialog(), ensure_ascii=True))
