# Arquitetura e recuperação

O MVP é um monolito de processo único. O domínio contém contratos, erros e transições. A aplicação coordena projetos, worker e recuperação. A infraestrutura concentra SQLite, arquivos, mídia, perfis Playwright e os dois provedores. A API tipa e valida entradas e o React consulta o estado por polling. Uma eventual integração de roteiro pode produzir um manifesto v1 e usar o importador, mantendo determinística a execução das cenas.

A fila usa os estados duráveis do projeto. Um lock de arquivo impede duas execuções do servidor no mesmo armazenamento. O worker processa uma cena por vez e sincroniza alterações de estado com os comandos da API. Cada diretório real de navegador tem um lock próprio. A instância fica vinculada ao projeto após a primeira tentativa. As sessões são independentes, abertas sob demanda.

A migração inicial cria as tabelas; SQLite usa chaves estrangeiras, WAL, sincronização completa e ordem única de cenas por projeto. A edição é bloqueada enquanto há execução. Reordenar exige cenas sem histórico. O título de uma cena com tentativa fica fixo para preservar os nomes publicados. Ao remover um projeto, o banco remove o cadastro e o histórico associado. A pasta permanece disponível para recuperação manual. A exclusão de uma cena com histórico é bloqueada.

## Submissões e arquivos

- Antes do envio, a intenção é confirmada no banco. Um reinício anterior à intenção permite retomar. Um reinício após a intenção exige reconciliar o arquivo e a evidência existente antes de nova geração.
- Uma solicitação de pausa impede novos envios. Uma cena já enviada pode terminar sua coleta. Ao fechar o servidor, o provedor recebe o sinal de interrupção local.
- MP4 e PNG são validados em uma pasta parcial antes de serem promovidos para uma tentativa no mesmo volume. A seleção usa substituição atômica por arquivo e conserva o arquivo imutável da tentativa. O painel serve a seleção pelo ID arquivado no banco. Uma promoção interrompida pode ser repetida com segurança. Se houver conflito com mídia alterada no disco, preserve o arquivo e resolva o conflito manualmente.
- A recuperação valida arquivos completos. Um download interrompido pelo processo pode deixar uma pasta parcial para diagnóstico. Se existir recibo confirmado do simulador, **Verificar tentativa** coleta novamente os mesmos artefatos. Para uma submissão real incerta, confira o resultado no provedor antes de encerrar a tentativa manualmente.
- O histórico identifica quais frames foram usados. A seleção de uma nova versão sinaliza dependentes diretas e transitivas. A próxima cena desatualizada aguarda decisão. A escolha de manter uma versão preserva a dependência registrada no momento da produção.
- Os logs estruturados ficam no SQLite e recebem uma cópia JSONL no projeto. Referências carregadas pela interface passam por limites de tamanho e formato. Os downloads são restritos aos caminhos registrados. O navegador e a API usam perfis e diretórios locais separados.

O FFmpeg recebe somente argumentos construídos pela aplicação. O fallback de frame atualiza um PNG para cada quadro decodificado, deixando o último. O simulador não altera duração, composição nem pixels com base no prompt. Ele valida o transporte de referências, persistência e entrega de mídia.
