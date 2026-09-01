# Arquitetura do sistema

## Objetivos arquiteturais

A implementação foi organizada para:

- preservar integralmente a contagem bruta recebida do microcontrolador;
- separar aquisição, gravação, processamento e renderização;
- impedir que o tamanho da janela visual limite a sessão armazenada;
- permitir a escolha por canal entre contagem bruta e tensão diferencial;
- operar em Raspberry Pi com tela sensível ao toque de 7 polegadas;
- detectar perdas, duplicações, reordenação e regressões temporais;
- suportar sessões longas sem carregá-las integralmente em memória;
- manter a interface responsiva mesmo diante de porta, protocolo ou firmware incompatível.

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
    └── ProcessingService — somente canal visível
           ├── ConversionService: count ou V
           ├── FilterPipeline
           ├── métricas
           └── Spectrum sob demanda
```

## Separação entre visualização e armazenamento

O `RingBuffer` contém apenas a janela necessária para o gráfico. Cada frame aceito é também encaminhado diretamente para o `RecordingService`, que escreve em HDF5 por uma fila limitada e uma thread dedicada.

Consequências:

- limpar o gráfico não remove amostras gravadas;
- congelar, ampliar ou reduzir a frequência da GUI não reduz a sessão armazenada;
- uma sessão de 100.000 frames pode usar uma janela visual de 5.000 frames sem perda no arquivo;
- saturação da fila gera falha explícita, em vez de descarte silencioso.

## Contrato temporal

O protocolo utiliza uma única sequência por ciclo multicanal:

```text
FRAME,<sequence_id>,<timestamp_us>,<v0>,...,<vN>
```

- `sequence_id` é `uint32` e avança uma vez por ciclo;
- `timestamp_us` é `uint64` e representa a primeira conversão do ciclo;
- o primeiro frame válido depois de cada conexão estabelece uma nova referência;
- o eixo X mantém a progressão dos timestamps mesmo após sobrescrita do buffer;
- gaps, ausentes, duplicados, fora de ordem e regressões temporais são contabilizados separadamente.

## Robustez da conexão serial

O leitor mantém estados visuais de conexão, conexão em andamento e desconexão em andamento. A solicitação de parada não bloqueia a thread da interface: tenta cancelar a leitura da porta e depende de um timeout curto como alternativa.

Erros de protocolo são contabilizados no leitor, mas chegam à GUI de forma agregada, no máximo uma vez por segundo. Quando nenhum frame válido é reconhecido após um período de tolerância e uma quantidade mínima de erros, a conexão é encerrada com orientação para verificar porta e firmware. O baudrate nominal é fixado em 115200 por consistência; no USB CDC atual ele não determina a velocidade física do enlace.

Uma nova validação de configuração sempre solicita primeiro a desconexão da serial. A configuração só é reconstruída após o sinal de encerramento da conexão.

## Sinal base e processamento derivado

A cadeia lógica é:

```text
contagem assinada do ADS1256
   ├── armazenamento HDF5
   └── seleção por canal
          ├── contagem bruta [count]
          └── tensão diferencial [V]
                    │
                    ▼
                sinal base
                    │
                    ▼
                  filtros
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
       métricas              FFT
```

A tensão de referência e o ganho do PGA são globais para todos os canais. A conversão considera o ADS1256 em modo diferencial e trata a assimetria dos extremos do complemento de dois de 24 bits.

A interface expõe apenas `Base` e `Processado`. A nomenclatura “convertido” é mantida somente em estruturas internas antigas necessárias à compatibilidade de arquivos e testes históricos.

## Redução de processamento na interface

O caminho ao vivo é deliberadamente seletivo:

- somente o canal da aba visível passa por conversão, filtros e métricas;
- FFT não é calculada no domínio temporal;
- no domínio espectral, somente o espectro base ou processado atualmente selecionado é calculado;
- snapshots sem nova sequência não provocam novo desenho;
- a página de configuração mostra um resumo direto dos buffers brutos;
- o diagnóstico operacional só atualiza widgets quando a página ao vivo está visível;
- o número de pontos entregue ao PyQtGraph é limitado;
- o zoom horizontal altera apenas a transformação do `ViewBox`;
- logs são acumulados em uma fila limitada quando a configuração está oculta e inseridos no widget em lote ao abri-la.

Essas decisões preservam a aquisição e a gravação integral enquanto reduzem o trabalho da thread principal do Qt.

## Navegação temporal

O gráfico permite pan e zoom apenas no eixo X. O eixo Y permanece bloqueado para evitar alterações acidentais em tela sensível ao toque.

No modo `Seguir`, a janela acompanha o timestamp mais recente. Uma alteração manual da faixa desativa esse modo e preserva a região escolhida. Reativar `Seguir` reposiciona a janela no fim do sinal. O zoom usa apenas os pontos já entregues ao gráfico; não relê HDF5 nem recalcula filtros.

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
- modelo e modo do ADC;
- VREF e ganho global do PGA;
- seleção bruto/tensão por canal;
- filtros ativos;
- diagnósticos de comunicação;
- timestamps inicial e final;
- quantidade confirmada de frames;
- hash SHA-256.

## Sessões longas

O repositório localiza intervalos por timestamp e lê somente a faixa solicitada. Quando o intervalo contém mais pontos que o limite visual, a redução é feita apenas para exibição. O HDF5 permanece inalterado e a exportação CSV continua integral.

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

Os ciclos progressivos estão definidos em `config/validation_plan.json` e produzem relatórios JSON e Markdown. O arquivo `config/conversion_profiles.json` permanece disponível apenas para exercitar modelos legados durante a validação.
