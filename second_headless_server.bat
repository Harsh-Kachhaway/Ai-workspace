@echo off
cd /d "C:\Users\harsh\Documents\Comfyui_old"

set PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

.\python_embeded\python.exe .\ComfyUI\main.py ^
--port 8190 ^
--lowvram ^
--reserve-vram 0.5 ^
--preview-method auto ^
--dont-print-server

pause