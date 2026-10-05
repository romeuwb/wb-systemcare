# ============================================================
# release.ps1 — WB SystemCare: build + git + GitHub Release
# Uso: powershell -ExecutionPolicy Bypass -File release.ps1
#      powershell -ExecutionPolicy Bypass -File release.ps1 -Version "1.6"
#      powershell -ExecutionPolicy Bypass -File release.ps1 -Patch
# ============================================================

param(
    [string]$Version  = "",     # Força uma versão específica, ex: "1.6"
    [switch]$Patch,             # Incrementa só o patch: 1.5 → 1.5.1
    [switch]$Minor,             # Incrementa minor: 1.5 → 1.6  (padrão)
    [switch]$Major,             # Incrementa major: 1.5 → 2.0
    [string]$Notes    = "",     # Notas da release (opcional)
    [switch]$DryRun             # Simula sem fazer alterações
)

$py    = "C:\Users\romeu\AppData\Local\Programs\Python\Python312\python.exe"
$dir   = "d:\Projetos\limpaPC"
$repo  = "romeuwb/wb-systemcare"
$pages = "https://romeuwb.github.io/wb-systemcare/"

Set-Location $dir

$sep = "=" * 56

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "  $msg" -ForegroundColor Yellow
}
function Write-OK([string]$msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
}
function Write-Fail([string]$msg) {
    Write-Host "  [ERRO] $msg" -ForegroundColor Red
    exit 1
}

Write-Host $sep -ForegroundColor DarkYellow
Write-Host "  W.B. SystemCare — Release Automatico" -ForegroundColor Yellow
Write-Host "  Dev: Waldemir (@romeuwb)" -ForegroundColor DarkYellow
Write-Host $sep -ForegroundColor DarkYellow

# ── 1. Lê a versão atual do app.py ───────────────────────────────────────────
Write-Step "Lendo versao atual..."

$currentLine = Select-String -Path "$dir\app.py" -Pattern 'CURRENT\s*=\s*"[\d\.]+"' | Select-Object -First 1
if (-not $currentLine) {
    # Fallback: busca no cabeçalho do arquivo
    $currentLine = Select-String -Path "$dir\app.py" -Pattern 'Versão\s*:\s*[\d\.]+' | Select-Object -First 1
}

# Extrai a versão do texto encontrado
$currentVer = ""
if ($currentLine) {
    if ($currentLine.Line -match '"([\d\.]+)"') {
        $currentVer = $Matches[1]
    } elseif ($currentLine.Line -match ':\s*([\d\.]+)') {
        $currentVer = $Matches[1].Trim()
    }
}

if (-not $currentVer) {
    $currentVer = "1.5"
    Write-Host "  Versao atual nao detectada, assumindo $currentVer" -ForegroundColor DarkYellow
} else {
    Write-OK "Versao atual: v$currentVer"
}

# ── 2. Calcula nova versão ────────────────────────────────────────────────────
Write-Step "Calculando nova versao..."

if ($Version -ne "") {
    $newVer = $Version
} else {
    $parts = $currentVer -split '\.'
    $major = [int]($parts[0])
    $minor = if ($parts.Count -ge 2) { [int]($parts[1]) } else { 0 }
    $patch = if ($parts.Count -ge 3) { [int]($parts[2]) } else { 0 }

    if ($Major) {
        $major += 1; $minor = 0; $patch = 0
    } elseif ($Patch) {
        $patch += 1
    } else {
        # Padrão: incrementa minor
        $minor += 1; $patch = 0
    }

    $newVer = if ($patch -gt 0) { "$major.$minor.$patch" } else { "$major.$minor" }
}

Write-OK "Nova versao: v$newVer"

if ($DryRun) {
    Write-Host ""
    Write-Host "  [DryRun] Seria: v$currentVer -> v$newVer" -ForegroundColor Cyan
    Write-Host "  [DryRun] Nenhuma alteracao feita." -ForegroundColor Cyan
    exit 0
}

# Confirmação
$confirm = Read-Host "  Publicar v$newVer? (S/N)"
if ($confirm -notmatch '^[Ss]') {
    Write-Host "  Cancelado." -ForegroundColor DarkYellow
    exit 0
}

# ── 3. Atualiza versão no app.py ──────────────────────────────────────────────
Write-Step "Atualizando versao no app.py..."

$appContent = Get-Content "$dir\app.py" -Raw -Encoding UTF8

# Atualiza CURRENT = "x.x" no _update_check
$appContent = $appContent -replace '(CURRENT\s*=\s*)"[\d\.]+"', "`${1}`"$newVer`""

# Atualiza "vX.X" no _build_page_update
$appContent = $appContent -replace '(text=")v[\d\.]+(", bg=C\["bg_card"\],\s*\n\s*fg=C\["accent"\], font=\("Segoe UI", 22)', "`${1}v$newVer`${2}"

# Atualiza versão no cabeçalho do docstring
$appContent = $appContent -replace '(Versão\s*:\s*)[\d\.]+', "`${1}$newVer"

