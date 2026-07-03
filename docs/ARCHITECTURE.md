# Arquitetura do sistema

## Objetivos arquiteturais

A implementação foi organizada para atender aos seguintes requisitos:

- preservar integralmente o sinal bruto recebido;
- separar aquisição, gravação, processamento e renderização;
- impedir que o tamanho da janela visual limite a sessão armazenada;
- permitir reprocessamento posterior com conversões e filtros reproduzíveis;
- operar em Raspberry Pi com interface sensível ao toque;
- detectar perdas, duplicações, reordenação e regressões temporais;
- suportar sessões longas sem carregá-las integralmente em memória.

## Pipeline principal

```text
Porta serial
    │
    ▼
SerialReader (QThread)
    │ linha textual
    ▼
FrameCsvParser
    │ SampleFrame validado
    ▼
MainController
    │
    ├── LiveAcquisitionService
    │      ├── CommunicationMonitor
    │      └── RingBuffer por canal
    │
    ├── RecordingService
    │      ├── fila limitada
    │      ├── thread de escrita
    │      └── Hdf5SessionWriter
    │
    └── ProcessingService
           ├── ConversionService
           ├── FilterPipeline
           ├── métricas
           └── Spectrum
```

## Separação entre visualização e armazenamento

O `RingBuffer` contém apenas a janela necessária para o gráfico. Cada frame aceito é também encaminhado diretamente para o `RecordingService`, que escreve em HDF5 por meio de uma fila limitada e uma thread dedicada.

Consequências:

- limpar o gráfico não remove amostras gravadas;
- congelar ou reduzir a frequência da GUI não reduz a sessão armazenada;
- uma sessão de 100.000 frames pode usar uma janela visual de 5.000 frames sem perda no arquivo;
- saturação da fila gera falha explícita, em vez de descarte silencioso.

## Contrato temporal

O protocolo utiliza uma única sequência por ciclo multicanal:

```text
FRAME,<sequence_id>,<timestamp_us>,<v0>,...,<vN>
```

- `sequence_id` é `uint32` e avança uma vez por ciclo;
- `timestamp_us` é `uint64` e representa a primeira conversão do ciclo;
- a origem temporal é estabelecida pelo primeiro frame válido após conexão ou reset visual;
- o eixo X mantém a progressão baseada nos timestamps, mesmo após sobrescrita do buffer circular;
- gaps, duplicações, fora de ordem e regressões temporais são contabilizados separadamente.

## Processamento derivado

A cadeia lógica é:

```text
valor bruto
   ├── armazenamento HDF5
   └── conversão opcional
          └── filtros
                 ├── métricas
                 ├── FFT
                 └── interface
```

A conversão é desativada por padrão. Quando habilitada, o perfil completo é copiado para os metadados da sessão.

## HDF5

Datasets extensíveis:

```text
/frames/sequence_id
/frames/timestamp_us
/frames/raw_values
```

Metadados relevantes:

- versões do formato, software e protocolo;
- estado e motivo de encerramento;
- configuração serial;
- configuração e ordem dos canais;
- perfis de conversão;
- filtros ativos;
- diagnósticos de comunicação;
- timestamps inicial e final;
- quantidade confirmada de frames;
- hash SHA-256.

## Sessões longas

O repositório localiza intervalos por timestamp e lê somente a faixa solicitada. Quando o intervalo contém mais pontos do que o limite visual, a redução é feita apenas para exibição. O HDF5 permanece inalterado e a exportação CSV continua integral.

## Diagnóstico operacional

O `OperationalMonitor` coleta, quando disponível:

- uso de CPU;
- uso de memória;
- temperatura do processador;
- espaço livre no volume das sessões.

No Linux, a implementação consulta `/proc` e `/sys`. Em outras plataformas, campos indisponíveis são apresentados como `--` sem interromper a aplicação.

## Integridade

Cada dataset possui uma cadeia SHA-256 independente. Os resumos de sequência, timestamp e valores são combinados em um hash canônico, tornando a verificação independente do tamanho dos lotes usados na gravação.

## Interface

A janela principal contém quatro áreas:

- menu;
- configuração;
- visualização ao vivo;
- sessões armazenadas.

O layout ao vivo foi dimensionado para `1024 × 600`, com controles de conexão e gravação permanentemente visíveis, painel lateral rolável e modo de foco que amplia somente a área do gráfico.

## Validação

A validação automatizada percorre:

```text
geração → aquisição → gravação → reabertura → conversão → filtragem → FFT → exportação → integridade
```

Os ciclos progressivos estão definidos em `config/validation_plan.json` e produzem relatórios JSON e Markdown.
