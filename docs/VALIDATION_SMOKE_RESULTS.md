# Resultado da validação sintética de referência

Foram executados os quatro ciclos do plano com o perfil `smoke`, contendo 2 segundos e 1.000 frames por ciclo a 500 Hz.

| Ciclo | Canais | Frames gravados | Resultado |
|---|---:|---:|---|
| cycle1_ecg | 1 | 1.000 | aprovado |
| cycle2_two_ecg | 2 | 1.000 | aprovado |
| cycle3_ppg | 3 | 1.000 | aprovado |
| cycle4_oximetry | 4 | 1.000 | aprovado |

A suíte automatizada resultou em:

```text
79 passed
```

A compilação com `compileall` foi concluída sem erros. Este ambiente não possui PyQt5, portanto a validação visual da interface continua dependente da Raspberry Pi ou de um computador com as dependências gráficas instaladas.
