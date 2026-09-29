# 🖥 LimpaPC — Ferramenta para Laboratório de Informática

Ferramenta para restaurar as configurações padrão do Windows e limpar os
arquivos deixados por alunos ao final de cada turma de curso.

---

## ▶ Como Executar

**Sem instalação de dependências** — apenas Python 3.8+ é necessário.

### Opção 1 — Duplo clique
Execute **`LimpaPC.bat`** (usuário normal) ou **`LimpaPC_Admin.bat`** (recomendado para restaurar temas e cursores).

### Opção 2 — Via terminal
```
python app.py
```

---

## 🔧 Requisitos

| Item | Versão |
|------|--------|
| Python | 3.8 ou superior |
| Sistema Operacional | Windows 10 / 11 |
| Bibliotecas | Apenas padrão (tkinter, winreg, ctypes) |

> **Sem instalação extra!** Todas as bibliotecas utilizadas já vêm incluídas no Python para Windows.

---

## 📋 Funcionalidades

### 🎨 Aba Tema Windows
Restaura as configurações visuais para o padrão do Windows:
- **Papel de parede** → Remove e define fundo preto sólido
- **Proteção de tela** → Desativa e define "Nenhuma"
- **Tela de bloqueio** → Restaura para o padrão do Windows
- **Ponteiro do mouse** → Restaura esquema Aero padrão
- **Cores do sistema** → Restaura cores, modo claro e cor de destaque

### 🔍 Aba Varredura
Escaneia as pastas do perfil do usuário atual:
- Área de Trabalho, Documentos, Downloads
- Músicas, Vídeos, Imagens
- Objetos 3D, Favoritos, Links
- Temp (AppData\Local\Temp)

Funcionalidades:
- Lista todos os arquivos e pastas com nome, tipo, tamanho e data
- Permite **seleção individual** de itens para excluir
- Botões "Selecionar Tudo" e "Desmarcar Tudo"
- Adicionar **pasta personalizada** para varredura extra

### ⚡ Aba Automação
Executa todas as etapas com um único clique:
- Escolha quais etapas ativar (tema, varredura, exclusão)
- Opção de **confirmar antes de excluir** (recomendada)
- Modo totalmente automático para limpeza rápida entre turmas

### 📊 Aba Progresso
Acompanhe cada etapa:
- Barra de progresso global
- Cards de status por etapa (Aguardando / Em andamento / Concluído / Erro)
- Resumo com contagem e tamanho total
- Log completo de todas as operações

---

## 📁 Arquivos do Projeto

```
limpaPC/
├── app.py              ← Aplicativo principal (GUI)
├── theme_restore.py    ← Módulo de restauração do tema Windows
├── file_scanner.py     ← Módulo de varredura e exclusão de arquivos
├── LimpaPC.bat         ← Atalho de execução normal
├── LimpaPC_Admin.bat   ← Atalho de execução como Administrador
├── limpapc.log         ← Log gerado automaticamente ao executar
└── README.md           ← Este arquivo
```

---

## ⚠ Observações Importantes

- **Exclusão é permanente**: os arquivos excluídos **não vão para a Lixeira**.
- **Administrador recomendado**: algumas configurações (cursores, temas) requerem privilégios elevados. Use `LimpaPC_Admin.bat`.
- **Cada aluno usa seu próprio perfil**: a varredura opera no perfil do usuário que está executando o programa. Em laboratórios com múltiplos usuários, execute com cada login.
- O log completo fica em `limpapc.log` na mesma pasta do programa.

---

## 🔄 Fluxo Recomendado para Fim de Curso

1. Execute `LimpaPC_Admin.bat`
2. Vá em **⚡ Automação**
3. Ative: ✔ Restaurar tema, ✔ Escanear pastas, ✔ Confirmar antes de excluir
4. Clique em **INICIAR LIMPEZA AUTOMÁTICA**
5. Revise a lista e confirme a exclusão
6. Pronto! O PC estará limpo para o próximo aluno.
