# CodeFlow

CodeFlow 静态分析 Python 项目。输入目录后，可以搜索函数、浏览直接调用关系并查看源码位置。分析过程只读取源码。

## Windows 一键启动

安装 Python 3.11+ 和 Node.js 22.12+（含 npm）后，双击仓库根目录的 `start.bat`。启动器会使用现有的 `backend/.venv`，首次没有虚拟环境时会自动创建。首次准备依赖时需要联网。前后端就绪后，启动器会打开 `http://127.0.0.1:5173/`。

在页面输入 `samples/python_basic` 即可试用。要停止服务，关闭「CodeFlow Backend」和「CodeFlow Frontend」两个窗口。

## 本地开发

需要 Python 3.11+ 和 Node.js 22.12+。在仓库根目录启动后端。

```sh
python -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -e ./backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload --reload-dir backend
```

Windows PowerShell 使用 `.\backend\.venv\Scripts\Activate.ps1` 激活虚拟环境。

另开一个终端启动前端。

```sh
cd frontend
npm ci
npm run dev
```

打开 Vite 输出的本地地址，在「项目目录」输入 `samples/python_basic` 并点击「扫描项目」。相对路径以 FastAPI 启动目录为基准。使用云端后端时，也可以直接输入云机器上的绝对路径。

样例中 `format_message` 调用了两个名为 `normalize` 的函数，分别位于 `main.py` 和 `helpers.py`。点击图中的函数可以查看源码和反向调用关系。回调 `callback` 会出现在「未解析调用点」里，点击可以定位该调用行。

## 分析范围

- 扫描 `.py` 文件，跳过常见的虚拟环境、缓存和构建目录，以及子目录中的符号链接。
- 提取函数、方法、嵌套函数及其源码位置。用 AST 和符号表解析对模块级函数的直接调用，支持普通导入、导入别名和包内相对导入。
- 动态回调、实例方法分派、第三方调用和其他无法确定的目标会保留为未解析调用点。首版统计函数体内的调用。模块路径以扫描目录推导，`src` 布局可直接扫描 `src/`。
- 语法错误、读取失败和扫描截断会出现在扫描提示中。
- 使用适合扫描当前机器文件的本机开发模式。前端通过 Vite 代理调用 `POST /api/analyze`，请求体为 `{"path":"samples/python_basic"}`。FastAPI 默认由上述命令绑定到环回地址。

## 验证

激活虚拟环境并在仓库根目录运行后端测试。

```sh
python -m unittest discover -s backend/tests -v
```

在 `frontend/` 下运行 `npm run build` 完成类型检查和构建。
