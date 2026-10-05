# W.B. SystemCare

**Ferramenta de restauração e limpeza para laboratórios de informática**
Desenvolvido por Waldemir (@romeuwb) para a Usina da Paz Salinópolis — Sala de Tecnologia.

🌐 **Site oficial:** [romeuwb.github.io/wb-systemcare](https://romeuwb.github.io/wb-systemcare/)

---

## Funcionalidades

### 🎨 Personalização do Windows
Restaura as configurações visuais do sistema para o padrão:
- Papel de parede (imagem padrão do Windows)
- Proteção de tela (desativada)
- Tela de bloqueio (Spotlight reativado)
- Ponteiros do mouse (esquema Aero padrão, tamanho 1)
- Cores do sistema (modo claro, cor de destaque automática)
- Histórico de navegação (Chrome, Edge, Firefox, IE)
- Lixeira (esvaziada)

### 🔍 Varredura de Arquivos
- Lista em cascata o conteúdo das pastas do usuário atual
- Escolha quais pastas varrer antes de iniciar
- Expande/recolhe pastas para ver o conteúdo
- Seleciona itens individualmente ou por grupo
- Exclui arquivos e pastas selecionados permanentemente

### ⚡ Automação Completa
- Executa restauração de tema + varredura + exclusão com um clique
- Opção de confirmar antes de excluir

### 🗓 Agendamento
- Inicialização automática com o Windows (todos os usuários ou só o atual)
- Limpeza periódica agendada a cada X dias

### 👥 Gerenciamento de Usuários
- Lista usuários locais com status, último login e grupos
- Altera senha, nome completo, expiração de senha
- Ativa ou desativa contas

### 🔄 Atualização Automática
- Verifica novas versões automaticamente via GitHub Releases
- Baixa, substitui o .exe atual e reinicia automaticamente

---

## Download

Baixe o executável na [página de releases](https://github.com/romeuwb/wb-systemcare/releases).
O arquivo `WB_SystemCare.exe` roda diretamente sem instalação.

---

## Publicar nova versão (desenvolvedores)

```powershell
# Incrementa minor automaticamente: 1.5 → 1.6
powershell -ExecutionPolicy Bypass -File release.ps1

# Força uma versão específica
powershell -ExecutionPolicy Bypass -File release.ps1 -Version "2.0"

# Só incrementa patch: 1.5 → 1.5.1
powershell -ExecutionPolicy Bypass -File release.ps1 -Patch

# Simula sem fazer nada
powershell -ExecutionPolicy Bypass -File release.ps1 -DryRun
```

O script faz automaticamente:
1. Incrementa a versão
2. Atualiza o número em todos os arquivos
3. Valida a sintaxe
4. Compila o .exe
5. Faz commit + push no GitHub
6. Cria a release com o .exe anexado

---

## Repositório

[github.com/romeuwb/wb-systemcare](https://github.com/romeuwb/wb-systemcare)
