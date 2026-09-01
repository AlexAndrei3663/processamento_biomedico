# Sistema de Aquisição e Monitoramento de Sinais Fisiológicos

Aplicação embarcada para aquisição serial, visualização, processamento e armazenamento contínuo de sinais fisiológicos. O projeto foi desenvolvido para execução em computador convencional ou Raspberry Pi com tela sensível ao toque de 7 polegadas, priorizando modularidade, preservação do dado bruto e operação em tempo quase real.

> **Aviso:** este software é um protótipo acadêmico e de pesquisa. Ele não é um dispositivo médico certificado e não deve ser utilizado isoladamente para diagnóstico, tratamento ou tomada de decisão clínica.

## Visão geral

O sistema recebe quadros multicanais enviados por um microcontrolador, valida a sequência e o timestamp, mantém uma janela circular para visualização, grava integralmente a sessão em HDF5 e permite reabrir, processar, inspecionar e exportar os dados.

Principais recursos:

- aquisição serial multicanal;
- suporte a ECG, PPG, oximetria, temperatura, respiração, EMG, EEG e canais genéricos;
- configuração da ordem dos canais por interface gráfica;
- seleção automática da primeira porta serial disponível;
- interface otimizada para operação por toque em `1024 × 600`;
- visualização temporal e espectral por canal;
- filtros digitais configuráveis;
- seleção por canal entre contagem bruta e tensão diferencial do ADS1256;
- gravação contínua em HDF5, independente do buffer de visualização;
- exportação completa para CSV em blocos;
- verificação SHA-256 da integridade das sessões;
- diagnóstico de sequência, perdas, fila de gravação, CPU, RAM, temperatura e espaço em disco;
- presets de configuração;
- validação sintética ponta a ponta e testes automatizados.

## Arquitetura

A aplicação segue uma separação em camadas:

```text
STM32 / gerador sintético
          │
          ▼
SerialReader + FrameCsvParser
          │
          ▼
LiveAcquisitionService
          │
     ┌────┴───────────────┐
     │                    │
     ▼                    ▼
RingBuffer          RecordingService
(janela visual)      (fila limitada)
     │                    │
     ▼                    ▼
ConversionService   Hdf5SessionWriter
     │                    │
     ▼                    ▼
ProcessingService   sessão HDF5 integral
     │                    │
     ├── filtros          ├── sequence_id
     ├── métricas         ├── timestamp_us
     ├── FFT              └── raw_values
     │
     ▼
Interface PyQt5 / PyQtGraph
```

### Responsabilidades por camada

| Camada | Responsabilidade |
|---|---|
| `serial_monitor/domain` | Modelos, enums e contratos de domínio. |
| `serial_monitor/application` | Regras de aquisição, sessão, conversão, gravação e diagnóstico. |
| `serial_monitor/infrastructure/serial` | Leitura da porta serial e parsing do protocolo. |
| `serial_monitor/infrastructure/storage` | Presets, HDF5, integridade, exportação e compatibilidade com sessões antigas. |
| `serial_monitor/processing` | Buffer circular, filtros, métricas e espectro. |
| `serial_monitor/ui` | Telas, abas e widgets da interface gráfica. |
| `serial_monitor/validation` | Geração sintética, planos e relatórios de validação. |
| `scripts` | Instalação, diagnóstico, benchmark e validação automatizada. |
| `tests` | Testes unitários, de integração e contratos da interface. |

