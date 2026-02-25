@echo off
echo --- CREANDO ENTORNO VIRTUAL ---
call conda create -n easy_whisper -y
call conda activate easy_whisper

echo --- INSTALANDO DEPENDENCIAS ---
call cd setup
call python cuda_test_install.py
pause

call python other_libs.py
pause
call conda deactivate

echo --- CREANDO ACCESO DIRECTO EN EL ESCRITORIO ---
set BAT_TARGET=%~dp0start_app.vbs
set ICONO=%~dp0easywhisper\logo.ico
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $WshShell = New-Object -ComObject WScript.Shell; $desktop = [Environment]::GetFolderPath('Desktop'); $lnk = Join-Path $desktop 'Easy_Whisper.lnk'; $s = $WshShell.CreateShortcut($lnk); $s.TargetPath = '%BAT_TARGET%'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%ICONO%'; $s.Save() }"

echo --- PROCESO FINALIZADO ---
pause