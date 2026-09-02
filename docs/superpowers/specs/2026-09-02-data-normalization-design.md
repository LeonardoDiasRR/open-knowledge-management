# Design: Higienização e tipagem de dados na ingestão tabular (OpenKM)

Data: 2026-09-02
Status: aprovado em conversa com o usuário (decisões registradas ao longo do doc)
Escopo: `scripts/tabular.py`, novo `scripts/normalizers.py`, testes, `SKILL.md`/`references/`

## 1. Contexto e problema

O helper tabular do OpenKM (`scripts/tabular.py`) persiste datasets em DuckDB
com tipos inferidos por `_infer_type` e valores convertidos por `_typed_value`.
Hoje:

- Datas só são reconhecidas em ISO estrito (`date.fromisoformat`). `02/09/2026`,
  `02-09-26`, `2 de setembro de 2026` são gravadas como VARCHAR cru.
- CPF, CNPJ, CEP e telefone não têm tratamento: máscaras (`123.456.789-09`,
  `(11) 3456-7890`, `01310-100`) são gravadas como vieram. Pior: um CPF
  inteiramente dígitos é inferido como BIGINT e **perde zeros à esquerda**
  (`045.106.365-09` → `4510636509` numérico).
- Não existe timestamp: `02/09/2026 14:30` vira VARCHAR.

Objetivo: antes de gravar no DuckDB, normalizar e tipar colunas de
**data (DATE), timestamp (TIMESTAMP), CPF, CNPJ, CEP e telefone (todos
VARCHAR, apenas dígitos)**, sem quebrar a filosofia da spec anterior
("no silent coercion; uncertain stays text") além do estritamente acordado.

## 2. Decisões acordadas (regras do produto)

1. Tipos no escopo: data, timestamp, CPF, CNPJ, CEP, telefone.
2. CPF/CNPJ/CEP/telefone são armazenados como **texto** (VARCHAR) somente
   dígitos; data como `DATE`; timestamp como `TIMESTAMP`.
3. Detecção por **convergência nome da coluna + conteúdo** (nunca um dos dois
   sozinho para documentos/telefone).
4. Datas: heurística **pt-BR** (dia primeiro em ambíguos); valores
   irrecuperáveis em coluna detectada viram **NULL**, contados e reportados.
5. CPF/CNPJ: **sem validação de dígito verificador** — higieniza sempre que
   o formato casar (dado legado/corrompido mantém formato consistente).
6. Telefone: remove não-dígitos e **completa DDI `55` quando o total limpo tem
   exatamente 10 ou 11 dígitos**; nunca remove nem insere dígitos
   adicionais; nunca detecta por conteúdo puro.
7. Gatilho de data: **nome forte aplica** (irrecuperáveis → NULL); **sem nome
   forte exige 100%** das células não-vazias parseáveis, senão a coluna inteira
   permanece VARCHAR (protege colunas de texto livre como `observacao`).

## 3. Arquitetura (abordagem A — módulo puro + wiring mínimo)

### 3.1 `scripts/normalizers.py` (novo, ~120 linhas, stdlib apenas)

Funções puras, sem DuckDB, determinísticas e idempotentes:

```python
ColumnKind = Literal["date", "timestamp", "cpf", "cnpj", "cep", "telefone"]

def parse_temporal(value: object) -> tuple[date | datetime, bool] | None
    # (valor, tem_hora). Aceita ISO, DD/MM/AAAA, DD-MM-AA, DD.MM.AAAA,
    # AAAA/MM/DD, extenso pt-BR, abreviaturas (set/out), parte opcional HH:MM[:SS][.f].
def detect_column_kind(header: str, values: Sequence[object]) -> ColumnKind | None
def normalize_cell(value: object, kind: ColumnKind) -> object | None
    # None = irrecuperável (vira NULL). Nunca lança por conteúdo.
```

`ValueError` apenas para programador (kind desconhecido).

### 3.2 Wiring em `scripts/tabular.py` — exatamente 3 pontos

1. **`_infer_type(values, column_name=None)`**: recebe o nome da coluna original.
   Com kind detectado: `date` → `"DATE"`, `timestamp` → `"TIMESTAMP"`,
   cpf/cnpj/cep/telefone → `"VARCHAR"` fixo (corrige o bug BIGINT/zero à
   esquerda). Sem kind: comportamento idêntico ao atual.
2. **`_typed_value(value, type_name, kind=None)`**: aplica `normalize_cell`
   antes da conversão existente. Datas/timestamps devolvem objetos `date`/
   `datetime` (caminho já suportado pelo driver DuckDB).
