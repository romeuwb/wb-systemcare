# WB SystemCare — Como publicar uma nova release

## Pré-requisitos
- [GitHub CLI](https://cli.github.com/) instalado
- Autenticado: `gh auth login`

## Publicar nova versão

```powershell
# 1. Compile o executável
powershell -ExecutionPolicy Bypass -File build_exe.ps1

# 2. Crie a release e faça upload do .exe
gh release create v1.5 dist\WB_SystemCare.exe `
  --title "WB SystemCare v1.5" `
  --notes "Versão 1.5 — Usina da Paz Salinópolis — Sala de Tecnologia"

# 3. Para versões futuras, troque v1.5 pela nova versão (ex: v1.6)
```

## Estrutura de versões
- Tag: `v1.5` (formato: `vMAJOR.MINOR`)
- Asset obrigatório: `WB_SystemCare.exe`
- O app busca automaticamente em `github.com/romeuwb/wb-systemcare/releases`
