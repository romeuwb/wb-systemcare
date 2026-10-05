# Como publicar uma nova versão

## Opção 1 — Duplo clique (mais fácil)

Execute o arquivo:

```
PUBLICAR_NOVA_VERSAO.bat
```

## Opção 2 — Terminal

Abra o terminal na pasta `d:\Projetos\limpaPC` e execute:

```powershell
powershell -ExecutionPolicy Bypass -File release.ps1
```

---

## O que o script faz automaticamente

1. Lê a versão atual (ex: v1.5)
2. Incrementa para a próxima (ex: v1.6)
3. Atualiza o número em todos os arquivos
4. Valida a sintaxe do código
5. Compila o WB_SystemCare.exe
6. Envia o código para o GitHub
7. Publica a release com o .exe

## Variações

| Para fazer isso...         | Use este comando                                          |
|----------------------------|-----------------------------------------------------------|
| Versão normal (1.5 → 1.6)  | `release.ps1`                                             |
| Só corrigir bug (1.5 → 1.5.1) | `release.ps1 -Patch`                                  |
| Versão grande (1.5 → 2.0)  | `release.ps1 -Major`                                      |
| Forçar versão específica    | `release.ps1 -Version "2.0"`                              |
| Simular sem publicar       | `release.ps1 -DryRun`                                     |

## Links após publicar

- Release: https://github.com/romeuwb/wb-systemcare/releases
- Site:    https://romeuwb.github.io/wb-systemcare/