# Atualiza no header do app (v1.x no label)
$appContent = $appContent -replace '("v)[\d\.]+(\s*•\s*")', "`${1}$newVer`${2}"
$appContent = $appContent -replace '(text=f"v)[\d\.]+(\s*•)', "`${1}$newVer`${2}"

Set-Content "$dir\app.py" -Value $appContent -Encoding UTF8 -NoNewline
Write-OK "app.py atualizado para v$newVer"

# ── 4. Valida sintaxe ──────────────────────────────────────────────────────────
Write-Step "Validando sintaxe..."

$allOk = $true
foreach ($f in @("theme_restore.py","file_scanner.py","tray_win32.py","user_manager.py","credential_helper.py","app.py")) {
    $out = & $py -c "import ast; ast.parse(open(r'$dir\$f','r',encoding='utf-8').read()); print('OK')" 2>&1
    if ($out -match "OK") {
        Write-OK $f
    } else {
        Write-Host "  [ERRO] ${f}: $out" -ForegroundColor Red
        $allOk = $false
    }
}
if (-not $allOk) { Write-Fail "Corrija os erros de sintaxe antes de publicar." }

# ── 5. Compila o .exe ──────────────────────────────────────────────────────────
Write-Step "Compilando WB_SystemCare.exe..."

# Remove build anterior
if (Test-Path "$dir\build\WB_SystemCare") {
    Remove-Item "$dir\build\WB_SystemCare" -Recurse -Force
}
if (Test-Path "$dir\WB_SystemCare.spec") {
    Remove-Item "$dir\WB_SystemCare.spec" -Force
}
if (Test-Path "$dir\dist\WB_SystemCare.exe") {
    Remove-Item "$dir\dist\WB_SystemCare.exe" -Force
}

& $py -m PyInstaller `
    --onefile `
    --windowed `
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
    Write-Fail "Falha na compilacao — exe nao gerado."
}

$mb = [math]::Round((Get-Item "$dir\dist\WB_SystemCare.exe").Length / 1MB, 1)
Write-OK "WB_SystemCare.exe gerado (${mb} MB)"

# ── 6. Git commit + push ──────────────────────────────────────────────────────
Write-Step "Enviando codigo para o GitHub..."

git add app.py README.md docs\index.html 2>&1 | Out-Null
git add theme_restore.py file_scanner.py tray_win32.py user_manager.py credential_helper.py build_exe.ps1 .gitignore assets\logo.ico 2>&1 | Out-Null

$commitMsg = "v$newVer - release automatica"
git commit -m $commitMsg 2>&1 | Out-Null
git push origin main 2>&1 | Out-Null

Write-OK "Codigo enviado: $commitMsg"

# ── 7. Cria release no GitHub com o .exe ─────────────────────────────────────
Write-Step "Criando release v$newVer no GitHub..."

# Remove release anterior com a mesma tag, se existir
gh release delete "v$newVer" --yes 2>&1 | Out-Null
git tag -d "v$newVer" 2>&1 | Out-Null
git push origin ":refs/tags/v$newVer" 2>&1 | Out-Null

# Monta as notas da release
$date = (Get-Date).ToString("dd/MM/yyyy")
if ($Notes -eq "") {
    $releaseNotes = "v$newVer — $date

Usina da Paz Salinopolis — Sala de Tecnologia
Desenvolvido por Waldemir (@romeuwb)

Site oficial: $pages
Repositorio: https://github.com/$repo"
} else {
    $releaseNotes = "$Notes

Site oficial: $pages"
}

# Cria a nova release
$result = gh release create "v$newVer" "$dir\dist\WB_SystemCare.exe" `
    --title "WB SystemCare v$newVer" `
    --notes $releaseNotes 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-OK "Release v$newVer publicada: https://github.com/$repo/releases/tag/v$newVer"
} else {
    Write-Host "  [AVISO] $result" -ForegroundColor Yellow
}

# ── 8. Resumo final ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host $sep -ForegroundColor DarkYellow
Write-Host "  CONCLUIDO: v$currentVer --> v$newVer" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Codigo  : https://github.com/$repo" -ForegroundColor Cyan
Write-Host "  Release : https://github.com/$repo/releases/tag/v$newVer" -ForegroundColor Cyan
Write-Host "  Site    : $pages" -ForegroundColor Cyan
Write-Host "  EXE     : $dir\dist\WB_SystemCare.exe (${mb} MB)" -ForegroundColor Cyan
Write-Host $sep -ForegroundColor DarkYellow
Write-Host ""