3. **`_persist`** calcula `kind = detect_column_kind(coluna, valores)` **uma vez
   por coluna, antes do `CREATE TABLE`**, e propaga para tipo, INSERT,
   `sample` do `TableManifest` e `_inspect_payload` (que passa a incluir
   `"kind"` por coluna). Nada muda de tipo no meio da carga.

Inalterados: motor de fórmulas Excel, `query_read_only`, catálogos
`_openkm_*`, assinaturas públicas (`persist_source`, `rebuild_source`,
`load_tabular_file`), CLI. `requirements.txt` inalterado (só stdlib).

### 3.3 Dependência de ordem

`load → detect por coluna → CREATE TABLE (tipo final) → INSERT normalizado`.
`inspect-file` e `persist-json` compartilham a mesma detecção — o agente vê o
tipo/kind/amostra normalizados na inspeção, antes de persistir.

## 4. Regras de detecção (núcleo)

Nome de coluna comparado após `sanitize_identifier` (minúsculas, sem acentos,
`_`). célula "vazia" = None, vazio, `-`, `--`, `s/ data`, `s/data`, `sem data`,
`n/a`, `na`, `null`, `none` (case-insensitive) — não conta como falha de
detecção nem como perda (vira NULL naturalmente).

Ordem de checagem (primeiro que casar vence):

| Kind | Nome forte | Gatilho por conteúdo | Tipo DuckDB |
|---|---|---|---|
| `timestamp` | contém `timestamp`, `hora`, `horario`, `created_at`, `updated_at` | 100% parseiam E **qualquer** célula tem parte horária explícita | `TIMESTAMP` |
| `date` | contém `data`, `nasc`, `venc`, `exped` ou prefixo `dt_` E ≥1 célula parseável | 100% parseiam E nenhuma com hora | `DATE` |
| `cpf` | contém `cpf` (e não `cnpj`) | 100% têm exatamente 11 dígitos após limpeza | `VARCHAR` |
| `cnpj` | contém `cnpj` | 100% têm exatamente 14 dígitos | `VARCHAR` |
| `cep` | contém `cep` | 100% têm exatamente 8 dígitos | `VARCHAR` |
| `telefone` | contém `telefone`, `celular`, `fone`, `whatsapp`, `contato` | **nunca** por conteúdo | `VARCHAR` |

Regras de colisão:

- **Hora manda sobre o nome**: coluna `data_registro` cujos valores trazem
  `HH:MM` é `timestamp` (DATE descartaria a hora silenciosamente). Célula sem
  hora em coluna timestamp → meia-noite.
- Nome forte de data com **zero** células parseáveis (ex.: coluna `data`
  cheia de texto livre) → não é data; permanece VARCHAR.
- `cep` é checado antes de `telefone`; telefone jamais detecta por conteúdo.
- Nome `cpf` com conteúdo que não casa 100% com 11 dígitos (ex.: `cpf_cnpj`
  misto) → nenhum kind; VARCHAR cru.

Validado tecnicamente em 2026-09-02 contra protótipo: 30/30 casos de
normalização e 13/13 de detecção (incluindo os cenários acima), roundtrip
real em DuckDB 1.5.5 (`typeof` = DATE/TIMESTAMP, predicado `DATE '...'`
funcional), e varredura das 9 tabelas do wiki real
(`~/llm-wiki/database/data.duckdb`): nenhuma coluna existente seria re-tipada.

## 5. Regras de normalização por tipo

### 5.1 Data / Timestamp

Precedência de parsing:

1. `datetime`/`date` Python (XLSX nativo) → uso direto (com fuso → item 5).
2. ISO `YYYY-MM-DD[THH:MM[:SS][.ffffff]][Z|±HH:MM]` — sempre vence.
3. Separadores `/`, `-`, `.`: grupo de 4 dígitos = ano; primeiro grupo ≤ 31
   com segundo ≤ 12 → **dia primeiro** (pt-BR); `DD/MM/AA` → ano 20AA.
   Ambíguo (`01/02/2026`) = 1º de fevereiro.
4. Extenso pt-BR: `2 de setembro de 2026`, `02/set/2026`, `02/setembro/26`
   (meses e abreviaturas de 3 letras, sem acento tolerante).
5. Fuso explícito (`Z`, `±HH:MM`) → convertido para UTC e gravado naive.
6. Data inválida por calendário (`31/02/2025`) → None.

`date`: hora descartada (colunas de nascimento/vencimento não carregam hora
de forma confiável). `timestamp`: data pura → 00:00.

### 5.2 CPF / CNPJ / CEP / telefone

Limpeza base: remover tudo que não for dígito (`re.sub(r"\D", "", v)`);
sem DVI.

- **cpf**: 11 dígitos → mantém; outro tamanho → None.
- **cnpj**: 14 dígitos → mantém; outro tamanho → None.
- **cep**: 8 dígitos → mantém; outro tamanho → None.
- **telefone**: 10–11 dígitos → prefixa `55`; 0 dígitos → None; qualquer
  outro tamanho → mantém os dígitos (legado sem DDD não é destruído).

