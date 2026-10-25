#!/usr/bin/env python3
"""RADIO.EXE — player de rádio com cara de DOS.

Estações vêm de https://www.allan.lat/radio.html (cache local se offline).
Toca via mpv (IPC socket), que dá conta de mp3/aac/icecast/HLS.
"""
import curses
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request

VERSION = "1.1"
BUILD_DATE = "2026-10-25"

SITE = "https://www.allan.lat/radio.html"
CACHE_DIR = os.path.expanduser("~/.cache/radio")
CACHE = os.path.join(CACHE_DIR, "stations.json")
STATE = os.path.expanduser("~/.config/radio/state.json")
SOCK = os.path.join(tempfile.gettempdir(), f"radio-mpv-{os.getuid()}.sock")


# ---------------------------------------------------------------- estações
def load_stations():
    try:
        req = urllib.request.Request(SITE, headers={"User-Agent": "radio.py"})
        html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8")
        m = re.search(r"const STATIONS = (\[.*?\]);\s*$", html, re.M)
        stations = json.loads(m.group(1))
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE, "w") as f:
            json.dump(stations, f, ensure_ascii=False)
        return stations, "online"
    except Exception:
        try:
            with open(CACHE) as f:
                return json.load(f), "cache"
        except Exception:
            return [], "sem lista"


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        with open(STATE, "w") as f:
            json.dump(st, f, ensure_ascii=False)
    except Exception:
        pass


