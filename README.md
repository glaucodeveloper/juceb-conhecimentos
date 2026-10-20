# JUCEB Conhecimentos

Especialidade de pesquisa do Cognoscere Metis para registro empresarial na Bahia e legislação empresarial, tributária e fiscal brasileira. O projeto transforma o bundle OKF recebido em fontes rastreáveis, mapas de pesquisa e unidades isoladas do Metis.

## Estado em 20/10/2026

- 86 referências normativas e institucionais no catálogo.
- 42 mapas temáticos preparados no envelope OKFForge.
- 78 fontes oficiais capturadas e extraídas automaticamente; 8 seguem pendentes.
- Speciality copiada para a raiz local `~/cognoscere/specialities/juceb-conhecimentos`.
- Os tensores Safetensors das 42 unidades ainda não foram gerados. O serviço Metis estava parado e a GPU tinha 383 MiB livres; sem o serviço carregado, não há inferência de memória a registrar.

Consulte [`SOURCES-STATUS.md`](SOURCES-STATUS.md) e [`relatorio_sincronizacao.json`](relatorio_sincronizacao.json) antes de usar qualquer conteúdo. Captura automática não confirma vigência ou consolidação legal.

## Estrutura

| Caminho | Conteúdo |
| --- | --- |
| [`speciality.json`](speciality.json) | Identidade e escopo da especialidade `juceb-conhecimentos` |
| [`manifest.json`](manifest.json) | Fontes, 42 unidades candidatas e estado de geração dos tensores |
| [`okf/monitor.okf`](okf/monitor.okf) | Escopo, critérios de roteamento e limites de resposta |
| [`source-okfs/references/`](source-okfs/references/) | 86 fichas com fonte oficial e proveniência |
| [`source-okfs/concepts/`](source-okfs/concepts/) | 42 mapas temáticos com referências ligadas |
| [`source-okfs/compiled/`](source-okfs/compiled/) | Texto candidato extraído automaticamente |
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

## Gerar memórias Metis

Instale a pasta do repositório em `COGNOSCERE_SPECIALITIES_ROOT/juceb-conhecimentos`. Quando o serviço Metis estiver ativo com modelo carregado e a raiz configurada, execute na pasta instalada:

```bash
python3 scripts/seed_metis.py
```

O script cria o tensor isolado de cada mapa pela API local, submete o OKF correspondente à consolidação Metis e atualiza o manifesto. Os Safetensors, snapshots e registros ficam fora do Git. O script recusa operar contra outra raiz ou substituir uma memória ativa.

## Regras de uso

- Identifique jurisdição, município, atividade econômica, operação e data de referência.
- Separe texto legal, orientação administrativa e inferência.
- Confira ato oficial, versão consolidada, vigência e efeitos antes de afirmar obrigação ou calcular tributo.
- Cite dispositivos e URLs oficiais; sinalize fonte ou extração incompleta.
- Trate os mapas como roteiros de pesquisa, não como parecer jurídico ou fiscal.

## Contrato Cognoscere

`speciality.json` usa `cognoscere.speciality.v1`; `manifest.json` usa `okfforge.metis.monitor-manifest.v1`; as fichas seguem `okfforge.juceb.*.v1`. O bundle original usa `okf.knowledge.v1`; a conversão preserva esse valor em `legacy_schema`.