Idempotência fim-a-fim: valores já normalizados produzem a mesma string
(12 dígitos com DDI não ganha outro `55`; ISO parseia para a mesma data).
`rebuild-json` de JSON já normalizado → banco idêntico.

## 6. Erros, avisos e visibilidade

- `normalize_cell` nunca lança por conteúdo: irrecuperável → `None` (NULL).
- `TableManifest` ganha `normalizations: list[dict]`, um item por coluna
  detectada:

  ```json
  {"column": "dt_nascimento", "kind": "date", "type": "DATE",
   "normalized": 118, "nulled": 3,
   "nulled_examples": ["s/ data", "31/02/2025", "abc"]}
  ```

  `normalized` = células que passaram pela normalização (convertidas ou
  já conformes); `nulled` = células **não-vazias** irrecuperáveis (células
  vazias viram NULL sem contagem — não são perda de normalização);
  `nulled_examples`: até 3 valores originais distintos, truncados a 40
  chars. É o conteúdo do caveat no Source Summary.
- Detecção por conteúdo puro (100% parseável) também aparece no inventário
  com `nulled: 0` — rastreabilidade completa do que mudou de tipo.
- Falha do DuckDB no INSERT continua abortando a transação inteira
  (`RuntimeError`), como hoje.
- **Tabelas existentes não são re-normalizadas automaticamente**; a
  normalização ocorre na ingestão/persistência. Re-ingestão via
  `rebuild_source` produz as tabelas re-tipadas. (No wiki real, varredura de
  2026-09-02 não encontrou coluna que seria alterada.)
- `SKILL.md` (seção de ingest/tabular) e `references/ingest-workflow.md`:
  um bullet cada instruindo o agente a reportar `normalizations` no Source
  Summary e a verificar `kind` no `inspect-file` antes de aprovar dataset de
  documento. Ajustar `tests/test_skill_contract.py` se o contrato atual
  fixar trechos dessas seções.

## 7. Testes

### `tests/test_normalizers.py` (novo — núcleo, sem DuckDB)

- **Datas:** ISO; `DD/MM/AAAA`; `DD-MM-AA`; `DD.MM.AAAA`; `AAAA/MM/DD`;
  ambíguo `01/02/2026` → 1º fev; `15/03/2026` fixa ordem; extenso
  `2 de setembro de 2026`; `02/set/2026`; inválidos → None (`31/02/2025`,
  `s/ data`, `""`, `—`).
- **Timestamps:** `2026-09-02T14:30:00`; `02/09/2026 14:30`; micros;
  `Z` e `±HH:MM` → UTC naive; data pura → 00:00; `02/09/2026 14:30:15.250`.
- **Documentos:** `123.456.789-09` → `12345678909`; `045.106.365-09` preserva
  zero; `111.111.111-11` passa (sem DVI); idempotência; CNPJ
  `12.345.678/0001-95` → `12345678000195`; tamanho errado → None.
- **CEP/telefone:** `01310-100` → `01310100`; `(11) 3456-7890` →
  `551134567890`; 11 dígitos → prefixa 55; 12 com DDI → intacto;
  8 dígitos → sem prefixo; vazio → None.
- **Detecção:** todos os cenários da tabela de colisões da §4 (inclusive
  `data` com texto livre → None; `data_registro` com hora → timestamp;
  `observacao` com 40% datas → None; `cpf_cnpj` misto → None).

### `tests/test_tabular.py` (estende)

- CSV com `cpf`, `data_nascimento`, `telefone` → schema final e valores
  conferidos **pós-SELECT no banco** (não só a função).
- CPF todo dígitos em coluna `cpf` → VARCHAR com zero à esquerda preservado
  (teste de regressão do bug BIGINT).
- `normalizations` no manifest com contagem `nulled` correta e exemplos.
- `inspect-file` reporta `kind` e amostra normalizada.
- `rebuild-json` de dataset já normalizado → conteúdo idêntico (idempotência).

Critério de aceite: suíte inteira verde (`pytest tests/`) + nenhum teste
existente modificado em comportamento, exceto asserts de schema/manifest que
a nova coluna do manifest exigir.

## 8. Fora de escopo

- Validação de dígito verificador (CPF/CNPJ), e-mail, placa, nome próprio.
- Completar DDI além da regra 10–11 dígitos; formatar/mascarar na saída.
- Migração/re-tipagem automática de tabelas já persistidas.
- SQL de normalização em `query_read_only` (continua read-only puro).
- Mudanças na tradução de fórmulas Excel e nos catálogos `_openkm_*`.
