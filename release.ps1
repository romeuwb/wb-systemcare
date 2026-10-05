# release.ps1 - WB SystemCare: build + git + GitHub Release automatico
# Uso:
#   powershell -ExecutionPolicy Bypass -File release.ps1           (minor: 1.5 -> 1.6)
#   powershell -ExecutionPolicy Bypass -File release.ps1 -Patch    (patch: 1.5 -> 1.5.1)
#   powershell -ExecutionPolicy Bypass -File release.ps1 -Major    (major: 1.5 -> 2.0)
#   powershell -ExecutionPolicy Bypass -File release.ps1 -Version "2.0"
#   powershell -ExecutionPolicy Bypass -File release.ps1 -DryRun   (simula sem alterar)

param(
    [string]$Version = "",
    [switch]$Patch,
    [switch]$Minor,
    [switch]$Major,
    [string]$Notes   = "",
    [switch]$DryRun
)

$py   = "C:\Users\romeu\AppData\Local\Programs\Python\Python312\python.exe"
$dir  = "d:\Projetos\limpaPC"
$repo = "romeuwb/wb-systemcare"
$site = "https://romeuwb.github.io/wb-systemcare/"

Set-Location $dir
$sep = "=" * 56

Write-Host $sep -ForegroundColor DarkYellow
Write-Host "  W.B. SystemCare - Release Automatico" -ForegroundColor Yellow
Write-Host $sep -ForegroundColor DarkYellow

# --- 1. Le versao atual do app.py ----------------------------------------
Write-Host ""
Write-Host "  [1/7] Lendo versao atual..." -ForegroundColor Cyan

$currentVer = "1.5"
$match = Select-String -Path "$dir\app.py" -Pattern 'CURRENT\s*=\s*"([\d\.]+)"' | Select-Object -First 1
if ($match -and $match.Line -match '"([\d\.]+)"') {
    $currentVer = $Matches[1]
}
Write-Host "  Versao atual: v$currentVer" -ForegroundColor Green

# --- 2. Calcula nova versao -----------------------------------------------
Write-Host "  [2/7] Calculando nova versao..." -ForegroundColor Cyan

if ($Version -ne "") {
    $newVer = $Version
} else {
    $parts = $currentVer -split '\.'
    $maj   = [int]($parts[0])
    $min   = if ($parts.Count -ge 2) { [int]($parts[1]) } else { 0 }
    $pat   = if ($parts.Count -ge 3) { [int]($parts[2]) } else { 0 }

    if ($Major) { $maj += 1; $min = 0; $pat = 0 }
    elseif ($Patch) { $pat += 1 }
    else { $min += 1; $pat = 0 }

    $newVer = if ($pat -gt 0) { "$maj.$min.$pat" } else { "$maj.$min" }
}

Write-Host "  Nova versao: v$newVer" -ForegroundColor Yellow

if ($DryRun) {
    Write-Host ""
    Write-Host "  [DryRun] Seria: v$currentVer -> v$newVer" -ForegroundColor Cyan
    Write-Host "  [DryRun] Nenhuma alteracao feita." -ForegroundColor Cyan
    exit 0
}

$confirm = Read-Host "  Publicar v$newVer? (S/N)"
if ($confirm -notmatch "^[Ss]") { Write-Host "  Cancelado."; exit 0 }

# --- 3. Atualiza versao no app.py -----------------------------------------
Write-Host "  [3/7] Atualizando versao em app.py..." -ForegroundColor Cyan

$content = Get-Content "$dir\app.py" -Raw -Encoding UTF8
$content = $content -replace '(CURRENT\s*=\s*)"[\d\.]+"',    ('${1}"' + $newVer + '"')
$content = $content -replace '(Versão\s*:\s*)[\d\.]+',        ('${1}' + $newVer)
$content = $content -replace '(text=f"v)[\d\.]+(\s*•)',       ('${1}' + $newVer + '${2}')
$content = $content -replace '(text="v)[\d\.]+(",)',           ('${1}' + $newVer + '${2}')
Set-Content "$dir\app.py" -Value $content -Encoding UTF8 -NoNewline
Write-Host "  app.py -> v$newVer" -ForegroundColor Green

