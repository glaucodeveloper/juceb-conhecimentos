# Lote de teste NF-e → Simples Nacional

`DEMO-NFE-*.xml` corresponde aos registros demonstrativos exibidos em **Notas fiscais**. O botão **Carregar lote de teste** lê estes mesmos arquivos e os envia ao processador usado pela importação manual: extração de campos, associação por CNPJ, cálculo por perfil, classificação de pendências e gravação local. A importação substitui a linha demonstrativa correspondente e ignora reimportações pela chave de acesso.

## Validação

Os XMLs foram gerados para o pacote oficial NF-e `PL_010f_v1.04` (Pacote 010f, publicado em 31/08/2026). Cada arquivo passa pelo XSD `nfe_v4.00.xsd`, tem chave de 44 dígitos e contém uma assinatura XMLDSig verificável com certificado autossinado de teste. O certificado e os CNPJs são fictícios. Os arquivos não têm protocolo de autorização (`protNFe`) e **não são documentos fiscais válidos para circulação, escrituração ou transmissão à SEFAZ**.

Baixe o pacote no [Portal Nacional da NF-e](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w%3D) e valide assim:

```bash
xmllint --noout --schema /caminho/PL_010f_v1.04/nfe_v4.00.xsd fixtures/nfe/DEMO-NFE-*.xml
python3 fixtures/validate_nfe_fixtures.py --schema /caminho/PL_010f_v1.04/nfe_v4.00.xsd
```

O segundo comando requer `lxml` e `cryptography`. O gerador está em `fixtures/generate_nfe_fixtures.py`; ele cria uma chave de teste efêmera e não grava a chave privada.

## Resultado fiscal esperado

O período de teste é outubro de 2026. O perfil de exemplo preenche Anexo I, receita de revenda, RBT12, regime de competência e `vNF` como base documental para Mercado Dois Irmãos (R$ 500.000), Casa do Cacau (R$ 150.000), Verdejar (R$ 300.000) e Oficina Horizonte (R$ 800.000). Os valores são dados sintéticos para exercitar faixas diferentes, não dados apurados de empresas.

O lote contém cinco NF-e de saída calculáveis. As notas de entrada e a nota de cliente fora do Simples não geram estimativa. As três notas de saída da Clínica e da Nuvem ficam pendentes porque a aplicação não infere anexo/atividade a partir do nome, NCM ou CFOP; o exemplo não converte prestação de serviço em receita de mercadoria. Todos os registros continuam identificados como exemplos.

O cálculo de cada nota é apenas uma estimativa documental usando a alíquota efetiva da faixa, conforme LC 123/2006, art. 18, § 1º e Anexos. O PGDAS-D exige a receita total do período, segregada por estabelecimento, atividade e tratamento tributário; logo, a soma deste lote **não é o DAS mensal** nem uma declaração transmitível.

## Base legal e corte de vigência

- [Lei Complementar 123/2006, art. 18 e Anexos I a V](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm): receita bruta, RBT12, alíquota efetiva, anexos e segregações.
- [Resolução CGSN 140/2018, versão compilada](https://normas.receita.fazenda.gov.br/sijut2consulta/normas.receisulta/link.action?idAto=92278&visao=compilado): arts. 16–19, 21–26 e 25, incluindo regimes, base e segregação de receita.
- [Manual PGDAS-D/DEFIS, versão de 17/06/2025](https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/MANUAL_PGDAS-D_2018_V4.pdf): declaração mensal e etapas de apuração.
- [Esquemas XML no Portal Nacional da NF-e](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w%3D): versão de schema aplicável ao XML, sujeita a atualização do portal.

O motor do app está limitado a competências até 12/2026. Não extrapole a tabela para 2027: verifique a vigência dos atos do CGSN e da transição da reforma tributária antes de estender as regras.
