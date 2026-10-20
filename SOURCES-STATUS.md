# Estado das fontes e limites do corpus

Referência do bundle: 19/10/2026. Captura e revisão: 20/10/2026.

## Contagem

- 86 referências no catálogo original.
- 42 mapas temáticos convertidos para OKFForge.
- 78 capturas oficiais com extração automática.
- 8 registros sem texto extraído. O detalhe por ato, URL final, hash e erro está em [`relatorio_sincronizacao.json`](relatorio_sincronizacao.json).

O relatório registra os endereços tentados em cada execução. `catalogo_fontes.json` contém a URL atualmente curada e separa `evidence_url` quando há comunicado oficial, mas ainda falta o texto do ato.

## Oito registros pendentes

- Resoluções CGSN 140/2018, 187/2026, 190/2026 e 191/2026: o SIJUT serve a aplicação dinâmica e não entregou texto ao coletor. Os links 187/190/191 do bundle apontavam para a Resolução 140. A Receita confirma as alterações de 2026; faltam os atos diretos e uma captura textual verificável.
- IN RFB 2.005/2021: o ato original está revogado pela IN RFB 2.237/2024. A URL direta foi corrigida, mas a aplicação dinâmica não forneceu texto ao coletor. Não usar como regra atual de DCTFWeb.
- IN RFB 2.110/2022: a URL direta foi corrigida, mas a aplicação dinâmica não forneceu texto. O ato recebeu alterações, inclusive em 2026; a versão consolidada ainda precisa ser capturada.
- Portal nacional da NF-e: a URL oficial redireciona em ciclo.
- Portal da SEFAZ-BA: a validação TLS falhou. O coletor mantém a verificação de certificado habilitada.

As URLs de LC 128/2008 e LC 147/2014 foram corrigidas para o Planalto e recapturadas; ambas agora constam entre as 78 capturas.

## Como interpretar as capturas

`extracted_automatic` informa apenas que o coletor obteve bytes oficiais e texto suficiente para processar. Não confirma vigência, consolidação, efeitos temporais, autenticidade de cada trecho nem precisão da divisão por artigo. O texto pode conter codificação imperfeita. Todo OKF compilado conserva `legal_consolidation_verified: false` e deve passar por revisão humana antes de orientar uma decisão.

Os mapas temáticos são roteiros de pesquisa com questões abertas e referências; não são pareceres nem interpretações validadas. O corpus não cobre a legislação tributária dos 417 municípios baianos, todos os atos setoriais, convênios, protocolos ou atualizações posteriores à data da captura.

## Fontes oficiais conferidas

- [LC 123/2006 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm)
- [LC 128/2008 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp128.htm)
- [LC 147/2014 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp147.htm)
- [LC 227/2026 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp227.htm)
- [Legislação da JUCEB](https://www.ba.gov.br/juceb/legislacao/leis)
- [Receita Federal: Resoluções CGSN 190 e 191/2026](https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/agosto/cgsn-atualiza-regras-do-simples-nacional-para-adequacao-a-reforma-tributaria-do-consumo)
- [Receita Federal: IN RFB 2.237/2024 — DCTFWeb](https://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=141910)
