# Dados de exemplo – experimento EXP37

`sensor_log_EXP37.csv` é o registro completo de um experimento com coração isolado de coelho no sistema de Langendorff do HEartLab, feito em **30/04/2026, das 10h10 às 15h23** (cerca de 5 h 13 min).

| Item | Valor |
|---|---|
| Linhas | 92 831 (uma a cada ~200 ms) |
| Separador | vírgula (`,`) |
| Cabeçalho | não tem – a primeira linha já é dado |
| Versão | registro de uma versão anterior do sistema (pacote `SN1`); o formato é diferente do CSV gerado hoje por `monitor_esp32.py` |

## Colunas

| Nº | Conteúdo | Unidade | Faixa no EXP37 |
|---|---|---|---|
| 1 | Data e hora (`AAAA-MM-DD hh:mm:ss.mmm`) | – | 10:10:53 a 15:23:39 |
| 2 | Identificador do pacote (`SN1`) | – | – |
| 3 | Início da gravação do **mapeamento elétrico** (0/1) | – | 1 durante ~10 s a cada gravação |
| 4 | Início da gravação do **mapeamento óptico** (0/1) | – | 1 durante ~10 s a cada gravação |
| 5 | Temperatura do tanque de imersão (termopar tipo K + MAX6675) | °C | 23,25 a 25,25 |
| 6 | Vazão de perfusão (Sensirion SLF3S-4000B) | ml/min | 0 a ~40 (picos por bolhas de ar) |
| 7 | Temperatura de perfusão (Sensirion SLF3S-4000B) | °C | ~39 a ~41,5 |
| 8 | Pressão de perfusão (Honeywell ABPDANN005PG2A3) | mmHg | sobe de ~38 para ~69 ao longo do experimento |

As colunas 3 e 4 permitem sincronizar as variáveis do perfusato com os registros elétricos e ópticos. No EXP37 há 3 marcações só do elétrico (10h11, 10h34 e 10h36) e 18 marcações simultâneas do elétrico e do óptico (de 12h10 a 15h09).

Os picos isolados de vazão (até ±327 ml/min) vêm de bolhas de ar no sensor de fluxo, como discutido no relatório (seção 4.3), e não correspondem a eventos fisiológicos.

## Leitura rápida em Python

```python
import pandas as pd

cols = ["timestamp", "id", "rec_eletrico", "rec_optico",
        "temp_tanque", "fluxo", "temp_fluxo", "pressao"]
df = pd.read_csv("sensor_log_EXP37.csv", header=None, names=cols,
                 parse_dates=["timestamp"])
df.plot(x="timestamp", y=["pressao", "fluxo", "temp_fluxo"], subplots=True)

# instantes em que cada gravação começou
inicio_optico = df.loc[df.rec_optico.diff() == 1, "timestamp"]
inicio_eletrico = df.loc[df.rec_eletrico.diff() == 1, "timestamp"]
```
