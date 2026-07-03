# Modos de exibição do gráfico

## Zoom horizontal

Os botões `+` e `−` atuam somente sobre a transformação horizontal do
`ViewBox` do PyQtGraph. A operação não refaz a conversão, os filtros ou a FFT,
e não altera a aquisição nem a gravação. O custo é restrito ao redesenho dos
pontos já enviados à curva, limitado por `max_plot_points`.

Os botões possuem área mínima de 58 × 40 pixels para facilitar o uso em tela
touch de 7 polegadas. O modo **Seguir** mantém a extremidade direita da janela
no timestamp mais recente; qualquer navegação manual desativa esse modo.

## Escala vertical no domínio do tempo

### Automática

O eixo Y acompanha os valores presentes na janela de visualização. Esse modo
favorece a inspeção de sinais de pequena amplitude, mas pode produzir variação
visual da escala quando surgem novos extremos.

### Faixa completa do ADC

O eixo Y permanece travado nos limites teóricos do ADS1256:

- contagem bruta: `-8388608` a `8388607`;
- tensão diferencial: `±(2 × VREF / PGA)`.

Como o ganho do PGA é global, todos os canais convertidos compartilham a mesma
faixa de tensão. Esse modo não executa cálculo adicional por atualização; apenas
reutiliza limites previamente conhecidos.

## Escala do espectro

### Magnitude linear

Mantém a magnitude unilateral calculada pela FFT na unidade base do canal.

### dBFS

Aplica apenas uma transformação vetorial ao espectro linear já calculado:

`20 × log10(magnitude / escala_completa)`

A referência é `8388607 counts` ou `2 × VREF / PGA volts`. O piso visual é
`-160 dBFS`, evitando valores infinitos para componentes nulos.

Não existe uma segunda FFT. Para uma janela com `N` amostras, a transformação
atua sobre aproximadamente `N/2 + 1` bins e utiliza operações vetorizadas do
NumPy. Como o sistema calcula o espectro somente para a aba visível e somente
quando o domínio espectral está selecionado, o custo adicional é pequeno em
comparação com a própria FFT e com a renderização do gráfico.
