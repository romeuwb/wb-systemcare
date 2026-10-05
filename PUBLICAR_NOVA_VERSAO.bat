@echo off
title W.B. SystemCare - Publicar Nova Versao
cd /d "%~dp0"

echo.
echo  ================================================
echo   W.B. SystemCare - Publicar Nova Versao
echo   Usina da Paz Salinopolis
echo  ================================================
echo.
echo  Opcoes:
echo.
echo  [1] Publicar proxima versao normal  (ex: 1.5 -^> 1.6)
echo  [2] Publicar correcao de bug        (ex: 1.5 -^> 1.5.1)
echo  [3] Simular sem publicar nada       (DryRun)
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
