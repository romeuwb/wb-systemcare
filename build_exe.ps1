# build_exe.ps1 — Compila WB_SystemCare.exe com PyInstaller
# Uso: powershell -ExecutionPolicy Bypass -File build_exe.ps1

$py   = "C:\Users\romeu\AppData\Local\Programs\Python\Python312\python.exe"
$dir  = "d:\Projetos\limpaPC"
$name = "WB_SystemCare"
$icon = "$dir\assets\logo.ico"

$sep = "=" * 50
Write-Host $sep -ForegroundColor DarkYellow
Write-Host "  W.B. SystemCare -- Build Script" -ForegroundColor Yellow
Write-Host "  Dev: Waldemir (@romeuwb)" -ForegroundColor DarkYellow
Write-Host $sep -ForegroundColor DarkYellow
Write-Host ""

# ── Verifica Python ───────────────────────────────────────────────────────────
if (-not (Test-Path $py)) {
    Write-Host "[ERRO] Python nao encontrado em: $py" -ForegroundColor Red
    exit 1
}
$ver = & $py --version 2>&1
Write-Host "[OK] $ver" -ForegroundColor Green

# ── Verifica dependências ─────────────────────────────────────────────────────
Write-Host "[..] Verificando modulos..." -ForegroundColor Cyan
$modCheck = & $py -c "import tkinter, winreg, ctypes, os, shutil, threading, logging, subprocess; print('OK')" 2>&1
if ($modCheck -match "OK") {
    Write-Host "[OK] Todos os modulos disponiveis." -ForegroundColor Green
} else {
    Write-Host "[AVISO] $modCheck" -ForegroundColor Yellow
}

# ── Valida sintaxe ────────────────────────────────────────────────────────────
Write-Host "[..] Validando sintaxe..." -ForegroundColor Cyan
$allOk = $true
foreach ($f in @("theme_restore.py", "file_scanner.py", "tray_win32.py", "user_manager.py", "credential_helper.py", "app.py")) {
    $out = & $py -c "import ast, sys; ast.parse(open(r'$dir\$f','r',encoding='utf-8').read()); print('OK')" 2>&1
    if ($out -match "OK") {
        Write-Host "  [OK] $f" -ForegroundColor Green
    } else {
        Write-Host "  [ERRO] $f : $out" -ForegroundColor Red
        $allOk = $false
    }
}
if (-not $allOk) {
    Write-Host "[ERRO] Corriga os erros de sintaxe antes de compilar." -ForegroundColor Red
    exit 1
}

# ── Remove dist/build antigos ─────────────────────────────────────────────────
Write-Host "[..] Limpando builds anteriores..." -ForegroundColor Cyan
foreach ($old in @("$dir\dist\$name.exe", "$dir\dist\LimpaPC.exe")) {
    if (Test-Path $old) { Remove-Item $old -Force; Write-Host "  Removido: $old" }
}
if (Test-Path "$dir\build\$name") {
    Remove-Item "$dir\build\$name" -Recurse -Force
}
foreach ($spec in @("$dir\$name.spec","$dir\LimpaPC.spec")) {
    if (Test-Path $spec) { Remove-Item $spec -Force }
}

# ── Compila ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[..] Compilando $name.exe ..." -ForegroundColor Cyan
Write-Host ""

& $py -m PyInstaller `
    --onefile `
    --windowed `
    --name $name `
    --icon "$icon" `
    --add-data "$dir\theme_restore.py;." `
    --add-data "$dir\file_scanner.py;." `
    --add-data "$dir\tray_win32.py;." `
    --add-data "$dir\user_manager.py;." `
    --add-data "$dir\credential_helper.py;." `
    --add-data "$dir\assets\logo.ico;assets" `
    --clean `
    --distpath "$dir\dist" `
    --workpath "$dir\build" `
    --specpath "$dir" `
    "$dir\app.py"

# ── Resultado ─────────────────────────────────────────────────────────────────
Write-Host ""
$exe = "$dir\dist\$name.exe"
if (Test-Path $exe) {
    $mb  = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    $sep = "=" * 50
    Write-Host $sep -ForegroundColor DarkYellow
    Write-Host "  SUCESSO! ${name}.exe gerado (${mb} MB)" -ForegroundColor Yellow
    Write-Host "  Local: ${exe}" -ForegroundColor Yellow
    Write-Host $sep -ForegroundColor DarkYellow
} else {
    $sep = "=" * 50
    Write-Host $sep -ForegroundColor Red
    Write-Host "  ERRO: exe nao foi gerado. Veja o log acima." -ForegroundColor Red
    Write-Host $sep -ForegroundColor Red
    exit 1
}
