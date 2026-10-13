@echo off
title W.B. SystemCare - Publicar Nova Versao
cd /d "%~dp0"

:: Le a versao atual do app.py
for /f "tokens=*" %%i in ('C:\Users\romeu\AppData\Local\Programs\Python\Python312\python.exe -c "import re; m=re.search(r'APP_VERSION\s*=\s*\"([\d.]+)\"', open('app.py','r',encoding='utf-8').read()); print(m.group(1) if m else '?')"') do set CURRENT=%%i

:: Calcula proxima versao (minor+1)
for /f "tokens=1,2 delims=." %%a in ("%CURRENT%") do (
    set MAJOR=%%a
    set /a MINOR=%%b+1
)
set NEXT=%MAJOR%.%MINOR%

:: Calcula versao de patch
for /f "tokens=1,2 delims=." %%a in ("%CURRENT%") do (
    set PMAJOR=%%a
    set PMINOR=%%b
)
set PATCH=%PMAJOR%.%PMINOR%.1

echo.
echo  ================================================
echo   W.B. SystemCare - Publicar Nova Versao
echo   Versao atual: v%CURRENT%
echo  ================================================
echo.
echo  Opcoes:
echo.
echo  [1] Proxima versao normal    v%CURRENT% -^> v%NEXT%
echo  [2] Correcao de bug          v%CURRENT% -^> v%PATCH%
echo  [3] Simular sem publicar nada (DryRun)
echo  [0] Cancelar
echo.
set /p opcao="  Escolha: "

if "%opcao%"=="1" (
    powershell -ExecutionPolicy Bypass -File "%~dp0release.ps1"
) else if "%opcao%"=="2" (
    powershell -ExecutionPolicy Bypass -File "%~dp0release.ps1" -Patch
) else if "%opcao%"=="3" (
    powershell -ExecutionPolicy Bypass -File "%~dp0release.ps1" -DryRun
    pause
) else (
    echo  Cancelado.
)

pause