A descrição técnica detalhada está em [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Fluxo dos dados

1. O microcontrolador envia uma linha textual por ciclo multicanal.
2. O parser valida o cabeçalho, a quantidade de campos, os limites dos contadores e os valores numéricos.
3. O monitor de comunicação classifica gaps, frames ausentes, duplicados, fora de ordem, inválidos e regressões temporais.
4. Cada frame aceito segue simultaneamente para:
   - o buffer circular usado pela interface;
   - a fila de gravação contínua.
5. A interface consulta snapshots em uma frequência própria, sem alterar a taxa de aquisição.
6. A gravação escreve o sinal bruto em HDF5 por lotes.
7. A seleção bruto/tensão, os filtros, as métricas e a FFT são produtos derivados e podem ser recalculados.

## Protocolo serial

Formato atual:

```text
FRAME,<sequence_id>,<timestamp_us>,<v0>,<v1>,...,<vN>
```

Exemplo com três canais:

```text
FRAME,205,1000000,123456,124100,81023
```

Contrato:

- `sequence_id`: inteiro sem sinal de 32 bits;
- `timestamp_us`: inteiro sem sinal de 64 bits, em microssegundos desde o boot do firmware;
- `v0 ... vN`: valores dos canais na mesma ordem configurada na interface;
- um frame representa um ciclo de varredura multicanal;
- o timestamp representa o instante da primeira conversão do ciclo;
- o contador pode reiniciar após reinício ou nova conexão do microcontrolador;
- o protocolo atual não transporta CRC; a interface mostra `CRC: n/d`.

## Estrutura de armazenamento

Durante a gravação, o arquivo utiliza a extensão temporária:

```text
session_YYYYMMDD_HHMMSS_mmm.partial.h5
```

Após finalização:

```text
session_YYYYMMDD_HHMMSS_mmm.h5
```

Estrutura principal:

```text
/                       atributos da sessão e diagnósticos
└── frames
    ├── sequence_id     uint32, extensível
    ├── timestamp_us    uint64, extensível
    └── raw_values      float64 [frames, canais], extensível
```

Características:

- o HDF5 preserva as contagens recebidas, sem substituí-las por tensão ou valores filtrados;
- VREF, ganho global do PGA, canais e contrato do protocolo são registrados nos metadados;
- os datasets usam compressão GZIP leve;
- a integridade é verificada por SHA-256 independente do tamanho dos lotes;
- sessões interrompidas encontradas na inicialização são fechadas com o conteúdo confirmado disponível;
- a abertura de sessões longas usa leitura por intervalo e limite de pontos para visualização.

## Requisitos

### Hardware recomendado

- Raspberry Pi 3 B+ ou superior, ou computador com Windows/Linux;
- display de 7 polegadas com resolução `1024 × 600` para uso embarcado;
- porta serial USB, UART ou adaptador compatível;
- microcontrolador responsável pela leitura dos sensores e formação dos frames.

### Software

- Python 3.10 ou superior;
- PyQt5;
- PyQtGraph;
- PySerial;
- NumPy;
- SciPy;
- h5py;
- pytest para executar os testes.

## Instalação

### Windows

No PowerShell, a partir da pasta do projeto:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Caso a política do PowerShell bloqueie a ativação do ambiente virtual, execute uma vez para o usuário atual:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Linux ou Raspberry Pi OS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Também é possível utilizar o instalador incluído:

```bash
chmod +x scripts/install_raspberry.sh
./scripts/install_raspberry.sh
```

Caso o usuário não tenha acesso à porta serial:

```bash
sudo usermod -a -G dialout "$USER"
```

Encerre a sessão do usuário e entre novamente para aplicar a permissão.

Em distribuições que não possuam previamente as bibliotecas do Qt ou do HDF5, pode ser necessário instalar os pacotes de sistema correspondentes antes de executar o `pip`.

## Diagnóstico do ambiente

Após a instalação:

```bash
python scripts/diagnose_environment.py
```

O diagnóstico informa:

- versão do Python;
- sistema operacional e arquitetura;
- disponibilidade das dependências;
- presença do plano de validação;
- portas seriais detectadas.

## Execução

### Modo padrão

```bash
python main.py
```

### Tela cheia para Raspberry Pi

```bash
python main.py \
  --fullscreen \
  --update-interval-ms 250 \
  --max-plot-points 2000
```

Ou:

```bash
chmod +x scripts/run_raspberry.sh
./scripts/run_raspberry.sh
```

### Argumentos disponíveis

| Argumento | Padrão | Função |
|---|---:|---|
| `--fullscreen` | desativado | Abre a interface em tela cheia. |
| `--update-interval-ms` | `100` | Intervalo de atualização da GUI, entre 50 e 2000 ms. |
| `--max-plot-points` | `5000` | Máximo de pontos renderizados por curva. |
| `--data-dir` | `data` | Diretório de sessões e presets. |
| `--recording-queue-capacity` | `8192` | Capacidade máxima da fila de gravação. |
| `--recording-batch-size` | `256` | Quantidade de frames por lote HDF5. |
| `--recording-flush-interval-ms` | `1000` | Intervalo máximo entre flushes. |
| `--minimum-free-disk-mb` | `256` | Espaço mínimo exigido para iniciar a gravação. |
| `--operational-update-interval-ms` | `1000` | Intervalo do diagnóstico de recursos. |

Exemplo completo:

```bash
python main.py \
  --fullscreen \
  --data-dir data \
  --update-interval-ms 250 \
  --max-plot-points 2000 \
  --recording-queue-capacity 8192 \
  --recording-batch-size 512 \
  --recording-flush-interval-ms 2000 \
  --operational-update-interval-ms 2000 \
  --minimum-free-disk-mb 256
```

### Contrato USB CDC

O perfil operacional usa `115200` como baudrate nominal em todos os caminhos do software. A BlackPill transmite por USB CDC, e o firmware parceiro não usa a configuração de line coding para determinar a velocidade física do enlace. O valor unificado evita divergências entre interface, perfil, scripts, testes e metadados; selecionar um número maior não aumenta a vazão física do USB.

O perfil TCC é a fonte autoritativa da sessão: quatro canais, taxa nominal de 1000 Hz, VREF de 2,5 V e PGA 1. A porta serial permanece selecionável em tempo de execução.

## Utilização da interface

### 1. Configurar a sessão

Na página **Configuração**:

1. atualize a lista de portas seriais;
2. selecione a porta serial;
3. confira os parâmetros fixos do perfil TCC exibidos na tela;
4. ajuste o intervalo de atualização da tela conforme o hardware;
5. valide a sessão.

Enquanto o perfil TCC estiver bloqueado, baudrate nominal, taxa base, janela, VREF,
PGA, canais e modos de conversão são somente leitura. A ordem exibida determina a
ordem esperada dos valores no frame serial.

### 2. Conectar e visualizar

Na página **Visualização ao vivo**:

1. pressione **Conectar**;
2. confira o estado da comunicação;
3. selecione a aba do canal;
4. escolha entre **Base** e **Processado**;
5. alterne entre visualização temporal e espectral;
6. habilite ou desabilite filtros;
7. use `+`, `−`, a roda do mouse ou o gesto equivalente para zoom horizontal;
8. desative **Seguir** para inspecionar uma faixa fixa e reative-o para acompanhar o timestamp mais recente;
9. use **Focar** para ampliar o gráfico sem ultrapassar a tela;
10. use **Limpar** apenas para reiniciar a janela visual e a referência da sequência.

O eixo temporal acompanha o `timestamp_us` recebido e avança com a sessão. O zoom altera apenas o `ViewBox`; não recalcula filtros, FFT nem relê a serial. Limpar o gráfico não remove dados já gravados.

### 3. Gravar uma sessão

1. valide a configuração;
2. conecte a serial;
3. pressione **Gravar**;
4. acompanhe duração, frames, fila, arquivo, perdas e recursos;
5. pressione **Finalizar** para fechar corretamente o HDF5;
6. utilize **Cancelar** apenas quando a sessão não deva ser mantida.

Se a fila atingir a capacidade máxima, a gravação é interrompida para evitar perda silenciosa.

### 4. Abrir e exportar sessões

Na página **Sessões**:

- atualize a lista;
- selecione uma sessão;
- verifique a integridade;
- defina início, duração e máximo de pontos;
- abra apenas o intervalo necessário;
- exporte a sessão completa para CSV;
- acompanhe ou cancele a exportação.

## Seleção do sinal base e conversão do ADS1256

O microcontrolador transmite a contagem assinada de 24 bits produzida pelo ADC. A gravação HDF5 preserva sempre esse valor recebido. Na configuração, cada canal escolhe qual sinal será usado como **base** na interface e no processamento:

- **Contagem bruta:** unidade `count`;
- **Tensão diferencial na entrada do ADC:** unidade `V`.

O ADS1256 é considerado no modo diferencial, de modo que a tensão corresponde a `AINP − AINN`. A tensão de referência e o ganho do PGA são globais para todos os canais e devem coincidir com a configuração física e com o firmware. No perfil TCC vigente, VREF é 2,5 V e o PGA é 1. Ganhos aceitos pelo modelo geral: `1`, `2`, `4`, `8`, `16`, `32` e `64`.

A faixa nominal é:

```text
VFS = ±(2 × VREF / PGA)
```

A conversão trata separadamente os extremos positivo e negativo do complemento de dois:

```text
count >= 0: V = count × VFS / 8_388_607
count <  0: V = count × VFS / 8_388_608
```

A tela ao vivo não apresenta um modo independente chamado “convertido”. Ela oferece somente:

- **Base:** bruto ou tensão, conforme selecionado na configuração;
- **Processado:** o mesmo sinal base após os filtros ativos.

A tensão calculada é a tensão diferencial na entrada do ADS1256. Ela não recompõe automaticamente a tensão original nos eletrodos ou no sensor, pois o front-end analógico pode aplicar ganho, offset e filtragem.

Antes de uma aquisição quantitativa, confirme por medição a tensão entre `VREFP` e `VREFN` e registre o valor usado. Para VREF de 2,5 V e PGA 1, os códigos `-8_388_608`, `0` e `8_388_607` correspondem nominalmente a `-5 V`, `0 V` e `+5 V`. Essa é a faixa diferencial; cada entrada também deve respeitar seus limites absolutos em relação a `AGND` e `AVDD`.

O arquivo `config/conversion_profiles.json` é mantido apenas para ensaios automatizados e compatibilidade com sessões antigas que usavam perfis genéricos. Ele não é necessário para a conversão ADS1256 da interface atual.

## Processamento de sinais

Filtros disponíveis:

- remoção de linha de base;
- remoção de nível DC;
- passa-altas;
- notch de 60 Hz;
- passa-faixa;
- passa-baixas;
- média móvel;
- envelope.

Métricas básicas:

- média;
- RMS;
- mínimo;
- máximo.

O espectro é calculado por FFT unilateral, com frequência dominante, magnitude de pico e resolução espectral.

Os filtros atuais são aplicados sobre janelas com processamento não causal. Por isso, a descrição correta do sistema é **aquisição contínua com processamento e visualização em tempo quase real**, e não filtragem causal em tempo real estrito.

### Medidas de redução de processamento

Durante a operação ao vivo:

- somente a aba visível é convertida, filtrada e atualizada;
- nenhuma FFT é calculada no domínio temporal;
- no domínio espectral, calcula-se apenas o espectro atualmente selecionado, base ou processado;
- snapshots sem nova sequência não são redesenhados;
- páginas que não exibem gráficos não executam o pipeline gráfico;
- o gráfico recebe no máximo `max_plot_points`;
- títulos, rótulos e faixas são reaplicados somente quando necessário;
- o diagnóstico de CPU, RAM, temperatura e disco só atualiza a tela ao vivo quando ela está visível;
- o resumo da configuração usa diretamente o buffer bruto, sem conversão, filtros, métricas ou FFT;
- mensagens de log ficam em uma fila limitada enquanto a página de configuração não está visível e são inseridas no widget em lote ao abrir a página;
- erros de protocolo são contabilizados individualmente, mas relatados graficamente de forma agregada, no máximo uma vez por segundo.

## Validação automatizada

O projeto possui quatro ciclos progressivos definidos em:

```text
config/validation_plan.json
```

Execução rápida:

```bash
python scripts/run_validation.py \
  --cycle cycle1_ecg \
  --profile smoke
```

Todos os ciclos:

```bash
python scripts/run_validation.py \
  --cycle all \
  --profile smoke
```

Perfis de duração:

- `smoke`: 2 segundos;
- `one_minute`: 60 segundos;
- `one_hour`: 3600 segundos;
- `eight_hours`: 28800 segundos.

Para respeitar a duração física:

```bash
python scripts/run_validation.py \
  --cycle cycle1_ecg \
  --profile one_hour \
  --real-time
```

Sem `--real-time`, o gerador produz os frames de forma acelerada para testar o pipeline.

Artefatos padrão:

```text
data/validation/
├── sessions/
├── csv/
└── reports/
```

O plano de ensaios físicos está em [`docs/VALIDATION_PLAN.md`](docs/VALIDATION_PLAN.md), e o formulário de registro está em [`docs/manual_test_record.csv`](docs/manual_test_record.csv).

## Benchmark de gravação

```bash
python scripts/benchmark_recording.py \
  --frames 100000 \
  --channels 3
```

Para manter o arquivo gerado:

```bash
python scripts/benchmark_recording.py \
  --frames 100000 \
  --channels 3 \
  --output-dir data/benchmark
```

## Testes

```bash
python -m pytest
```

Compilação dos módulos:

```bash
python -m compileall -q serial_monitor tests scripts
```

## Estrutura do repositório

```text
.
├── config/
│   ├── conversion_profiles.json
│   └── validation_plan.json
├── docs/
│   ├── ARCHITECTURE.md
│   ├── OPERATIONAL_REVIEW.md
│   ├── VALIDATION_PLAN.md
│   ├── VALIDATION_SMOKE_RESULTS.md
│   └── manual_test_record.csv
├── scripts/
│   ├── benchmark_recording.py
│   ├── diagnose_environment.py
│   ├── install_raspberry.sh
│   ├── run_raspberry.sh
│   └── run_validation.py
├── serial_monitor/
│   ├── app/
│   ├── application/
│   ├── domain/
│   ├── infrastructure/
│   ├── processing/
│   ├── ui/
│   └── validation/
├── tests/
├── main.py
├── pytest.ini
├── requirements.txt
└── README.md
```

## Diretórios gerados em execução

```text
data/
├── sessions/         arquivos HDF5 e CSV
├── config_presets/   presets da interface
└── validation/       artefatos dos ensaios automatizados
```

O diretório `data/` é ignorado pelo Git por padrão.

## Limitações conhecidas

- o protocolo textual atual não possui CRC;
- os canais agrupados representam uma varredura sequencial, não amostras fisicamente simultâneas;
- a taxa configurada ainda deve ser comparada com a taxa efetiva obtida pelos timestamps;
- a leitura serial entrega frames ao controlador Qt por sinais; a suficiência desse modelo deve ser confirmada em ensaios prolongados;
- temperatura de CPU pode não estar disponível fora do Linux/Raspberry Pi;
- a conversão nominal para tensão não substitui a calibração do ADC nem a caracterização do front-end analógico;
- os ensaios sintéticos não substituem gerador de funções, osciloscópio, hardware completo ou equipamento biomédico de referência.

## Documentação complementar

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): decisões arquiteturais e fluxo interno;
- [`docs/OPERATIONAL_REVIEW.md`](docs/OPERATIONAL_REVIEW.md): estado operacional e pendências conscientes;
- [`docs/VALIDATION_PLAN.md`](docs/VALIDATION_PLAN.md): sequência de validação progressiva;
- [`docs/VALIDATION_SMOKE_RESULTS.md`](docs/VALIDATION_SMOKE_RESULTS.md): resultado de referência dos ensaios rápidos.

## Licença e uso

O repositório ainda não contém um arquivo de licença. Até que uma licença seja definida, o uso, redistribuição e incorporação em outros projetos devem ser autorizados pelos autores.


### Escalas e navegação do gráfico

Na aba de cada canal, os botões **+** e **−** controlam somente o zoom
horizontal. O botão **Seguir** retorna a janela ao timestamp mais recente.

No domínio do tempo há duas escalas verticais:

- **Automática**: acompanha a amplitude presente na janela exibida;
- **Faixa completa do ADC**: fixa o eixo entre os limites teóricos do ADS1256.
  Para contagens, a faixa é `-8388608` a `8388607`. Para tensão, a faixa é
  `±(2 × VREF / PGA)`.

No espectro há duas escalas de magnitude:

- **Magnitude linear**: mantém a apresentação original na unidade do sinal;
- **dBFS**: usa `20·log10(magnitude/escala_completa)` e piso visual de
  `-160 dBFS`. A troca de escala não recalcula a FFT; apenas transforma o
  vetor de magnitude já calculado para a aba visível.
