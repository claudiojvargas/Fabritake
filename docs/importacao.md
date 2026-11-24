# Importação de projetos

A versão 1 é recebida por `POST /api/projects/import` com os campos `instance_id` e `manifest`. Na interface, use **Projetos → Importar** e selecione a instância. Seu provedor precisa corresponder ao informado no arquivo.

Use [monolito-modular.json](../examples/monolito-modular.json) como modelo. O manifesto tem `version: 1`, um objeto `project` e uma lista `scenes`. Cada cena tem `order` inteiro positivo e único, `title` e `prompt`. Campos opcionais incluem `duration` em segundos, `references` e `continuity`. A continuidade padrão é `previous_final_frame`. As outras opções são `explicit_reference` e `none`.

O projeto pode indicar `description`, `language` (padrão `pt-BR`), `duration`, `ratio` (`16:9`, `9:16` ou `1:1`), `provider` (`simulated` ou `flow`), `references` e `settings`. Em `settings`, use `manual_review`, `model`, `timeout` (segundos) e `paid_authorized` (falso por padrão e reiniciado para falso na importação). O importador descarta `progress` de um `projeto.json` exportado e cria um projeto novo com todas as cenas pendentes.

Referências usam caminhos como `referencias/diagrama.png`. O manifesto transporta metadados. Envie novamente as imagens em **Arquivos → Enviar referência**, usando os mesmos nomes indicados no manifesto. A geração pausa ou falha com indicação da referência ausente. Para vincular novas imagens, use o editor do projeto ou da cena depois do envio.

## Roteiro Markdown

A aba **Arquivos** exporta um roteiro com cabeçalho `# Fabritake v1`, um bloco de metadados JSON e seções `## Cena`. Cada seção contém um bloco JSON que segue os campos da cena (exceto `prompt`) e um bloco `prompt` com o texto literal. Use uma cerca de quatro crases por bloco. A mesma cerca em uma linha isolada do prompt é reservada. O importador lê apenas este formato, inclusive quando o texto é editado no Obsidian.

`````markdown
# Fabritake v1

````json
{"title": "Exemplo", "provider": "simulated"}
````

## Cena

````json
{"order": 1, "title": "Abertura", "continuity": "none"}
````

````prompt
Plano geral de uma sala de operações. Termine com a câmera voltada ao painel.
````
`````

Para a API, envie `instance_id` e `markdown` em `POST /api/projects/import-markdown`. O roteiro pode ser importado novamente como novo projeto, enquanto `prompts.md` é uma leitura rápida da sequência. O Fabritake preserva edições locais dos dois Markdown. A opção de exportação sempre produz uma cópia atual dos metadados do banco.

Operações de escrita na API local exigem o cabeçalho `X-Fabritake: local`. A interface envia esse cabeçalho em todas as operações.