def fold(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


# ---------------------------------------------------------------- mpv
class Mpv:
    def __init__(self, volume):
        if os.path.exists(SOCK):
            os.unlink(SOCK)
        self.proc = subprocess.Popen(
            ["mpv", "--idle=yes", "--no-video", "--no-terminal",
             "--input-ipc-server=" + SOCK, f"--volume={volume}",
             "--cache=yes", "--network-timeout=15"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        self.sock = None
        for _ in range(50):
            try:
                self.sock = socket.socket(socket.AF_UNIX)
                self.sock.connect(SOCK)
                break
            except OSError:
                self.sock = None
                time.sleep(0.1)
        if self.sock is None:
            raise RuntimeError("não consegui falar com o mpv")
        self.sock.setblocking(False)
        self.buf = b""
        self.events = []
        self.props = {}
        for i, p in enumerate(("media-title", "pause", "volume",
                               "paused-for-cache", "idle-active"), 1):
            self.cmd("observe_property", i, p)

    def cmd(self, *args):
        try:
            self.sock.sendall(json.dumps({"command": list(args)}).encode() + b"\n")
        except OSError:
            pass

    def poll(self):
        try:
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                self.buf += chunk
        except (BlockingIOError, InterruptedError):
            pass
        except OSError:
            return
        *lines, self.buf = self.buf.split(b"\n")
        for line in lines:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("event") == "property-change":
                self.props[msg["name"]] = msg.get("data")
            elif "event" in msg:
                self.events.append(msg)

    def play(self, url):
        self.cmd("loadfile", url, "replace")
        self.cmd("set_property", "pause", False)

    def stop(self):
        self.cmd("stop")

    def quit(self):
        self.cmd("quit")
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        try:
            os.unlink(SOCK)
        except OSError:
            pass


# ---------------------------------------------------------------- UI
C_BG, C_BAR, C_SEL, C_TITLE, C_KEY, C_DIM, C_PLAY, C_ERR, C_TAB = range(1, 10)

SKINS = ["Azul", "PC-XT", "Vermelha", "Preta"]


def skin_colors(skin):
    """(B,W,K,Y,C,G,R,L) — papéis de cor usados por init_colors().
    B=fundo, L=texto normal, K=preto, Y=título, C=info/dim, G=tocando, R=erro, W=tecla."""
    hi = curses.COLORS >= 256
    if skin == "PC-XT":
        # mono CGA fósforo verde: tudo no mesmo verde, fundo preto
        return (16, 46, 16, 46, 28, 46, 46, 46) if hi else (
            curses.COLOR_BLACK, curses.COLOR_GREEN, curses.COLOR_BLACK,
            curses.COLOR_GREEN, curses.COLOR_GREEN, curses.COLOR_GREEN,
            curses.COLOR_GREEN, curses.COLOR_GREEN)
    if skin == "Vermelha":
        # igual à Azul, só o fundo troca de azul pra vermelho
        return (88, 231, 16, 227, 37, 83, 203, 250) if hi else (
            curses.COLOR_RED, curses.COLOR_WHITE, curses.COLOR_BLACK,
            curses.COLOR_YELLOW, curses.COLOR_CYAN, curses.COLOR_GREEN,
            curses.COLOR_RED, curses.COLOR_WHITE)
    if skin == "Preta":
        # mono CGA fósforo branco: tudo em branco/cinza, fundo preto
        return (16, 231, 16, 231, 250, 231, 231, 231) if hi else (
            curses.COLOR_BLACK, curses.COLOR_WHITE, curses.COLOR_BLACK,
            curses.COLOR_WHITE, curses.COLOR_WHITE, curses.COLOR_WHITE,
            curses.COLOR_WHITE, curses.COLOR_WHITE)
    # "Azul" — paleta CGA/DOS de verdade (o "azul" de cada terminal varia muito)
    return (19, 231, 16, 227, 37, 83, 203, 250) if hi else (
        curses.COLOR_BLUE, curses.COLOR_WHITE, curses.COLOR_BLACK,
        curses.COLOR_YELLOW, curses.COLOR_CYAN, curses.COLOR_GREEN,
        curses.COLOR_RED, curses.COLOR_WHITE)


def init_colors(skin="Azul"):
    curses.start_color()
    curses.use_default_colors()
    B, W, K, Y, C, G, R, L = skin_colors(skin)
    curses.init_pair(C_BG, L, B)
    curses.init_pair(C_BAR, K, C)
    curses.init_pair(C_SEL, K, C)
    curses.init_pair(C_TITLE, Y, B)
    curses.init_pair(C_KEY, W, K)
    curses.init_pair(C_DIM, C, B)
    curses.init_pair(C_PLAY, G, B)
    curses.init_pair(C_ERR, R, B)
    curses.init_pair(C_TAB, Y, K)


def put(win, y, x, text, attr=0, width=None):
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    if width is not None:
        text = text[:width].ljust(width)
    text = text[: max(0, w - x - (1 if y == h - 1 else 0))]
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def box(win, y, x, h, w, title, attr):
    put(win, y, x, "╔" + "═" * (w - 2) + "╗", attr)
    for i in range(1, h - 1):
        put(win, y + i, x, "║", attr)
        put(win, y + i, x + w - 1, "║", attr)
    put(win, y + h - 1, x, "╚" + "═" * (w - 2) + "╝", attr)
    if title:
        put(win, y, x + 3, f" {title} ", curses.color_pair(C_TITLE) | curses.A_BOLD)


def vol_bar(v, n=20):
    v = max(0, min(100, int(v or 0)))
    full = round(v / 100 * n)
    return "█" * full + "░" * (n - full) + f" {v:3d}%"


HELP = [
    "↑ ↓  PgUp PgDn  Home End   escolher estação",
    "← →  ou  Tab                trocar categoria",
    "Enter                       tocar",
    "Espaço                      pausar / continuar",
    "S                           parar",
    "+  -                        volume",
    "/                           buscar pelo nome (Esc limpa)",
    "R                           recarregar lista do site",
    "K                           trocar skin (Azul/PC-XT/Vermelha/Preta)",
    "F8                          como adicionar novas rádios",
    "Q  ou  F10                  sair",
    "",
    f"RADIO.EXE v{VERSION} — {BUILD_DATE}",
]

ADD_INFO = [
    "As estações vêm de duas fontes:",
    "",
    "1) Online: o HTML em SITE (constante no topo do radio.py),",
    '   um array  const STATIONS = [...]  com {n, u, t}.',
    "2) Cache local: ~/.cache/radio/stations.json — uma lista",
    "   JSON de objetos, por exemplo:",
    '   {"n": "Nome", "u": "http://stream.url", "t": "Categoria"}',
    "",
    "Edite o stations.json à mão e tecle R pra recarregar.",
    "Atenção: se SITE estiver acessível, ele sobrescreve esse",
    "cache no próximo R. Pra manter sua lista fixa, aponte a",
    "constante SITE pro seu próprio HTML (ou deixe-a inválida).",
]


def main(scr):
    curses.curs_set(0)
    state = load_state()
    skin = state.get("skin") if state.get("skin") in SKINS else "Azul"
    init_colors(skin)
    scr.bkgd(" ", curses.color_pair(C_BG))
    scr.timeout(250)
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    curses.mouseinterval(0)

    stations, source = load_stations()
    mpv = Mpv(state.get("volume", 80))

    tags = ["Todas"] + list(dict.fromkeys(s["t"] for s in stations))
    tag_i = tags.index(state["tag"]) if state.get("tag") in tags else 0
    query, searching = "", False
    sel, top = 0, 0
    playing, status, show_help = None, "Parado", False
    show_addinfo = False

    def visible():
        out = stations if tags[tag_i] == "Todas" else [s for s in stations if s["t"] == tags[tag_i]]
        if query:
            q = fold(query)
            out = [s for s in out if q in fold(s["n"])]
        return out

    if state.get("last"):
        names = [s["n"] for s in visible()]
        if state["last"] in names:
            sel = names.index(state["last"])

    while True:
        mpv.poll()
        for ev in mpv.events:
            if ev.get("event") == "end-file" and ev.get("reason") == "error":
                status = "ERRO: rádio fora do ar"
            elif ev.get("event") == "file-loaded":
                status = "Tocando"
        mpv.events.clear()
        p = mpv.props
        if playing and status in ("Tocando", "Pausado", "Carregando…"):
            if p.get("pause"):
                status = "Pausado"
            elif p.get("paused-for-cache"):
                status = "Carregando…"
            else:
                status = "Tocando"

        lst = visible()
        sel = max(0, min(sel, len(lst) - 1))

        # ---------------- desenho
        scr.erase()
        h, w = scr.getmaxyx()
        if h < 12 or w < 50:
            put(scr, 0, 0, "Tela pequena demais (mín. 50x12)", curses.color_pair(C_ERR))
            scr.refresh()
            if scr.getch() in (ord("q"), ord("Q")):
                break
            continue

        bar = curses.color_pair(C_BAR)
        put(scr, 0, 0, " " * w, bar)
        put(scr, 0, 1, "RADIO.EXE", bar | curses.A_BOLD)
        put(scr, 0, 12, f"│ v{VERSION} │ " + f"{len(stations)} estações ({source})", bar)
        put(scr, 0, w - 7, time.strftime("%H:%M"), bar)

        # abas de categoria / busca
        tab_hits = []
        x = 1
        if searching or query:
            put(scr, 1, 1, "Busca: ", curses.color_pair(C_TITLE) | curses.A_BOLD)
            put(scr, 1, 8, query + ("▌" if searching else ""), curses.color_pair(C_BG) | curses.A_BOLD)
            put(scr, 1, w - 22, f"[{tags[tag_i]}]", curses.color_pair(C_DIM))
        else:
            for i, t in enumerate(tags):
                label = f" {t} "
                if x + len(label) >= w - 1:
                    break
                attr = curses.color_pair(C_TAB) | curses.A_BOLD if i == tag_i else curses.color_pair(C_DIM)
                put(scr, 1, x, label, attr)
                tab_hits.append((i, x, x + len(label)))
                x += len(label) + 1

        # lista
        panel_h = 5
        lh = h - 3 - panel_h
        box(scr, 2, 0, lh, w, f"Estações ({len(lst)})", curses.color_pair(C_BG))
        rows = lh - 2
        if sel < top:
            top = sel
        if sel >= top + rows:
            top = sel - rows + 1
        top = max(0, min(top, max(0, len(lst) - rows)))
        name_w = w - 4 - 16
        for r in range(rows):
            i = top + r
            if i >= len(lst):
                break
            s = lst[i]
            mark = "♪" if playing is s else " "
            line = f"{mark} {s['n'][:name_w].ljust(name_w)} {s['t'][:13]:>13}"
            if i == sel:
                attr = curses.color_pair(C_SEL) | curses.A_BOLD
            elif playing is s:
                attr = curses.color_pair(C_PLAY) | curses.A_BOLD
            else:
                attr = curses.color_pair(C_BG)
            put(scr, 3 + r, 1, " " + line, attr, width=w - 2)
        scroll_hit = None
        if len(lst) > rows:
            pos = int((top / max(1, len(lst) - rows)) * (rows - 1))
            for r in range(rows):
                put(scr, 3 + r, w - 1, "█" if r == pos else "░", curses.color_pair(C_DIM))
            scroll_hit = (w - 1, 3, 3 + rows - 1)
        if not lst:
            put(scr, 4, 3, "Nenhuma estação encontrada.", curses.color_pair(C_DIM))
        row_hit = (3, 3 + rows - 1, 1, w - 2)

        # painel "tocando"
        py = 2 + lh
        box(scr, py, 0, panel_h, w, "Tocando", curses.color_pair(C_BG))
        st_attr = (curses.color_pair(C_ERR) if status.startswith("ERRO") else
                   curses.color_pair(C_PLAY) if status == "Tocando" else
                   curses.color_pair(C_TITLE)) | curses.A_BOLD
        put(scr, py + 1, 2, "Rádio : ", curses.color_pair(C_DIM))
        put(scr, py + 1, 10, playing["n"] if playing else "—", curses.color_pair(C_BG) | curses.A_BOLD, width=w - 30)
        put(scr, py + 1, w - 20, f"[{status}]"[:19].rjust(19), st_attr)
        track = p.get("media-title") or ""
        if playing and track and track not in (playing["u"], os.path.basename(playing["u"].split("?")[0])):
            put(scr, py + 2, 2, "Música: ", curses.color_pair(C_DIM))
            put(scr, py + 2, 10, track, curses.color_pair(C_TITLE), width=w - 12)
        put(scr, py + 3, 2, "Volume: ", curses.color_pair(C_DIM))
        put(scr, py + 3, 10, vol_bar(p.get("volume", state.get("volume", 80))), curses.color_pair(C_BG))
        vol_hit = (py + 3, 10, 30)

        # barra de teclas estilo DOS
        fkey_hits = []
        keys = [("F1", "Ajuda"), ("Enter", "Tocar"), ("Espaço", "Pausa"), ("S", "Parar"),
                ("+/-", "Volume"), ("/", "Busca"), ("←→", "Categ."), ("K", "Skin"), ("F10", "Sair")]
        x = 0
        put(scr, h - 1, 0, " " * w, bar)
        for k, label in keys:
            if x + len(k) + len(label) + 2 > w:
                break
            put(scr, h - 1, x, k, curses.color_pair(C_KEY) | curses.A_BOLD)
            put(scr, h - 1, x + len(k), label + " ", bar)
            if k == "+/-":
                mid = x + 1
                fkey_hits.append((x, mid, "vol+"))
                fkey_hits.append((mid, x + len(k), "vol-"))
            elif k == "←→":
                mid = x + len(k) // 2
                fkey_hits.append((x, mid, "cat_prev"))
                fkey_hits.append((mid, x + len(k), "cat_next"))
            else:
                fkey_hits.append((x, x + len(k) + len(label) + 1,
                                   {"F1": "help", "Enter": "play", "Espaço": "pause",
                                    "S": "stop", "/": "search", "K": "skin",
                                    "F10": "quit"}[k]))
            x += len(k) + len(label) + 2

        if show_help:
            hw, hh = 52, len(HELP) + 4
            hy, hx = max(0, (h - hh) // 2), max(0, (w - hw) // 2)
            for r in range(hh):
                put(scr, hy + r, hx, " " * hw, bar)
            box(scr, hy, hx, hh, hw, "Ajuda", bar)
            for r, line in enumerate(HELP):
                put(scr, hy + 2 + r, hx + 2, line, bar)
            put(scr, hy + hh - 1, hx + hw - 22, " qualquer tecla ", bar | curses.A_BOLD)

        if show_addinfo:
            hw2, hh2 = 64, len(ADD_INFO) + 4
            hy2, hx2 = max(0, (h - hh2) // 2), max(0, (w - hw2) // 2)
            for r in range(hh2):
                put(scr, hy2 + r, hx2, " " * hw2, bar)
            box(scr, hy2, hx2, hh2, hw2, "Como adicionar rádios", bar)
            for r, line in enumerate(ADD_INFO):
                put(scr, hy2 + 2 + r, hx2 + 2, line, bar, width=hw2 - 4)
            put(scr, hy2 + hh2 - 1, hx2 + hw2 - 22, " qualquer tecla ", bar | curses.A_BOLD)

        scr.refresh()

        # ---------------- teclado
        try:
            k = scr.get_wch()
        except curses.error:
            continue

        mbstate = mcx = mcy = None
        if k == curses.KEY_MOUSE:
            try:
                _, mcx, mcy, _, mbstate = curses.getmouse()
            except curses.error:
                continue
        # um clique "solta" dois eventos (pressionar e soltar); só o de
        # pressionar deve fechar os quadros de ajuda, senão o próprio
        # clique que os abre já os fecharia de novo no evento de soltar.
        mouse_press = mbstate is not None and bool(
            mbstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED))
        if show_help:
            if mbstate is None or mouse_press:
                show_help = False
            continue
        if show_addinfo:
            if mbstate is None or mouse_press:
                show_addinfo = False
            continue

        if mbstate is not None and not searching:
            bstate = mbstate
            if bstate & curses.BUTTON4_PRESSED:
                sel -= 1
                continue
            if bstate & getattr(curses, "BUTTON5_PRESSED", 0):
                sel += 1
                continue
            if not bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                continue
            if tab_hits and mcy == 1:
                for i, x0, x1 in tab_hits:
                    if x0 <= mcx < x1:
                        tag_i, sel, top = i, 0, 0
                        break
                continue
            if row_hit[0] <= mcy <= row_hit[1] and row_hit[2] <= mcx <= row_hit[3]:
                i = top + (mcy - row_hit[0])
                if i < len(lst):
                    sel = i
                    playing = lst[i]
                    status = "Conectando…"
                    mpv.props.pop("media-title", None)
                    mpv.play(playing["u"])
                    state.update(last=playing["n"], tag=tags[tag_i])
                    save_state(state)
                continue
            if scroll_hit and mcx == scroll_hit[0] and scroll_hit[1] <= mcy <= scroll_hit[2]:
                span = max(1, scroll_hit[2] - scroll_hit[1])
                frac = (mcy - scroll_hit[1]) / span
                top = int(frac * max(0, len(lst) - rows))
                sel = top
                continue
            if vol_hit[1] <= mcx <= vol_hit[2] and mcy == vol_hit[0]:
                span = max(1, vol_hit[2] - vol_hit[1])
                frac = max(0.0, min(1.0, (mcx - vol_hit[1]) / span))
                mpv.cmd("set_property", "volume", round(frac * 100))
                continue
            if mcy == h - 1 and fkey_hits:
                want_quit = False
                for fx0, fx1, action in fkey_hits:
                    if fx0 <= mcx < fx1:
                        if action == "help":
                            show_help = True
                        elif action == "play" and lst:
                            playing = lst[sel]
                            status = "Conectando…"
                            mpv.props.pop("media-title", None)
                            mpv.play(playing["u"])
                            state.update(last=playing["n"], tag=tags[tag_i])
                            save_state(state)
                        elif action == "pause" and playing:
                            mpv.cmd("cycle", "pause")
                        elif action == "stop":
                            mpv.stop()
                            playing, status = None, "Parado"
                        elif action == "vol+":
                            mpv.cmd("add", "volume", 5)
                        elif action == "vol-":
                            mpv.cmd("add", "volume", -5)
                        elif action == "search":
                            searching = True
                        elif action == "cat_prev":
                            tag_i, sel, top = (tag_i - 1) % len(tags), 0, 0
                        elif action == "cat_next":
                            tag_i, sel, top = (tag_i + 1) % len(tags), 0, 0
                        elif action == "skin":
                            skin = SKINS[(SKINS.index(skin) + 1) % len(SKINS)]
                            init_colors(skin)
                            state["skin"] = skin
                            save_state(state)
                            status = f"Skin: {skin}"
                        elif action == "quit":
                            want_quit = True
                        break
                if want_quit:
                    break
            continue

        if searching:
            if k in ("\n", "\r", curses.KEY_ENTER):
                searching = False
            elif k == "\x1b":
                searching, query = False, ""
            elif k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                query = query[:-1]
            elif isinstance(k, str) and k.isprintable():
                query += k
                sel = top = 0
            elif k in (curses.KEY_UP, curses.KEY_DOWN):
                searching = False
            else:
                continue
            if searching:
                continue

        if k in ("q", "Q", curses.KEY_F10):
            break
        elif k == curses.KEY_F1 or k in ("h", "H", "?"):
            show_help = True
        elif k == curses.KEY_F8:
            show_addinfo = True
        elif k == curses.KEY_UP:
            sel -= 1
        elif k == curses.KEY_DOWN:
            sel += 1
        elif k == curses.KEY_PPAGE:
            sel -= rows
        elif k == curses.KEY_NPAGE:
            sel += rows
        elif k == curses.KEY_HOME:
            sel = 0
        elif k == curses.KEY_END:
            sel = len(lst) - 1
        elif k in (curses.KEY_RIGHT, "\t"):
            tag_i, sel, top = (tag_i + 1) % len(tags), 0, 0
        elif k in (curses.KEY_LEFT, curses.KEY_BTAB):
            tag_i, sel, top = (tag_i - 1) % len(tags), 0, 0
        elif k == "/":
            searching = True
        elif k == "\x1b" and query:
            query = ""
        elif k in ("\n", "\r", curses.KEY_ENTER) and lst:
            playing = lst[sel]
            status = "Conectando…"
            mpv.props.pop("media-title", None)
            mpv.play(playing["u"])
            state.update(last=playing["n"], tag=tags[tag_i])
            save_state(state)
        elif k == " " and playing:
            mpv.cmd("cycle", "pause")
        elif k in ("s", "S"):
            mpv.stop()
            playing, status = None, "Parado"
        elif k in ("+", "="):
            mpv.cmd("add", "volume", 5)
        elif k in ("-", "_"):
            mpv.cmd("add", "volume", -5)
        elif k in ("r", "R"):
            stations, source = load_stations()
            tags = ["Todas"] + list(dict.fromkeys(s["t"] for s in stations))
            tag_i = min(tag_i, len(tags) - 1)
        elif k in ("k", "K"):
            skin = SKINS[(SKINS.index(skin) + 1) % len(SKINS)]
            init_colors(skin)
            state["skin"] = skin
            save_state(state)
            status = f"Skin: {skin}"

    if mpv.props.get("volume") is not None:
        state["volume"] = int(mpv.props["volume"])
    save_state(state)
    mpv.quit()


if __name__ == "__main__":
    os.environ.setdefault("ESCDELAY", "25")
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    except RuntimeError as e:
        print(f"radio: {e}", file=sys.stderr)
        sys.exit(1)
