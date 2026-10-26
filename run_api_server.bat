@echo off
cd /d "C:\Users\harsh\Documents\Comfyui_old"
.\python_embeded\python.exe .\ComfyUI\main.py --port 8190 --lowvram --disable-smart-memory --dont-print-server --preview-method auto
echo ----------------------------------------------------
echo ComfyUI is now running as a Headless API Server.
echo (Browser will not open. Close this window to stop)
echo ----------------------------------------------------
pause