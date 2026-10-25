# radio-python

Player de rádio no terminal com cara de DOS/CGA (CA-Clipper old school). Toca
estações de rádio via [mpv](https://mpv.io), tudo em uma TUI feita com
`curses` puro (biblioteca padrão do Python, sem dependências externas de UI).

```
 RADIO.EXE  │ v1.0 │ 123 estações (online)                              14:32
  Todas   News   Rock   Gaúcha   Geral
╔══ Estações (123) ═══════════════════════════════════════════════════════╗
║ ♪ Antena 1                                                        Rock  ║
║   BBC World Service                                                News ║
...
```

## Requisitos

- Python 3.8+ (só biblioteca padrão — `curses`, `json`, `socket`, etc.)
- [`mpv`](https://mpv.io) instalado e no `PATH` (toca o áudio via socket IPC)

Instalando o mpv:

```bash
# Debian/Ubuntu
sudo apt install mpv

# Arch
sudo pacman -S mpv

# macOS (Homebrew)
brew install mpv
```

## Como rodar

```bash
python3 radio.py
```

Lista de estações vem de `https://www.allan.lat/radio.html` (com cache local
em `~/.cache/radio/stations.json` pra funcionar offline depois da primeira
vez). Quer apontar pra outra fonte? É só trocar a constante `SITE` no topo
do arquivo.

## Atalhos

| Tecla              | Ação                                   |
|---------------------|-----------------------------------------|
| `↑` `↓` `PgUp` `PgDn` `Home` `End` | navegar na lista          |
| `←` `→` ou `Tab`    | trocar categoria                       |
| `Enter`             | tocar a estação selecionada            |
| `Espaço`            | pausar / continuar                     |
| `S`                 | parar                                  |
| `+` `-`             | volume                                 |
| `/`                 | buscar pelo nome (`Esc` limpa)          |
| `R`                 | recarregar lista do site               |
| `K`                 | trocar skin (veja abaixo)              |
| `F1`                | ajuda                                  |
| `F8`                | como adicionar novas rádios            |
| `Q` ou `F10`        | sair                                   |

Mouse também funciona: clica numa categoria, numa estação (toca na hora),
na barra de rolagem, na barra de volume e em cada item do rodapé.

## Skins

Aperte `K` pra ciclar entre 4 esquemas de cor (fica salvo em
`~/.config/radio/state.json`, então abre direto na última escolhida):

- **Azul** (padrão) — o visual CGA/DOS azul clássico.
- **PC-XT** — mono fósforo verde, estilo monitor CGA/Hercules dos anos 80.
- **Vermelha** — a mesma paleta da Azul, só com o fundo em tons de vermelho.
- **Preta** — mono fósforo branco (preto e branco puro).

## Adicionando suas próprias rádios

As estações vêm de duas fontes (também tem um resumo disso dentro do
programa, tecla `F8`):

1. **Online**: o HTML apontado pela constante `SITE` (topo do arquivo),
   contendo um array `const STATIONS = [...]` com objetos `{n, u, t}`.
2. **Cache local**: `~/.cache/radio/stations.json` — uma lista JSON simples:

```json
[{"n": "Nome da Rádio", "u": "http://stream.url/exemplo", "t": "Categoria"}]
```

Edite esse arquivo à mão e tecle `R` pra recarregar. Só uma pegadinha: se
`SITE` estiver acessível, ele sobrescreve esse cache no próximo `R`. Pra
manter sua lista fixa, troque `SITE` pelo seu próprio HTML ou deixe-a
apontando pra algo inválido/offline.

## Estado salvo

Fica tudo em `~/.config/radio/state.json`: última estação, categoria, volume
e skin escolhida. Pode apagar o arquivo pra resetar.
