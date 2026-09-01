# Estado operacional e pendências

## Funcionalidades atendidas

- interface dimensionada para `1024 × 600`;
- botões, abas e controles adequados ao toque;
- configuração principal sem necessidade de teclado;
- primeira porta serial e primeiro preset selecionados automaticamente;
- controles de conexão e gravação visíveis em tela cheia;
- painel lateral rolável e foco do gráfico sem extrapolar a tela;
- zoom e pan horizontais com modo de acompanhamento do timestamp;
- exibição de duração, frames, fila, arquivo e destino da gravação;
- diagnóstico de frames ausentes, inválidos, disco, CPU, RAM e temperatura;
- separação entre atualização gráfica, aquisição e escrita HDF5;
- log gráfico atualizado apenas na página de configuração;
- agregação das mensagens de protocolo inválido;
- desconexão serial não bloqueante e estado visual imediato;
- desconexão automática antes de validar uma nova configuração;
- seleção por canal entre contagem bruta e tensão diferencial;
- VREF e ganho do PGA globais para todos os canais;
- pré-verificação configurável de espaço livre;
- integridade HDF5 independente do tamanho dos lotes;
- validação da sessão com retorno booleano explícito.

## Convenções operacionais

- `CRC: n/d` é exibido enquanto o protocolo textual não transportar CRC;
- limpar a visualização reinicia a referência de sequência e timestamp, mas não apaga a gravação;
- o primeiro frame válido após reconexão estabelece uma nova referência temporal;
- a tela mostra apenas `Base` e `Processado`;
- `Base` significa contagem bruta ou tensão, conforme a configuração do canal;
- a tensão calculada corresponde a `AINP − AINN` na entrada do ADS1256;
- filtros são calculados por janela, portanto o sistema opera em tempo quase real, não em filtragem causal estrita.

## Estratégia de desempenho

- apenas a aba visível é processada;
- FFT é calculada somente no domínio espectral e apenas para a série selecionada;
- snapshots repetidos não são redesenhados;
- a configuração consulta diretamente o buffer bruto;
- o diagnóstico operacional não atualiza widgets fora da página ao vivo;
- o zoom atua somente no `ViewBox`;
- mensagens de log ficam em uma fila limitada quando a configuração está oculta;
- erros de protocolo continuam sendo contabilizados, mas são reportados à GUI em blocos.

## Pendências conscientes

A leitura serial ocorre em `QThread`, mas cada frame válido é entregue ao controlador Qt por sinal. Os ensaios de taxa, fila e perdas devem confirmar se essa arquitetura é suficiente no hardware final. Caso haja crescimento contínuo da fila de eventos ou perdas em aquisição prolongada, o consumo dos frames deverá migrar para um worker dedicado independente da thread da interface.

O tratamento de erro de protocolo foi mantido porque é útil para detectar porta, protocolo e firmware incompatíveis. Se os ensaios na Raspberry Pi mostrarem custo relevante, a primeira simplificação recomendada é manter apenas contadores acumulados e a desconexão por ausência de frames válidos, eliminando a mensagem de exemplo. A remoção completa do diagnóstico só deve ser considerada se houver evidência experimental de impacto.

O protocolo atual não inclui CRC. A adoção de integridade no enlace deve ser avaliada após medir a vazão e a margem do USB CDC. O baudrate 115200 é nominal e não controla a velocidade física desse enlace no firmware atual.
