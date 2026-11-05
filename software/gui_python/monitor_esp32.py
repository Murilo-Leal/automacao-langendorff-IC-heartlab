#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESP32 Hub — Monitor e Controle  (v2)
====================================
Supervisório para o firmware "ESP_Central_Compativel_14_Dinamico".

Recebe pela serial (115200 baud) — o ESP imprime tudo que chega pelo rádio:
    NODE 2: SN2 <fluxo*100> <tempFluxo*100> <pressao*100> <tempMax*100>
    NODE 4: SN4 <fluxo*100> <tempFluxo*100> <pressao*100> <tempMax*100>
    + mensagens de alerta, PID, relés e falhas de rádio

Envia (terminados em '\n'):
    SET_FLUXO:<valor>   PID_ON   PID_OFF
    LIGAR_RELE_1  DESLIGAR_RELE_1  LIGAR_RELE_2  DESLIGAR_RELE_2
    SERVO1:<ang>  SERVO2:<ang>  SERVO3:<ang>  SERVO4:<ang>   (para o NODE 3)
    qualquer outro texto -> encaminhado ao NODE 3

Dependências:  pip install pyserial matplotlib
Uso:           python monitor_esp32.py
               (escolha "SIMULADOR" na lista de portas para testar sem hardware)
"""

import csv
import math
import queue
import random
import re
import threading
import time
from collections import deque
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

import numpy as np
import serial
import serial.tools.list_ports
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================
APP_TITLE = "ESP32 Hub — Monitor e Controle"
BAUD_PADRAO = 115200
SIM_PORT = "SIMULADOR"

# Nós com sensores (fluxo, temp. fluxo, pressão, temp. tanque)
NODES_SENSOR = (2, 4)

# Limites (iguais ao firmware). O firmware só avalia o NODE 2;
# o NODE 4 é avaliado aqui no PC com os mesmos limites.
TEMP_FLUXO_MIN, TEMP_FLUXO_MAX = 37.0, 41.0
TEMP_MAX_MIN, TEMP_MAX_MAX = 22.0, 41.0
PRESSAO_MAX = 80.0
MARGEM_FLUXO = 5.0
SETPOINT_PADRAO = 40.0
SETPOINT_LIM = (5.0, 100.0)      # firmware aceita 5 < sp < 100
LINK_TIMEOUT = 2.0               # mesmo critério do firmware (2000 ms)
MAX_PONTOS = 20000

# Servos do NODE 3: nome e faixa de ângulo (0 % = ângulo mínimo, 100 % = máximo).
# >>> Ajuste a faixa conforme a mecânica de cada válvula/servo. <<<
SERVOS = {
    1: {"nome": "Servo 1 (Fluxo/PID)", "faixa": (0, 90)},
    2: {"nome": "Servo 2 (Oxigenação)", "faixa": (0, 90)},
    3: {"nome": "Servo 3 (Oxigenação)", "faixa": (0, 90)},
    4: {"nome": "Servo 4 (Oxigenação)", "faixa": (0, 90)},
}
SERVOS_OXI = (2, 3, 4)
SERVO1_PADRAO = 45               # posição inicial do PID no firmware

COR_OK = "#2e7d32"
COR_ALERTA = "#c62828"
COR_NEUTRO = "#607d8b"
COR_AVISO = "#f9a825"
COR_INFO = "#455a64"
COR_NODE = {2: "#1565c0", 4: "#ef6c00"}
COR_SERVO = {1: "#757575", 2: "#2e7d32", 3: "#00838f", 4: "#6a1b9a"}
VARS = ("fluxo", "temp_fluxo", "pressao", "temp_max")


def ang_para_pct(n, ang):
    a0, a1 = SERVOS[n]["faixa"]
    return max(0.0, min(100.0, (ang - a0) * 100.0 / (a1 - a0)))


def pct_para_ang(n, pct):
    a0, a1 = SERVOS[n]["faixa"]
    return int(round(a0 + (a1 - a0) * max(0.0, min(100.0, pct)) / 100.0))


# =============================================================================
# PARSER DAS MENSAGENS DO ESP32
# =============================================================================
class ParserESP:
    # "NODE 2: SN2 ..." / "NODE 4: SN4 ..." — o nó vem do prefixo (pipe de rádio)
    RE_SN = re.compile(r"(?:NODE\s+(\d+)\s*:\s*)?SN(\d)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)")
    RE_SERVO_PID = re.compile(r"Ajustando Servo:\s*(-?\d+)\s*->\s*(-?\d+)")
    RE_SETPOINT = re.compile(r"NOVO SETPOINT DE FLUXO DEFINIDO:\s*(-?\d+(?:\.\d+)?)")
    # Relé 2 imprime "DESLIGAR_RELE_2 enviado"; Relé 1 imprime "DESLIGAR_RELE enviado"
    RE_RELE_AUTO = re.compile(r"Comando (LIGAR|DESLIGAR)_RELE(_2)? enviado")
    RE_FALHA = re.compile(r"Falha ao contatar NODE\s*(\d+)")
    RE_MANUAL = re.compile(r"COMANDO MANUAL RECEBIDO:\s*(.+)")
    RE_SERVO_CMD = re.compile(r"SERVO(\d)\s*:\s*(-?\d+)")

    def __init__(self):
        self._manual_pendente = None

    @classmethod
    def efeito_comando(cls, cmd):
        """Efeito esperado de um comando manual aceito pelo NODE 3."""
        cmd = cmd.strip().upper()
        mapa = {
            "LIGAR_RELE_1": ("rele", 1, True), "DESLIGAR_RELE_1": ("rele", 1, False),
            "LIGAR_RELE_2": ("rele", 2, True), "DESLIGAR_RELE_2": ("rele", 2, False),
        }
        if cmd in mapa:
            return [mapa[cmd]]
        m = cls.RE_SERVO_CMD.match(cmd)
        if m and int(m.group(1)) in SERVOS:
            return [("servo", int(m.group(1)), int(m.group(2)))]
        return []

    def parse(self, linha):
        ev = []
        m = self.RE_SN.search(linha)
        if m:
            node = int(m.group(1) or m.group(2))
            f, tf, p, tm = (int(x) / 100.0 for x in m.groups()[2:])
            ev.append(("sensor", node, {"fluxo": f, "temp_fluxo": tf, "pressao": p, "temp_max": tm}))
            return ev

        if "Sistema Pronto" in linha:
            ev.append(("boot",))
        if "Controle PID ATIVADO" in linha:
            ev.append(("pid", True))
        if "PID DESATIVADO" in linha:
            ev.append(("pid", False))

        m = self.RE_SERVO_PID.search(linha)
        if m:
            ev.append(("servo", 1, int(m.group(2))))
        m = self.RE_SETPOINT.search(linha)
        if m:
            ev.append(("setpoint", float(m.group(1))))
        m = self.RE_RELE_AUTO.search(linha)
        if m:
            ev.append(("rele", 2 if m.group(2) else 1, m.group(1) == "LIGAR"))
        m = self.RE_FALHA.search(linha)
        if m:
            ev.append(("falha", int(m.group(1))))

        m = self.RE_MANUAL.search(linha)
        if m:
            self._manual_pendente = m.group(1).strip()
        if "Comando manual enviado com sucesso" in linha and self._manual_pendente:
            ev += self.efeito_comando(self._manual_pendente)
            self._manual_pendente = None
        if "Falha ao enviar comando manual" in linha:
            self._manual_pendente = None
        return ev


# =============================================================================
# COMUNICAÇÃO SERIAL (thread)
# =============================================================================
class SerialWorker(threading.Thread):
    def __init__(self, porta, baud, fila):
        super().__init__(daemon=True)
        self.porta, self.baud, self.fila = porta, baud, fila
        self.stop_evt = threading.Event()
        self.lock = threading.Lock()
        self.ser = None

    def run(self):
        try:
            self.ser = serial.Serial()
            self.ser.port = self.porta
            self.ser.baudrate = self.baud
            self.ser.timeout = 0.1
            # DTR/RTS em False evita que o ESP32 reinicie ao abrir a porta
            self.ser.dtr = False
            self.ser.rts = False
            self.ser.open()
        except Exception as e:
            self.fila.put(("erro", f"Não foi possível abrir {self.porta}: {e}"))
            self.fila.put(("desconectado", None))
            return

        self.fila.put(("conectado", self.porta))
        buf = b""
        while not self.stop_evt.is_set():
            try:
                dados = self.ser.read(self.ser.in_waiting or 1)
            except Exception as e:
                self.fila.put(("erro", f"Erro de leitura: {e}"))
                break
            if dados:
                buf += dados
                while b"\n" in buf:
                    linha, buf = buf.split(b"\n", 1)
                    texto = linha.decode("utf-8", errors="replace").strip("\r")
                    self.fila.put(("linha", texto))
        try:
            self.ser.close()
        except Exception:
            pass
        self.fila.put(("desconectado", None))

    def send(self, texto):
        with self.lock:
            self.ser.write((texto + "\n").encode("utf-8"))

    def reset_esp(self):
        """Pulso em RTS (EN) reinicia o ESP32 sem entrar em modo boot."""
        with self.lock:
            self.ser.dtr = False
            self.ser.rts = True
            time.sleep(0.12)
            self.ser.rts = False

    def stop(self):
        self.stop_evt.set()


# =============================================================================
# SIMULADOR (imita o firmware para testar sem hardware)
# =============================================================================
class SimuladorESP(threading.Thread):
    def __init__(self, fila):
        super().__init__(daemon=True)
        self.fila = fila
        self.stop_evt = threading.Event()
        self.cmds = queue.Queue()
        self._reset_estado()

    def _reset_estado(self):
        self.setpoint, self.pid, self.servo = SETPOINT_PADRAO, True, SERVO1_PADRAO
        self.servo_fisico = SERVO1_PADRAO
        self.oxi = {2: 0, 3: 0, 4: 0}
        self.r1 = self.r2 = True
        self.alerta = False
        self.fluxo, self.tf, self.tm, self.p = 30.0, 38.5, 30.0, 40.0
        self.n4 = {"fluxo": 36.0, "tf": 38.8, "tm": 29.0}
        self.erro_acum = 0.0
        self.ultimo_erro = 0.0
        self.t_pid = time.time()

    def _out(self, s):
        self.fila.put(("linha", s))

    def _boot(self):
        for s in ("Bluetooth ON.", "SistemaAlarme: Hardware configurado via CPP.",
                  "Radio NRF24L01 Iniciado.", "Sistema Pronto.",
                  "Digite comandos: LIGAR_RELE_1_2, DESLIGAR_RELE_1_2, SERVO_DIR..."):
            self._out(s)

    def send(self, texto):
        self.cmds.put(texto.strip())

    def reset_esp(self):
        self.cmds.put("__RESET__")

    def stop(self):
        self.stop_evt.set()

    def run(self):
        self.fila.put(("conectado", SIM_PORT))
        self._boot()
        prox = time.time()
        while not self.stop_evt.is_set():
            try:
                self._comando(self.cmds.get(timeout=0.05))
            except queue.Empty:
                pass
            if time.time() >= prox:
                prox += 0.5
                self._passo()
        self.fila.put(("desconectado", None))

    def _comando(self, c):
        if c == "__RESET__":
            self._reset_estado()
            self._boot()
            return
        if not c:
            return
        if c.startswith("SET_FLUXO:"):
            try:
                v = float(c[10:])
            except ValueError:
                v = 0.0
            if 5.0 < v < 100.0:
                self.setpoint = v
                self._out("=========================================")
                self._out(f"-> NOVO SETPOINT DE FLUXO DEFINIDO: {v:.2f}")
                self._out(f"-> LIMITES DO ALARME ATUALIZADOS: {v - MARGEM_FLUXO:.2f} a {v + MARGEM_FLUXO:.2f}")
                self._out("=========================================")
            else:
                self._out("-> ERRO: Valor de setpoint invalido. Use algo entre 5.0 e 100.0")
            return
        if c == "PID_ON":
            self.pid = True
            self._out("-> Controle PID ATIVADO.")
            return
        if c == "PID_OFF":
            self.pid = False
            self._out("-> Controle PID DESATIVADO (Modo Manual).")
            return
        self._out("COMANDO MANUAL RECEBIDO: " + c)
        if random.random() < 0.03:                      # simula falha de rádio ocasional
            self._out("!!! Falha ao contatar NODE 3")
            self._out("-> Falha ao enviar comando manual.")
            return
        self._out("-> Comando manual enviado com sucesso!")
        if c == "LIGAR_RELE_1": self.r1 = True
        if c == "DESLIGAR_RELE_1": self.r1 = False
        if c == "LIGAR_RELE_2": self.r2 = True
        if c == "DESLIGAR_RELE_2": self.r2 = False
        m = re.match(r"SERVO(\d):(\d+)", c)
        if m:
            n, ang = int(m.group(1)), int(m.group(2))
            if n == 1:
                self.servo_fisico = ang
            elif n in self.oxi:
                self.oxi[n] = ang

    def _pid(self, fluxo):
        agora = time.time()
        dt = agora - self.t_pid
        if dt <= 0 or dt > 1.0:
            dt = 0.1
        erro = self.setpoint - fluxo
        if abs(erro) < 2.0:
            self.erro_acum *= 0.95
            self.t_pid = agora
            return self.servo
        P = 0.1 * erro
        self.erro_acum = max(-20, min(20, self.erro_acum + erro * dt))
        I = 0.05 * self.erro_acum
        D = 0.01 * (erro - self.ultimo_erro) / dt
        self.ultimo_erro, self.t_pid = erro, agora
        return max(0, min(90, self.servo + int(P + I + D)))

    def _passo(self):
        # --- NODE 2 ---
        self.fluxo += 0.25 * (self.servo_fisico * 0.9 - self.fluxo) + random.gauss(0, 0.4)
        self.tf += (0.18 if self.r2 else -0.12) + random.gauss(0, 0.03)
        self.tm += (0.06 if self.r1 else -0.05) + random.gauss(0, 0.02)
        self.p = 15 + self.fluxo * 0.9 + 3 * math.sin(time.time() / 7) + random.gauss(0, 0.5)
        self._out(f"NODE 2: SN2 {int(self.fluxo * 100)} {int(self.tf * 100)} "
                  f"{int(self.p * 100)} {int(self.tm * 100)}")

        # --- NODE 4 (oxigenação aumenta um pouco o fluxo/pressão) ---
        oxi_med = sum(self.oxi.values()) / 3.0
        n4 = self.n4
        n4["fluxo"] += 0.2 * (34 + oxi_med * 0.12 - n4["fluxo"]) + random.gauss(0, 0.35)
        n4["tf"] += 0.1 * (39.0 - n4["tf"]) + random.gauss(0, 0.05)
        n4["tm"] += 0.02 * (31.0 - n4["tm"]) + random.gauss(0, 0.03)
        p4 = 12 + n4["fluxo"] * 0.85 + random.gauss(0, 0.5)
        self._out(f"NODE 4: SN4 {int(n4['fluxo'] * 100)} {int(n4['tf'] * 100)} "
                  f"{int(p4 * 100)} {int(n4['tm'] * 100)}")

        # --- lógica do firmware (só NODE 2) ---
        mn, mx = self.setpoint - MARGEM_FLUXO, self.setpoint + MARGEM_FLUXO
        fora = (not 37 <= self.tf <= 41) or (not 22 <= self.tm <= 41) or \
               (not mn <= self.fluxo <= mx) or self.p > 80
        if fora and not self.alerta:
            self._out("")
            self._out("!!! ALERTA DE SEGURANÇA ATIVADO !!!")
            if not 37 <= self.tf <= 41: self._out(f"- Temp Fluxo fora: {self.tf:.2f} C")
            if not 22 <= self.tm <= 41: self._out(f"- Temp Tanque fora: {self.tm:.2f} C")
            if not mn <= self.fluxo <= mx:
                self._out(f"- Fluxo fora da margem: {self.fluxo:.2f} (Aceitavel: {mn:.2f} a {mx:.2f})")
            if self.p > 80: self._out(f"- Pressão crítica: {self.p:.2f}")
        elif not fora and self.alerta:
            self._out("")
            self._out("-> Sistema normalizado. Alarme desligado.")
        self.alerta = fora

        if self.pid:
            nova = self._pid(self.fluxo)
            if nova != self.servo:
                self._out(f"Ajustando Servo: {self.servo} -> {nova} "
                          f"(Fluxo Atual: {self.fluxo:.2f} | Alvo: {self.setpoint:.2f})")
                self.servo = nova
                self.servo_fisico = nova

        if self.tf > 41.3 and self.r2:
            self.r2 = False
            self._out(f"Alerta: Temp Fluxo {self.tf:.2f}C > 40C. Comando DESLIGAR_RELE_2 enviado.")
        elif self.tf <= 39.3 and not self.r2:
            self.r2 = True
            self._out(f"Estabilizado: Temp Fluxo {self.tf:.2f}C. Comando LIGAR_RELE_2 enviado.")
        if self.tm > 40.0 and self.r1:
            self.r1 = False
            self._out(f"Alerta: Temp Max {self.tm:.2f}C > 40C. Comando DESLIGAR_RELE enviado.")
        elif self.tm <= 40.0 and not self.r1:
            self.r1 = True
            self._out(f"Estabilizado: Temp Max {self.tm:.2f}C. Comando LIGAR_RELE enviado.")


# =============================================================================
# INTERFACE GRÁFICA
# =============================================================================
class Card(tk.Frame):
    """Indicador compacto de uma grandeza."""
    def __init__(self, master, titulo, unidade, faixa_txt):
        super().__init__(master, bg=COR_NEUTRO, padx=8, pady=3)
        self.unidade = unidade
        self.l_tit = tk.Label(self, text=titulo, bg=COR_NEUTRO, fg="white",
                              font=("Segoe UI", 9, "bold"))
        self.l_val = tk.Label(self, text="--", bg=COR_NEUTRO, fg="white",
                              font=("Segoe UI", 17, "bold"))
        self.l_fx = tk.Label(self, text=faixa_txt, bg=COR_NEUTRO, fg="#eceff1",
                             font=("Segoe UI", 7))
        for w in (self.l_tit, self.l_val, self.l_fx):
            w.pack(anchor="w")

    def _cor(self, cor):
        for w in (self, self.l_tit, self.l_val, self.l_fx):
            w.config(bg=cor)

    def set(self, valor, ok):
        self.l_val.config(text="--" if valor is None else f"{valor:.2f} {self.unidade}")
        self._cor(COR_NEUTRO if valor is None else (COR_OK if ok else COR_ALERTA))

    def neutro(self):
        self._cor(COR_NEUTRO)


def badge(master, width=14):
    return tk.Label(master, text="?", bg=COR_NEUTRO, fg="white", width=width,
                    font=("Segoe UI", 9, "bold"))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1420x900")
        self.minsize(1150, 760)

        self.fila = queue.Queue()
        self.worker = None
        self.parser = ParserESP()
        self.estado = {
            "pid": None, "rele1": None, "rele2": None,
            "servos": {n: None for n in SERVOS},           # ângulo conhecido de cada servo
            "setpoint": SETPOINT_PADRAO,
            "alerta": {n: False for n in NODES_SENSOR},
            "ultimo": {n: 0.0 for n in NODES_SENSOR},
            "falhas": 0, "amostras": 0,
        }
        self.series = {n: {k: deque(maxlen=MAX_PONTOS) for k in ("t",) + VARS}
                       for n in NODES_SENSOR}
        self.serie_servos = {k: deque(maxlen=MAX_PONTOS) for k in ["t"] + list(SERVOS)}
        self.csv_arq = None
        self.csv_w = None
        self.hist_cmd, self.hist_idx = [], 0

        self._estilo()
        self._montar_ui()
        self.atualizar_portas()
        self._atualizar_status()
        self.protocol("WM_DELETE_WINDOW", self.ao_fechar)
        self.after(50, self._processar_fila)
        self.after(500, self._tick)

    # ------------------------------------------------------------------ UI
    def _estilo(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        st.configure("Verde.TButton", foreground="white", background=COR_OK)
        st.map("Verde.TButton", background=[("active", "#1b5e20")])
        st.configure("Vermelho.TButton", foreground="white", background=COR_ALERTA)
        st.map("Vermelho.TButton", background=[("active", "#8e0000")])
        for n, cor in COR_SERVO.items():
            st.configure(f"S{n}.Horizontal.TProgressbar", background=cor, troughcolor="#e0e0e0")

    def _montar_ui(self):
        # --- Barra superior: conexão ---
        top = ttk.Frame(self, padding=(8, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Porta:").pack(side="left")
        self.cb_porta = ttk.Combobox(top, width=28, state="readonly")
        self.cb_porta.pack(side="left", padx=4)
        ttk.Button(top, text="↻", width=3, command=self.atualizar_portas).pack(side="left")
        ttk.Label(top, text="Baud:").pack(side="left", padx=(10, 0))
        self.cb_baud = ttk.Combobox(top, width=8, state="readonly",
                                    values=["9600", "57600", "115200", "230400", "921600"])
        self.cb_baud.set(str(BAUD_PADRAO))
        self.cb_baud.pack(side="left", padx=4)
        self.bt_con = ttk.Button(top, text="Conectar", command=self.alternar_conexao)
        self.bt_con.pack(side="left", padx=6)
        self.bt_reset = ttk.Button(top, text="Reiniciar ESP", command=self.reset_esp,
                                   state="disabled")
        self.bt_reset.pack(side="left")
        self.l_con = tk.Label(top, text="  Desconectado  ", bg=COR_NEUTRO, fg="white",
                              font=("Segoe UI", 9, "bold"))
        self.l_con.pack(side="left", padx=10)
        self.bt_csv = ttk.Button(top, text="● Gravar CSV", command=self.alternar_csv)
        self.bt_csv.pack(side="right")

        corpo = ttk.PanedWindow(self, orient="horizontal")
        corpo.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        esq = ttk.Frame(corpo)
        dir_ = ttk.PanedWindow(corpo, orient="vertical")
        corpo.add(esq, weight=0)
        corpo.add(dir_, weight=1)

        self._montar_leituras(esq)
        self._montar_status(esq)
        self._montar_controle(esq)
        self._montar_graficos(dir_)
        self._montar_log(dir_)
        self._atualizar_faixa_fluxo()

    def _montar_leituras(self, master):
        fr = ttk.LabelFrame(master, text="Leituras", padding=6)
        fr.pack(fill="x", pady=(0, 6))
        self.cards, self.b_link = {}, {}
        titulos = {"fluxo": ("Fluxo", ""), "temp_fluxo": ("Temp. Fluxo", "°C"),
                   "pressao": ("Pressão", ""), "temp_max": ("Temp. Tanque", "°C")}
        faixas = {"fluxo": "",
                  "temp_fluxo": f"faixa {TEMP_FLUXO_MIN:.0f} – {TEMP_FLUXO_MAX:.0f} °C",
                  "pressao": f"máx. {PRESSAO_MAX:.0f}",
                  "temp_max": f"faixa {TEMP_MAX_MIN:.0f} – {TEMP_MAX_MAX:.0f} °C"}
        for c, node in enumerate(NODES_SENSOR):
            cab = tk.Frame(fr, bg=COR_NODE[node])
            cab.grid(row=0, column=c, sticky="ew", padx=3, pady=(0, 3))
            tk.Label(cab, text=f"NODE {node}", bg=COR_NODE[node], fg="white",
                     font=("Segoe UI", 10, "bold")).pack(side="left", padx=6)
            self.b_link[node] = badge(cab, width=10)
            self.b_link[node].pack(side="right", padx=3, pady=2)
            for r, k in enumerate(VARS, start=1):
                card = Card(fr, *titulos[k], faixas[k])
                card.grid(row=r, column=c, sticky="nsew", padx=3, pady=2)
                self.cards[(node, k)] = card
        fr.columnconfigure(0, weight=1, uniform="n")
        fr.columnconfigure(1, weight=1, uniform="n")

    def _montar_status(self, master):
        fr = ttk.LabelFrame(master, text="Alarmes", padding=6)
        fr.pack(fill="x", pady=(0, 6))
        self.b_alerta = {}
        for i, node in enumerate(NODES_SENSOR):
            ttk.Label(fr, text=f"NODE {node}").grid(row=0, column=2 * i, sticky="w", padx=(0, 4))
            self.b_alerta[node] = badge(fr, width=10)
            self.b_alerta[node].grid(row=0, column=2 * i + 1, sticky="w", padx=(0, 12))
        ttk.Label(fr, text="Falhas NODE 3").grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.b_falhas = badge(fr, width=10)
        self.b_falhas.grid(row=1, column=3, sticky="w", pady=(4, 0))

    def _montar_controle(self, master):
        nb = ttk.Notebook(master)
        nb.pack(fill="both", expand=True)
        self.servo_ui = {}

        # ---------- Aba Processo ----------
        tab = ttk.Frame(nb, padding=8)
        nb.add(tab, text="  Processo  ")
        tab.columnconfigure(1, weight=1)

        ttk.Label(tab, text="Setpoint fluxo").grid(row=0, column=0, sticky="w", pady=3)
        f = ttk.Frame(tab); f.grid(row=0, column=1, sticky="w")
        self.e_sp = ttk.Entry(f, width=7)
        self.e_sp.insert(0, f"{SETPOINT_PADRAO:.1f}")
        self.e_sp.pack(side="left")
        self.e_sp.bind("<Return>", lambda e: self.enviar_setpoint())
        ttk.Button(f, text="Aplicar", width=8, command=self.enviar_setpoint).pack(side="left", padx=4)
        self.b_sp = badge(tab, width=11)
        self.b_sp.grid(row=0, column=2, sticky="e")

        def linha_onoff(row, nome, cmd_on, cmd_off):
            ttk.Label(tab, text=nome).grid(row=row, column=0, sticky="w", pady=3)
            f = ttk.Frame(tab); f.grid(row=row, column=1, sticky="w")
            ttk.Button(f, text="Ligar", width=8, style="Verde.TButton",
                       command=lambda: self.enviar(cmd_on)).pack(side="left")
            ttk.Button(f, text="Desligar", width=8, style="Vermelho.TButton",
                       command=lambda: self.enviar(cmd_off)).pack(side="left", padx=4)
            b = badge(tab, width=11)
            b.grid(row=row, column=2, sticky="e")
            return b

        self.b_pid = linha_onoff(1, "Controle PID", "PID_ON", "PID_OFF")
        self.b_rele = {1: linha_onoff(2, "Relé 1 (Tanque)", "LIGAR_RELE_1", "DESLIGAR_RELE_1"),
                       2: linha_onoff(3, "Relé 2 (Fluxo)", "LIGAR_RELE_2", "DESLIGAR_RELE_2")}

        fs = ttk.Frame(tab)
        fs.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self._linha_servo(fs, 1)
        self.l_aviso_servo = ttk.Label(tab, text="", foreground=COR_ALERTA, font=("Segoe UI", 8))
        self.l_aviso_servo.grid(row=5, column=0, columnspan=3, sticky="w")

        # ---------- Aba Oxigenação ----------
        tab = ttk.Frame(nb, padding=8)
        nb.add(tab, text="  Oxigenação (Servos 2–4)  ")
        for n in SERVOS_OXI:
            self._linha_servo(tab, n)
        f = ttk.Frame(tab); f.pack(fill="x", pady=(8, 0))
        ttk.Label(f, text="Todos:").pack(side="left")
        ttk.Button(f, text="Fechar (0%)", command=lambda: self.enviar_oxi_todos(0)).pack(side="left", padx=3)
        ttk.Button(f, text="50%", width=5, command=lambda: self.enviar_oxi_todos(50)).pack(side="left", padx=3)
        ttk.Button(f, text="Abrir (100%)", command=lambda: self.enviar_oxi_todos(100)).pack(side="left", padx=3)
        ttk.Button(f, text="Enviar sliders", command=lambda: self.enviar_oxi_todos(None)).pack(side="left", padx=3)
        ttk.Label(tab, text="A barra mostra a última abertura confirmada pelo NODE 3.",
                  foreground="#666", font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 0))

    def _linha_servo(self, master, n):
        cfg = SERVOS[n]
        fr = ttk.Frame(master)
        fr.pack(fill="x", pady=4)
        cab = ttk.Frame(fr); cab.pack(fill="x")
        ttk.Label(cab, text=cfg["nome"], font=("Segoe UI", 9, "bold")).pack(side="left")
        b = badge(cab, width=15)
        b.pack(side="right")
        pb = ttk.Progressbar(fr, maximum=100, mode="determinate",
                             style=f"S{n}.Horizontal.TProgressbar")
        pb.pack(fill="x", pady=2)
        bot = ttk.Frame(fr); bot.pack(fill="x")
        ini = round(ang_para_pct(n, SERVO1_PADRAO)) if n == 1 else 0
        var = tk.IntVar(value=ini)
        ttk.Scale(bot, from_=0, to=100, variable=var,
                  command=lambda v, var=var: var.set(int(float(v)))).pack(side="left", fill="x", expand=True)
        sp = ttk.Spinbox(bot, from_=0, to=100, increment=5, textvariable=var, width=4)
        sp.pack(side="left", padx=3)
        sp.bind("<Return>", lambda e: self.enviar_servo(n))
        ttk.Label(bot, text="%").pack(side="left")
        ttk.Button(bot, text="Enviar", width=7, command=lambda: self.enviar_servo(n)).pack(side="left", padx=3)
        self.servo_ui[n] = {"var": var, "badge": b, "pb": pb}

    def _montar_graficos(self, master):
        fr_g = ttk.Frame(master)
        master.add(fr_g, weight=3)
        bar = ttk.Frame(fr_g); bar.pack(fill="x")
        ttk.Label(bar, text="Janela:").pack(side="left")
        self.cb_jan = ttk.Combobox(bar, width=7, state="readonly",
                                   values=["30 s", "60 s", "120 s", "300 s", "600 s", "1800 s"])
        self.cb_jan.set("120 s")
        self.cb_jan.pack(side="left", padx=4)
        self.v_pausa = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Pausar gráfico", variable=self.v_pausa).pack(side="left", padx=8)
        ttk.Button(bar, text="Limpar dados", command=self.limpar_dados).pack(side="left")
        self.l_amostras = ttk.Label(bar, text="")
        self.l_amostras.pack(side="right")

        self.fig = Figure(figsize=(8, 6), dpi=96, layout="constrained")
        gs = self.fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.85])
        self.ax = {"fluxo": self.fig.add_subplot(gs[0, 0]),
                   "temp_fluxo": self.fig.add_subplot(gs[0, 1]),
                   "pressao": self.fig.add_subplot(gs[1, 0]),
                   "temp_max": self.fig.add_subplot(gs[1, 1])}
        self.ax_servos = self.fig.add_subplot(gs[2, :])
        titulos = {"fluxo": "Fluxo", "temp_fluxo": "Temp. Fluxo (°C)",
                   "pressao": "Pressão", "temp_max": "Temp. Tanque (°C)"}
        self.linhas, self.refs = {}, {}
        for k, ax in self.ax.items():
            ax.set_title(titulos[k], fontsize=10)
            ax.grid(alpha=0.3)
            ax.tick_params(labelsize=8)
            for node in NODES_SENSOR:
                (self.linhas[(node, k)],) = ax.plot([], [], color=COR_NODE[node], lw=1.5,
                                                    label=f"NODE {node}")
        self.ax["fluxo"].legend(fontsize=7, loc="upper left")
        sp = SETPOINT_PADRAO
        self.refs["sp"] = self.ax["fluxo"].axhline(sp, ls="--", color="#2e7d32", lw=1)
        self.refs["sp_min"] = self.ax["fluxo"].axhline(sp - MARGEM_FLUXO, ls=":", color=COR_ALERTA, lw=1)
        self.refs["sp_max"] = self.ax["fluxo"].axhline(sp + MARGEM_FLUXO, ls=":", color=COR_ALERTA, lw=1)
        for v in (TEMP_FLUXO_MIN, TEMP_FLUXO_MAX):
            self.ax["temp_fluxo"].axhline(v, ls=":", color=COR_ALERTA, lw=1)
        self.ax["pressao"].axhline(PRESSAO_MAX, ls=":", color=COR_ALERTA, lw=1)
        for v in (TEMP_MAX_MIN, TEMP_MAX_MAX):
            self.ax["temp_max"].axhline(v, ls=":", color=COR_ALERTA, lw=1)

        a = self.ax_servos
        a.set_title("Abertura dos servos (%)", fontsize=10)
        a.grid(alpha=0.3)
        a.tick_params(labelsize=8)
        a.set_ylim(-5, 105)
        for n in SERVOS:
            (self.linhas[("servo", n)],) = a.plot([], [], color=COR_SERVO[n], lw=1.6,
                                                  drawstyle="steps-post", label=f"S{n}")
        a.legend(fontsize=7, loc="upper left", ncol=4)

        self.canvas = FigureCanvasTkAgg(self.fig, master=fr_g)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _montar_log(self, master):
        fr_log = ttk.LabelFrame(master, text="Monitor serial", padding=4)
        master.add(fr_log, weight=2)
        bar = ttk.Frame(fr_log); bar.pack(fill="x")
        self.v_sn = tk.BooleanVar(value=False)
        self.v_scroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Mostrar linhas de sensores (SN2/SN4)",
                        variable=self.v_sn).pack(side="left")
        ttk.Checkbutton(bar, text="Auto-rolagem", variable=self.v_scroll).pack(side="left", padx=8)
        ttk.Button(bar, text="Salvar log", command=self.salvar_log).pack(side="right")
        ttk.Button(bar, text="Limpar", command=lambda: self.txt.delete("1.0", "end")).pack(side="right", padx=4)

        cmd = ttk.Frame(fr_log); cmd.pack(side="bottom", fill="x", pady=(4, 0))
        ttk.Label(cmd, text="Comando livre → NODE 3:").pack(side="left")
        self.e_cmd = ttk.Entry(cmd)
        self.e_cmd.pack(side="left", fill="x", expand=True, padx=4)
        self.e_cmd.bind("<Return>", lambda e: self.enviar_livre())
        self.e_cmd.bind("<Up>", lambda e: self._historico(-1))
        self.e_cmd.bind("<Down>", lambda e: self._historico(1))
        ttk.Button(cmd, text="Enviar", command=self.enviar_livre).pack(side="left")

        self.txt = scrolledtext.ScrolledText(fr_log, height=8, font=("Consolas", 9),
                                             bg="#101418", fg="#d0d7de", insertbackground="white")
        self.txt.pack(fill="both", expand=True)
        self.txt.tag_config("tx", foreground="#64b5f6")
        self.txt.tag_config("alerta", foreground="#ff6b6b")
        self.txt.tag_config("ok", foreground="#81c784")
        self.txt.tag_config("info", foreground="#9e9e9e")
        self.txt.tag_config("aviso", foreground="#ffd54f")

    # ------------------------------------------------------------ conexão
    def atualizar_portas(self):
        portas = [f"{p.device} — {p.description}" for p in serial.tools.list_ports.comports()]
        portas.append(SIM_PORT)
        self.cb_porta["values"] = portas
        if self.cb_porta.get() not in portas:
            self.cb_porta.set(portas[0])

    def alternar_conexao(self):
        if self.worker:
            self.worker.stop()
            self.bt_con.config(state="disabled")
            return
        sel = self.cb_porta.get()
        if not sel:
            return
        porta = sel.split(" — ")[0]
        self.parser = ParserESP()
        if porta == SIM_PORT:
            self.worker = SimuladorESP(self.fila)
        else:
            self.worker = SerialWorker(porta, int(self.cb_baud.get()), self.fila)
        self.bt_con.config(state="disabled")
        self.worker.start()

    def reset_esp(self):
        if self.worker:
            try:
                self.worker.reset_esp()
                self.log("[Reiniciando ESP32...]", "info")
            except Exception as e:
                self.log(f"[Falha ao reiniciar: {e}]", "alerta")

    # ------------------------------------------------------------- envio
    def enviar(self, cmd, avisar=True):
        if not self.worker:
            if avisar:
                messagebox.showwarning(APP_TITLE, "Conecte-se ao ESP32 primeiro.")
            return False
        try:
            self.worker.send(cmd)
        except Exception as e:
            self.log(f"[Erro ao enviar '{cmd}': {e}]", "alerta")
            return False
        self.log(f"> {cmd}", "tx")
        return True

    def enviar_setpoint(self):
        try:
            v = float(self.e_sp.get().replace(",", "."))
        except ValueError:
            messagebox.showerror(APP_TITLE, "Setpoint inválido.")
            return
        if not SETPOINT_LIM[0] < v < SETPOINT_LIM[1]:
            messagebox.showerror(APP_TITLE, "O firmware aceita setpoint entre 5.0 e 100.0 (exclusivo).")
            return
        self.enviar(f"SET_FLUXO:{v:.2f}")

    def _pct_slider(self, n):
        try:
            return max(0, min(100, int(self.servo_ui[n]["var"].get())))
        except (tk.TclError, ValueError):
            messagebox.showerror(APP_TITLE, f"Valor inválido para {SERVOS[n]['nome']} (use 0 a 100).")
            return None

    def enviar_servo(self, n, avisar=True):
        pct = self._pct_slider(n)
        if pct is None:
            return
        self.servo_ui[n]["var"].set(pct)
        self.enviar(f"SERVO{n}:{pct_para_ang(n, pct)}", avisar=avisar)

    def enviar_oxi_todos(self, pct):
        """Envia os servos 2–4 em sequência (200 ms entre eles, para não lotar o rádio)."""
        if not self.worker:
            messagebox.showwarning(APP_TITLE, "Conecte-se ao ESP32 primeiro.")
            return
        for i, n in enumerate(SERVOS_OXI):
            if pct is not None:
                self.servo_ui[n]["var"].set(pct)
            self.after(i * 200, lambda n=n: self.enviar_servo(n, avisar=False))

    def enviar_livre(self):
        cmd = self.e_cmd.get().strip()
        if not cmd:
            return
        if self.enviar(cmd):
            self.hist_cmd.append(cmd)
            self.hist_idx = len(self.hist_cmd)
            self.e_cmd.delete(0, "end")

    def _historico(self, passo):
        if not self.hist_cmd:
            return "break"
        self.hist_idx = max(0, min(len(self.hist_cmd), self.hist_idx + passo))
        self.e_cmd.delete(0, "end")
        if self.hist_idx < len(self.hist_cmd):
            self.e_cmd.insert(0, self.hist_cmd[self.hist_idx])
        return "break"

    # ---------------------------------------------------- recepção / fila
    def _processar_fila(self):
        try:
            for _ in range(500):
                tipo, dado = self.fila.get_nowait()
                if tipo == "linha":
                    self._tratar_linha(dado)
                elif tipo == "conectado":
                    self._ao_conectar(dado)
                elif tipo == "desconectado":
                    self._ao_desconectar()
                elif tipo == "erro":
                    self.log(f"[{dado}]", "alerta")
        except queue.Empty:
            pass
        self.after(50, self._processar_fila)

    def _ao_conectar(self, porta):
        self.bt_con.config(text="Desconectar", state="normal")
        self.bt_reset.config(state="normal")
        self.cb_porta.config(state="disabled")
        self.l_con.config(text=f"  Conectado: {porta}  ", bg=COR_OK)
        self.log(f"[Conectado em {porta}]", "ok")

    def _ao_desconectar(self):
        self.worker = None
        self.bt_con.config(text="Conectar", state="normal")
        self.bt_reset.config(state="disabled")
        self.cb_porta.config(state="readonly")
        self.l_con.config(text="  Desconectado  ", bg=COR_NEUTRO)
        self.log("[Desconectado]", "info")

    def _tratar_linha(self, linha):
        eventos = self.parser.parse(linha)
        eh_sensor = any(e[0] == "sensor" for e in eventos)
        if not eh_sensor or self.v_sn.get():
            tag = None
            if "ALERTA" in linha or "Falha" in linha or "ERRO" in linha or linha.startswith("- "):
                tag = "alerta"
            elif "normalizado" in linha or "sucesso" in linha or "Estabilizado" in linha:
                tag = "ok"
            elif "Ajustando Servo" in linha:
                tag = "aviso"
            if linha.strip():
                self.log(linha, tag)
        for ev in eventos:
            self._aplicar_evento(ev)

    def _aplicar_evento(self, ev):
        tipo = ev[0]
        e = self.estado
        if tipo == "sensor":
            self._novo_dado(ev[1], ev[2])
            return
        if tipo == "boot":
            e.update(pid=True, rele1=True, rele2=True, setpoint=SETPOINT_PADRAO)
            e["servos"][1] = SERVO1_PADRAO
            self._atualizar_faixa_fluxo()
            self.log("[ESP32 iniciado — estados assumidos com os valores padrão do firmware]", "info")
        elif tipo == "pid":
            e["pid"] = ev[1]
        elif tipo == "servo":
            e["servos"][ev[1]] = ev[2]
        elif tipo == "setpoint":
            e["setpoint"] = ev[1]
            self._atualizar_faixa_fluxo()
        elif tipo == "rele":
            e[f"rele{ev[1]}"] = ev[2]
        elif tipo == "falha":
            e["falhas"] += 1
        self._atualizar_status()

    def _avaliar(self, d):
        sp = self.estado["setpoint"]
        return {
            "fluxo": sp - MARGEM_FLUXO <= d["fluxo"] <= sp + MARGEM_FLUXO,
            "temp_fluxo": TEMP_FLUXO_MIN <= d["temp_fluxo"] <= TEMP_FLUXO_MAX,
            "pressao": d["pressao"] <= PRESSAO_MAX,
            "temp_max": TEMP_MAX_MIN <= d["temp_max"] <= TEMP_MAX_MAX,
        }

    def _novo_dado(self, node, d):
        if node not in NODES_SENSOR:
            return
        agora = time.time()
        ok = self._avaliar(d)
        for k in VARS:
            self.cards[(node, k)].set(d[k], ok[k])
        e = self.estado
        alerta_antes = e["alerta"][node]
        e["alerta"][node] = not all(ok.values())
        if node != 2 and e["alerta"][node] and not alerta_antes:
            fora = [k for k in VARS if not ok[k]]
            self.log(f"[ALERTA NODE {node} (avaliado no PC): {', '.join(fora)}]", "alerta")
        e["ultimo"][node] = agora
        e["amostras"] += 1

        s = self.series[node]
        s["t"].append(agora)
        for k in VARS:
            s[k].append(d[k])

        if self.csv_w:
            pct = [self._pct_ou_vazio(n) for n in SERVOS]
            self.csv_w.writerow([datetime.now().isoformat(timespec="milliseconds"), node,
                                 d["fluxo"], d["temp_fluxo"], d["pressao"], d["temp_max"],
                                 e["setpoint"], *pct,
                                 self._bool(e["pid"]), self._bool(e["rele1"]),
                                 self._bool(e["rele2"]), int(e["alerta"][node])])
            self.csv_arq.flush()
        self._atualizar_status()

    def _pct_ou_vazio(self, n):
        ang = self.estado["servos"][n]
        return "" if ang is None else round(ang_para_pct(n, ang), 1)

    @staticmethod
    def _bool(v):
        return "" if v is None else int(v)

    # --------------------------------------------------------- atualização
    def _atualizar_faixa_fluxo(self):
        sp = self.estado["setpoint"]
        for node in NODES_SENSOR:
            self.cards[(node, "fluxo")].l_fx.config(
                text=f"alvo {sp:.1f}  ({sp - MARGEM_FLUXO:.1f} – {sp + MARGEM_FLUXO:.1f})")
        if self.refs:
            self.refs["sp"].set_ydata([sp, sp])
            self.refs["sp_min"].set_ydata([sp - MARGEM_FLUXO] * 2)
            self.refs["sp_max"].set_ydata([sp + MARGEM_FLUXO] * 2)

    def _atualizar_status(self):
        e = self.estado
        agora = time.time()
        for node in NODES_SENSOR:
            link = (agora - e["ultimo"][node]) <= LINK_TIMEOUT
            self.b_link[node].config(text="recebendo" if link else "sem dados",
                                     bg=COR_OK if link else COR_NEUTRO)
            if link:
                al = e["alerta"][node]
                self.b_alerta[node].config(text="ALERTA!" if al else "Normal",
                                           bg=COR_ALERTA if al else COR_OK)
            else:
                self.b_alerta[node].config(text="—", bg=COR_NEUTRO)

        def onoff(b, v, on="Ligado", off="Desligado"):
            if v is None:
                b.config(text="?", bg=COR_NEUTRO)
            else:
                b.config(text=on if v else off, bg=COR_OK if v else COR_ALERTA)

        onoff(self.b_pid, e["pid"], "Automático", "Manual")
        onoff(self.b_rele[1], e["rele1"])
        onoff(self.b_rele[2], e["rele2"])
        self.b_sp.config(text=f"atual {e['setpoint']:.2f}", bg=COR_INFO)
        self.b_falhas.config(text=str(e["falhas"]), bg=COR_AVISO if e["falhas"] else COR_OK)

        for n, ui in self.servo_ui.items():
            ang = e["servos"][n]
            if ang is None:
                ui["badge"].config(text="? (desconhecido)", bg=COR_NEUTRO)
                ui["pb"]["value"] = 0
            else:
                pct = ang_para_pct(n, ang)
                ui["badge"].config(text=f"{pct:.0f}%  ({ang}°)", bg=COR_SERVO[n])
                ui["pb"]["value"] = pct
        self.l_aviso_servo.config(
            text="PID ligado: o controle automático pode sobrescrever o Servo 1." if e["pid"] else "")

    def _tick(self):
        agora = time.time()
        self._atualizar_status()
        for node in NODES_SENSOR:
            if agora - self.estado["ultimo"][node] > LINK_TIMEOUT:
                for k in VARS:
                    self.cards[(node, k)].neutro()
        if self.worker:                                 # histórico de abertura dos servos
            ss = self.serie_servos
            ss["t"].append(agora)
            for n in SERVOS:
                ang = self.estado["servos"][n]
                ss[n].append(np.nan if ang is None else ang_para_pct(n, ang))
        if not self.v_pausa.get():
            self._atualizar_grafico()
        self.l_amostras.config(text=f"amostras: {self.estado['amostras']}"
                                    + ("   ● gravando CSV" if self.csv_w else ""))
        self.after(500, self._tick)

    @staticmethod
    def _recorte(serie_t, agora, jan):
        if not serie_t:
            return None, None
        t = np.fromiter(serie_t, float) - agora
        mask = t >= -jan
        return t[mask], mask

    def _atualizar_grafico(self):
        jan = float(self.cb_jan.get().split()[0])
        agora = time.time()
        sp = self.estado["setpoint"]
        refs = {"fluxo": [sp - MARGEM_FLUXO, sp + MARGEM_FLUXO],
                "temp_fluxo": [TEMP_FLUXO_MIN, TEMP_FLUXO_MAX],
                "pressao": [PRESSAO_MAX], "temp_max": [TEMP_MAX_MIN, TEMP_MAX_MAX]}
        cortes = {n: self._recorte(self.series[n]["t"], agora, jan) for n in NODES_SENSOR}
        for k, ax in self.ax.items():
            vals = [np.array(refs[k], float)]
            for n in NODES_SENSOR:
                t, mask = cortes[n]
                if t is None:
                    self.linhas[(n, k)].set_data([], [])
                    continue
                y = np.fromiter(self.series[n][k], float)[mask]
                self.linhas[(n, k)].set_data(t, y)
                vals.append(y)
            v = np.concatenate(vals)
            lo, hi = float(np.nanmin(v)), float(np.nanmax(v))
            pad = max((hi - lo) * 0.1, 0.5)
            ax.set_xlim(-jan, 0)
            ax.set_ylim(lo - pad, hi + pad)

        t, mask = self._recorte(self.serie_servos["t"], agora, jan)
        for n in SERVOS:
            if t is None:
                self.linhas[("servo", n)].set_data([], [])
            else:
                self.linhas[("servo", n)].set_data(t, np.fromiter(self.serie_servos[n], float)[mask])
        self.ax_servos.set_xlim(-jan, 0)
        self.canvas.draw_idle()

    def limpar_dados(self):
        for s in list(self.series.values()) + [self.serie_servos]:
            for d in s.values():
                d.clear()
        self.estado["amostras"] = 0
        self._atualizar_grafico()

    # ---------------------------------------------------------------- log
    def log(self, texto, tag=None):
        hora = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.txt.insert("end", f"[{hora}] {texto}\n", tag or ())
        linhas = int(self.txt.index("end-1c").split(".")[0])
        if linhas > 4000:
            self.txt.delete("1.0", f"{linhas - 3000}.0")
        if self.v_scroll.get():
            self.txt.see("end")

    def salvar_log(self):
        nome = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Texto", "*.txt")],
            initialfile=f"log_esp32_{datetime.now():%Y%m%d_%H%M%S}.txt")
        if nome:
            with open(nome, "w", encoding="utf-8") as f:
                f.write(self.txt.get("1.0", "end"))

    def alternar_csv(self):
        if self.csv_w:
            self.csv_arq.close()
            self.csv_arq = self.csv_w = None
            self.bt_csv.config(text="● Gravar CSV")
            self.log("[Gravação CSV encerrada]", "info")
            return
        nome = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"dados_esp32_{datetime.now():%Y%m%d_%H%M%S}.csv")
        if not nome:
            return
        self.csv_arq = open(nome, "w", newline="", encoding="utf-8")
        self.csv_w = csv.writer(self.csv_arq, delimiter=";")
        self.csv_w.writerow(["timestamp", "node", "fluxo", "temp_fluxo", "pressao", "temp_tanque",
                             "setpoint"] + [f"servo{n}_pct" for n in SERVOS]
                            + ["pid", "rele1", "rele2", "alerta"])
        self.bt_csv.config(text="■ Parar CSV")
        self.log(f"[Gravando CSV em {nome}]", "ok")

    def ao_fechar(self):
        if self.worker:
            self.worker.stop()
            self.worker.join(timeout=1.0)
        if self.csv_arq:
            self.csv_arq.close()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
