$notes = "v1.6 - Correcoes criticas: instancia unica no tray, lista de admins correta, exclusao robusta (arquivos em uso ignorados), etapas de progresso corretas, tema sem abrir janela de personalizacao, watchdog anti-travamento"
powershell -ExecutionPolicy Bypass -File "d:\Projetos\limpaPC\release.ps1" -Notes $notes
