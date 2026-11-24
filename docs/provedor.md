# Contrato do provedor de vídeo

O contrato `VideoGenerationProvider` em `backend/app/domain/workflow.py` usa valores comuns de Python e é independente do Playwright.

| Operação | Responsabilidade |
| --- | --- |
| `status(instance_id)` | Informar autenticação, disponibilidade e créditos quando a origem da observação é confiável. |
| `prepare(generation)` | Validar modelo, proporção, duração, permissões e referências sem submeter. |
| `submit(generation)` | Fazer um envio e devolver evidência ou identificador remoto. O worker registra a intenção antes dessa chamada. |
| `wait(generation, submission, stopping)` | Observar a conclusão com timeout e cancelamento cooperativo local. |
| `reconcile(instance_id, submission)` | Consultar se uma submissão conhecida existe com segurança, sem enviar nova geração. |
| `save_frame(..., path)` | Escrever um PNG e devolver a origem, ou indicar fallback por download e FFmpeg. |
| `download(..., path)` | Salvar o MP4 no arquivo temporário indicado. |

`Generation` carrega a instância, o projeto, um possível ID remoto, as referências locais, o modelo opcional, a duração desejada, a proporção, o timeout e a permissão explícita para execução paga. `WorkflowError` fornece código e mensagem adequados ao usuário. A tentativa grava dependências por ID, resultado, evidência e erro.

O simulador devolve fixtures locais e o recibo determinístico `sim-<tentativa>`. Assim, a recuperação pode coletar novamente uma fixture associada a um recibo confirmado sem chamar `submit`.

## Estado do Google Flow

O gerenciador de navegador abre o Chromium visível com perfil exclusivo e navega à página pública do Flow. O usuário realiza login e inspeciona a interface manualmente. O status programático observa somente a localização da página ou um possível redirecionamento. O adaptador não tem seletores de edição, custo, cota ou geração confirmados.

A próxima validação precisa de uma sessão gráfica, conta autorizada e permissão explícita antes de qualquer geração paga. Confirme termos, limites e ações permitidas. Registre os nomes acessíveis e estados observáveis para projeto remoto, modos, modelos, proporções, duração, custo, envio, conclusão, frame nativo e download. Valide a configuração selecionada, implemente somente as operações confirmadas e teste uma sequência de duas cenas autorizadas na mesma instância. Verifique no disco os MP4 e frames e confirme o uso do frame da primeira cena na segunda.

CAPTCHA, sessão expirada e restrição exigem intervenção manual. A observação de cota deve informar valor, fonte e hora, quando disponível. A seleção de modelo é configurável. O nome Omni 1.1 é tratado como preferência possível e precisa ser conferido na conta. Uma observação de créditos desconhecida não é autorização de gastos.
