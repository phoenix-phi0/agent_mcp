@echo off
chcp 65001 >nul
REM 打包 JP-E01-π 桌面程序
REM 用法：在项目根目录（mcp\）执行 build.bat

echo === 检查依赖 ===
py -c "import webview" 2>nul || (echo 缺 pywebview，执行：pip install pywebview & exit /b 1)
py -c "import PyInstaller" 2>nul || (echo 缺 pyinstaller，执行：pip install pyinstaller & exit /b 1)

echo === 清理旧构建 ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo === 打包 ===
REM SOUL.md 跟代码走，打包进去
REM flows / verbs / workspace / config.json 不打包，放在 exe 旁边供用户编辑
py -m PyInstaller ^
  --noconfirm ^
  --noconsole ^
  --onefile ^
  --name "日语教师" ^
  --add-data "agents\souls;agents\souls" ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  agents\app.py

if errorlevel 1 (echo 打包失败 & exit /b 1)

echo === 复制可编辑资源到 dist ===
xcopy /e /i /y flows dist\flows >nul
xcopy /e /i /y verbs dist\verbs >nul
xcopy /e /i /y workspace dist\workspace >nul
if exist config.json (
  echo 注意：config.json 含 API Key，没有自动复制。
  echo 请手动放一份到 dist\ ，或在程序里配置。
)

echo.
echo === 完成 ===
echo 产物在 dist\ 目录：
echo   日语教师.exe
echo   flows\      教学流程，可直接编辑 .zs
echo   verbs\      动词包，可直接编辑 .py
echo   workspace\  教材与学习进度
echo   config.json 需要你手动放进去
echo.
echo 整个 dist 目录一起分发；改 flows 或 verbs 后重开程序即可生效。
pause
