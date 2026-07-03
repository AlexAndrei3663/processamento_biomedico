# Plano de validação progressiva

## Regra de avanço

Um ciclo somente deve ser considerado concluído quando todas as etapas abaixo forem
executadas e registradas:

```text
adquirir → transmitir → gravar → reabrir → converter → filtrar → visualizar → exportar → validar
```

## Ciclo 1 — um ECG

1. Executar o ensaio sintético.
2. Aplicar senoide, quadrada e triangular com gerador de funções.
3. Comparar frequência, amplitude, offset e forma com o osciloscópio.
4. Adquirir ECG pelo AD8232.
5. Executar uma gravação contínua de uma hora.
6. Verificar HDF5, CSV, taxa efetiva, jitter, perdas e recursos.

## Ciclo 2 — dois ECG

Repetir o ciclo completo com duas derivações e confirmar:

- ordem dos canais;
- separação elétrica e lógica;
- sincronismo do ciclo multiplexado;
- ausência de troca entre canais;
- impacto na taxa efetiva.

## Ciclo 3 — PPG

Adicionar PPG somente após os dois ECG estarem concluídos. Validar:

- nível DC;
- componente pulsátil;
- frequência cardíaca;
- sensibilidade a movimento e iluminação;
- conversão e filtragem reproduzíveis.

## Ciclo 4 — oximetria independente

Adicionar o canal lógico de SpO2 e validar:

- unidade percentual;
- faixa admissível;
- comportamento em perda de leitura;
- independência em relação ao PPG analógico;
- sincronização ou identificação explícita de assincronia.

## Ensaios de robustez

Registrar separadamente:

- reinício do STM32;
- desconexão e reconexão do cabo;
- encerramento inesperado da aplicação;
- fila próxima da saturação;
- pouco espaço livre em disco;
- sessão de uma hora;
- sessão de oito horas;
- uso exclusivamente por toque em 1024 × 600.

## Evidências mínimas

Para cada execução, preservar:

- arquivo HDF5;
- CSV exportado;
- relatório JSON;
- relatório Markdown;
- fotografia da bancada;
- captura da interface;
- configuração do gerador;
- configuração do osciloscópio;
- versão do firmware e commit do software.