# --- 4. Valida sintaxe ----------------------------------------------------
Write-Host "  [4/7] Validando sintaxe..." -ForegroundColor Cyan
$ok = $true
foreach ($f in @("theme_restore.py","file_scanner.py","tray_win32.py","user_manager.py","credential_helper.py","app.py")) {
    $out = & $py -c "import ast; ast.parse(open(r'$dir\$f','r',encoding='utf-8').read()); print('OK')" 2>&1
    if ($out -match "OK") { Write-Host "    OK: $f" -ForegroundColor Green }
    else { Write-Host "    ERRO: $f : $out" -ForegroundColor Red; $ok = $false }
}
if (-not $ok) { Write-Host "  Corrija os erros antes de publicar." -ForegroundColor Red; exit 1 }

# --- 5. Compila exe -------------------------------------------------------
Write-Host "  [5/7] Compilando WB_SystemCare.exe..." -ForegroundColor Cyan

if (Test-Path "$dir\build\WB_SystemCare") { Remove-Item "$dir\build\WB_SystemCare" -Recurse -Force }
if (Test-Path "$dir\WB_SystemCare.spec")  { Remove-Item "$dir\WB_SystemCare.spec" -Force }
if (Test-Path "$dir\dist\WB_SystemCare.exe") { Remove-Item "$dir\dist\WB_SystemCare.exe" -Force }

& $py -m PyInstaller `
    --onefile --windowed `
    --name "WB_SystemCare" `
    --icon "$dir\assets\logo.ico" `
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
    "$dir\app.py" | Out-Null

if (-not (Test-Path "$dir\dist\WB_SystemCare.exe")) {
    Write-Host "  ERRO: exe nao gerado." -ForegroundColor Red; exit 1
}
$mb = [math]::Round((Get-Item "$dir\dist\WB_SystemCare.exe").Length / 1MB, 1)
Write-Host "  WB_SystemCare.exe gerado (${mb} MB)" -ForegroundColor Green

# --- 6. Git commit + push -------------------------------------------------
Write-Host "  [6/7] Enviando para o GitHub..." -ForegroundColor Cyan

git add app.py README.md release.ps1 docs\index.html theme_restore.py file_scanner.py tray_win32.py user_manager.py credential_helper.py build_exe.ps1 .gitignore assets\logo.ico 2>&1 | Out-Null
$commitMsg = "v$newVer"
git commit -m $commitMsg 2>&1 | Out-Null
git push origin main 2>&1 | Out-Null
Write-Host "  Codigo enviado: $commitMsg" -ForegroundColor Green

# --- 7. Cria release no GitHub --------------------------------------------
Write-Host "  [7/7] Criando release v$newVer no GitHub..." -ForegroundColor Cyan

gh release delete "v$newVer" --yes 2>&1 | Out-Null
git tag -d "v$newVer" 2>&1 | Out-Null
git push origin ":refs/tags/v$newVer" 2>&1 | Out-Null

$date = (Get-Date).ToString("dd/MM/yyyy")
$releaseBody = "v$newVer - $date`nUsina da Paz Salinopolis - Sala de Tecnologia`nDesenvolvido por Waldemir`n`nSite: $site"
if ($Notes -ne "") { $releaseBody = "${Notes}`n`nSite: $site" }

gh release create "v$newVer" "$dir\dist\WB_SystemCare.exe" `
    --title "WB SystemCare v$newVer" `
    --notes $releaseBody 2>&1 | Out-Null

Write-Host "  Release v$newVer publicada!" -ForegroundColor Green

# --- Resumo ---------------------------------------------------------------
Write-Host ""
Write-Host $sep -ForegroundColor DarkYellow
Write-Host "  CONCLUIDO: v$currentVer -> v$newVer" -ForegroundColor Yellow
Write-Host "  Codigo  : https://github.com/$repo" -ForegroundColor Cyan
Write-Host "  Release : https://github.com/$repo/releases/tag/v$newVer" -ForegroundColor Cyan
Write-Host "  Site    : $site" -ForegroundColor Cyan
Write-Host "  EXE     : $dir\dist\WB_SystemCare.exe (${mb} MB)" -ForegroundColor Cyan
Write-Host $sep -ForegroundColor DarkYellow
