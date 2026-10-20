# JUCEB Conhecimentos

Especialidade de pesquisa do Cognoscere Metis para registro empresarial na Bahia e legislação empresarial, tributária e fiscal brasileira. O projeto transforma o bundle OKF recebido em fontes rastreáveis, mapas de pesquisa e unidades isoladas do Metis.

## Estado em 20/10/2026

- 86 referências normativas e institucionais no catálogo.
- 42 mapas temáticos preparados no envelope OKFForge.
- 78 fontes oficiais capturadas e extraídas automaticamente; 8 seguem pendentes.
- O Cognoscere particionou automaticamente 14.190 candidatos de artigo em OKFs individuais e identificou 32.743 candidatos de parágrafo, inciso e alínea como subdispositivos.
- O índice jurídico possui 78 documentos e 42 mapas de pesquisa. A memória raiz da speciality é criada pela API direta do Cognoscere; os textos completos ficam nos OKFs e entram no chat por recuperação de evidências.
- Os tensores isolados dos 42 mapas temáticos continuam pendentes; eles são diferentes da memória raiz e da recuperação automática por artigo.

Consulte [`SOURCES-STATUS.md`](SOURCES-STATUS.md) e [`relatorio_sincronizacao.json`](relatorio_sincronizacao.json) antes de usar qualquer conteúdo. Captura e partição automáticas não confirmam vigência ou consolidação legal.

## Estrutura

| Caminho | Conteúdo |
| --- | --- |
| [`speciality.json`](speciality.json) | Identidade e escopo da especialidade `juceb-conhecimentos` |
| [`manifest.json`](manifest.json) | Fontes, 42 unidades candidatas e estado de geração dos tensores |
| [`okf/monitor.okf`](okf/monitor.okf) | Escopo, critérios de roteamento e limites de resposta |
| [`source-okfs/references/`](source-okfs/references/) | 86 fichas com fonte oficial e proveniência |
| [`source-okfs/concepts/`](source-okfs/concepts/) | 42 mapas temáticos com referências ligadas |
| [`source-okfs/compiled/`](source-okfs/compiled/) | Texto candidato extraído automaticamente |
| `source-okfs/provisions/` (gerado) | Um OKF por artigo candidato, com subdispositivos e proveniência |
| `source-okfs/provision-index.json` (gerado) | Índice usado pelo Cognoscere para localizar artigos durante o chat |
| [`documentos_oficiais/`](documentos_oficiais/) | Respostas originais dos hosts oficiais permitidos |
| [`textos_extraidos/`](textos_extraidos/) | Extrações textuais com marcadores de página quando disponíveis |
| [`okf_compilados/`](okf_compilados/) | Saída bruta do coletor, antes da conversão para OKFForge |
| [`imports/`](imports/) | ZIP original, usado como fonte imutável da conversão |
| [`scripts/`](scripts/) | Coleta, conversão e geração das memórias |

## Preparar ou atualizar o corpus

O coletor usa HTTPS, valida certificados e aceita somente hosts oficiais allowlisted. O relatório preserva falhas; não substitua falhas por texto reconstruído.

```bash
python3 -m pip install -r requirements.txt
python3 scripts/sync_official.py --verified-only
python3 scripts/build_speciality.py
```

Revise `catalogo_fontes.json`, `relatorio_sincronizacao.json` e [`SOURCES-STATUS.md`](SOURCES-STATUS.md) antes de publicar novas capturas. Use `--ids` somente após conferir a URL oficial exata; `--all` também tenta registros ainda não verificados. `build_speciality.py` converte referências, mapas e extrações para os schemas OKFForge e deixa `manifest.skills` vazio até a geração real dos tensores.

## Pipeline automático do Cognoscere

Ao criar ou preparar a speciality pela API direta do Cognoscere, o serviço executa a partição artigo a artigo, atualiza o índice idempotente e grava um seed compacto na memória raiz Metis:

```http
POST /specialities/create
Content-Type: application/json

{"slug":"juceb-conhecimentos","title":"JUCEB | Bens, serviços e legislação empresarial da Bahia"}
```

O Cognoscere recupera até quatro evidências por consulta e injeta o texto e as referências oficiais no contexto do modelo. Se a preparação da memória falhar, o manifesto fica pendente e a próxima chamada à mesma rota tenta novamente. Conteúdo integral não é colocado no seed Metis.

Para reconstruir localmente os OKFs de artigo e o índice, execute:

```bash
python3 scripts/partition_legal_corpus.py
```

A rotina usa somente a biblioteca padrão do Python, preserva hash e proveniência das fontes e não reescreve os resultados quando o corpus não mudou. As saídas ficam fora do Git porque são derivadas dos arquivos em `source-okfs/compiled/` e podem ser regeneradas.

`scripts/seed_metis.py` permanece como operação explícita para criar memórias isoladas dos mapas temáticos. Os Safetensors, snapshots e registros ficam fora do Git.

## Regras de uso

- Identifique jurisdição, município, atividade econômica, operação e data de referência.
- Separe texto legal, orientação administrativa e inferência.
- Confira ato oficial, versão consolidada, vigência e efeitos antes de afirmar obrigação ou calcular tributo.
- Cite dispositivos e URLs oficiais; sinalize fonte ou extração incompleta.
- Trate os mapas como roteiros de pesquisa, não como parecer jurídico ou fiscal.

## Contrato Cognoscere

`speciality.json` usa `cognoscere.speciality.v1`; `manifest.json` usa `okfforge.metis.monitor-manifest.v1`; os artigos usam `okfforge.juceb.legal_provision.v1`. O bundle original usa `okf.knowledge.v1`; a conversão preserva esse valor em `legacy_schema`.
