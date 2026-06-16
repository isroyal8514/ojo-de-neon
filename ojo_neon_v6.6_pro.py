#!/usr/bin/env python3
# ojo_neon_v6.6_pro.py
import os
import sys

# Silenciar logs de OpenCV a nivel de sistema operativo
os.environ["OPENCV_LOG_LEVEL"] = "OFF"

import cv2
import time
import json
import subprocess
import urllib.request
import select
import threading
import argparse
from pyzbar.pyzbar import decode

# =========================================================================
# CONFIGURACIÓN DE RUTAS Y PARÁMETROS
# =========================================================================
APP_DIR = os.path.expanduser("~/.ojo_neon")
HISTORIAL_PATH = os.path.join(APP_DIR, "historial.json")
os.makedirs(APP_DIR, exist_ok=True)

COOLDOWN_REPETICION = 5.0
qr_memorizados = {}

# Paleta de Colores ANSI Neón
PURPLE = "\033[1;35m"
GOLD   = "\033[1;33m"
CYAN   = "\033[1;36m"
GREEN  = "\033[1;32m"
RED    = "\033[1;31m"
RESET  = "\033[0m"

# Lista negra preventiva de seguridad de comandos
PALABRAS_PELIGROSAS = ["rm", "mv", "dd", "shutdown", "mkfs", "reboot", ":(){ :|:& };:", "> /dev/"]

try: cv2.setLogLevel(0)
except: pass

# =========================================================================
# INTERFAZ VISUAL DE LA TERMINAL (Modo Cámara)
# =========================================================================
def limpiar_y_renderizar_ui(estado="ESPERANDO QR"):
    os.system('clear')
    print(rf"""{PURPLE}
   ____  _       ____  _____   _   _ _____ ___  _   _ 
  / __ \| |     / __ \|_   _| | \ | | ____/ _ \| \ | |
 | |  | | |    | |  | | | |   |  \| |  _|| | | |  \| |
 | |__| | |___ | |__| | | |   | |\  | |__| |_| | |\  |
  \____/|_____| \____/  |_|   |_| \_|_____\___/|_| \_| {GOLD}v6.6 PRO
{RESET}""")
    print(f"{CYAN} ----------------------------------------------------------------------{RESET}")
    print(f" {GOLD}SETUP:{RESET} COCLE / DEBIAN | {GOLD}ESTADO:{RESET} [{estado}]")
    print(f" {GOLD}CONTROL DE SALIDA:{RESET} Presiona [{PURPLE}Q{RESET}] o [{PURPLE}ENTER{RESET}] para cerrar la terminal")
    print(f"{CYAN} ----------------------------------------------------------------------{RESET}\n")

# =========================================================================
# UTILERÍAS DE INFRAESTRUCTURA Y TUBERÍAS
# =========================================================================
def enviar_notificacion(titulo, mensaje, icono="dialog-information"):
    try: subprocess.Popen(["notify-send", "-i", icono, titulo, mensaje])
    except: pass

def guardar_en_historial(tipo, contenido):
    try:
        data = []
        if os.path.exists(HISTORIAL_PATH):
            with open(HISTORIAL_PATH, "r") as f: data = json.load(f)
        data.append({"fecha": time.strftime("%F %T"), "tipo": tipo, "contenido": contenido})
        with open(HISTORIAL_PATH, "w") as f: json.dump(data, f, indent=2, ensure_ascii=False)
    except: pass

def abrir_en_sistema_seguro(comando_lista):
    try: subprocess.Popen(comando_lista, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
    except: pass

def descargar_imagen_flotante_hilo(url):
    try:
        nombre_archivo = f"qr_img_{int(time.time())}" + os.path.splitext(url)[1]
        ruta_temporal = os.path.join("/tmp", nombre_archivo)
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=4) as response, open(ruta_temporal, 'wb') as out_file:
            out_file.write(response.read())
        
        abrir_en_sistema_seguro(["xdg-open", ruta_temporal])
    except Exception:
        abrir_en_sistema_seguro(["xdg-open", url])

def wifi_handler(contenido):
    try:
        partes = contenido.split(';')
        ssid, password = "", ""
        for parte in partes:
            if parte.startswith("WIFI:S:") or parte.startswith("S:"):
                ssid = parte.replace("WIFI:S:", "").replace("S:", "")
            elif parte.startswith("P:"):
                password = parte.replace("P:", "")
        if ssid:
            enviar_notificacion("📶 WiFi Detectado", f"Configurando red: {ssid}", "network-wireless")
            comando = f"nmcli connection add type wifi ifname '*' con-name '{ssid}' ssid '{ssid}' -- wifi-sec.key-mgmt wpa-psk wifi-sec.psk '{password}'"
            res = subprocess.run(comando, shell=True, capture_output=True, text=True)
            if res.returncode == 0 or "already exists" in res.stderr or "ya existe" in res.stderr:
                abrir_en_sistema_seguro(["nmcli", "connection", "up", ssid])
                enviar_notificacion("✅ Conectado", f"Interfaz lista en {ssid}")
    except: pass

# =========================================================================
# FILTRO DE SEGURIDAD PARA COMANDOS (SANDBOX)
# =========================================================================
def evaluar_y_confirmar_comando(comando, modo_archivo):
    # Si viene desde captura de pantalla, forzar apertura de Kitty para confirmación interactiva
    if modo_archivo:
        print(f"{GOLD}[!] Comando detectado desde la pantalla. Abriendo terminal de validación...{RESET}")
        # CORRECCIÓN AQUÍ: Cambiamos la ruta fija por sys.argv[0]
        subprocess.Popen(["kitty", "--class", "ojo-neon-pop", "python3", sys.argv[0], "--run-cmd-direct", comando])
        return False
    es_peligroso = any(palabra in comando.split() for palabra in PALABRAS_PELIGROSAS) or ";" in comando or "&&" in comando

    if es_peligroso:
        limpiar_y_renderizar_ui(estado="⚠️ ALERTA DE SEGURIDAD")
        print(f"{RED}████████████████████████████████████████████████████████████{RESET}")
        print(f"{RED}[⚠️] ADVERTENCIA CRÍTICA: SE DETECTÓ UN COMANDO POTENCIALMENTE PELIGROSO{RESET}")
        print(f"{RED}████████████████████████████████████████████████████████████\n{RESET}")
        print(f" {GOLD}Comando a evaluar:{RESET} {PURPLE}{comando}{RESET}\n")
        print(f" {RED}Peligro:{RESET} Contiene instrucciones de alteración del núcleo o borrado masivo de datos.\n")
        print(f" ¿Deseas ejecutarlo de todas formas? Escribe [{RED}S{RESET}] para confirmar o [{GREEN}N/Q{RESET}] para abortar y cerrar.")
        
        while True:
            r = sys.stdin.readline().strip().lower()
            if r == 's': return True
            if r in ['n', 'q', '']: 
                print(f"{RED}[🔒] Abortando y cerrando terminal...{RESET}")
                os.system("kill -9 $PPID") # Mata la terminal Kitty que lo contiene de inmediato
                sys.exit(0)
    else:
        limpiar_y_renderizar_ui(estado="❓ CONFIRMACIÓN DE ACCIÓN")
        print(f" {GOLD}[❓] El QR quiere ejecutar el siguiente comando:{RESET}")
        print(f" 💾 {CYAN}{comando}{RESET}\n")
        print(f" Presiona [{GREEN}ENTER{RESET}] para autorizar la ejecución o [{RED}Q{RESET}] para cancelar y cerrar.")
        
        while True:
            r = sys.stdin.readline().strip().lower()
            if r == '': return True
            if r == 'q': 
                print(f"{RED}[🔒] Cancelado por el usuario. Cerrando terminal...{RESET}")
                os.system("kill -9 $PPID") # Suicidio limpio de la terminal Kitty flotante
                sys.exit(0)

# =========================================================================
# ENRUTADOR CENTRAL DE ACCIONES
# =========================================================================
def procesar_codigo_qr(contenido, modo_archivo=False):
    ahora = time.time()
    if contenido in qr_memorizados and (ahora - qr_memorizados[contenido]) < COOLDOWN_REPETICION:
        return False

    qr_memorizados[contenido] = ahora

    # Enlaces Web e Imágenes
    if contenido.startswith(("http://", "https://")):
        url = contenido.strip()
        guardar_en_historial("url", url)
        extensiones_imagen = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
        if any(url.lower().endswith(ext) for ext in extensiones_imagen):
            enviar_notificacion("🖼️ Imagen por QR", "Descargando en segundo plano...", "image-x-generic")
            threading.Thread(target=descargar_imagen_flotante_hilo, args=(url,), daemon=True).start()
        else:
            enviar_notificacion("🌐 Ojo de Neón", f"Abriendo: {url[:30]}...", "browser")
            abrir_en_sistema_seguro(["xdg-open", url])
        return True

    # Redes WiFi
    elif contenido.startswith("WIFI:"):
        guardar_en_historial("wifi", contenido)
        wifi_handler(contenido)
        return True

    # Comandos de Consola (CMD:)
    elif contenido.startswith("CMD:"):
        comando = contenido[4:].strip()
        if evaluar_y_confirmar_comando(comando, modo_archivo):
            guardar_en_historial("cmd", comando)
            enviar_notificacion("⚡ Comando Ejecutado", comando, "utilities-terminal")
            try: subprocess.Popen(comando, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
            except: pass
            
            # Si venía de una validación de pantalla (--run-cmd-direct), cerrar la terminal emergente tras ejecutar
            if len(sys.argv) > 1 and "--run-cmd-direct" in sys.argv:
                os.system("kill -9 $PPID")
                sys.exit(0)
            return True
        return True

    # Texto Plano a Portapapeles
    else:
        guardar_en_historial("texto", contenido)
        enviar_notificacion("📝 Texto Copiado", "Volcado al portapapeles de Wayland", "edit-copy")
        try:
            p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, text=True)
            p.communicate(input=contenido)
        except: pass
        return True

# =========================================================================
# CONTROLADORES DE INGRESO DE FLUJO (CÁMARA VS ARCHIVO)
# =========================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archivo", type=str, help="Ruta de imagen para escaneo instantáneo")
    parser.add_argument("--run-cmd-direct", type=str, help="Lanzador interno para confirmaciones flotantes")
    args = parser.parse_args()

    # Sub-modo técnico: Confirmación flotante forzada para capturas de comandos
    if args.run_cmd_direct:
        if evaluar_y_confirmar_comando(args.run_cmd_direct, modo_archivo=False):
            guardar_en_historial("cmd", args.run_cmd_direct)
            enviar_notificacion("⚡ Comando Ejecutado", args.run_cmd_direct, "utilities-terminal")
            subprocess.Popen(args.run_cmd_direct, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
            time.sleep(0.5)
            os.system("kill -9 $PPID")
        sys.exit(0)

    # MODO A: Escaneo de imágenes/capturas locales
    if args.archivo:
        if not os.path.exists(args.archivo):
            sys.exit(1)
        frame_estatico = cv2.imread(args.archivo)
        codigos = decode(frame_estatico)
        if codigos:
            for cod in codigos:
                datos = cod.data.decode('utf-8')
                procesar_codigo_qr(datos, modo_archivo=True)
        else:
            enviar_notificacion("ℹ️ Ojo de Neón", "No se detectó ningún código QR en el recorte", "dialog-information")
        sys.exit(0)

    # MODO B: Escaneo en vivo por Cámara
    limpiar_y_renderizar_ui()
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print(f"{RED}[❌] Error: No se puede acceder al hardware de la cámara (/dev/video0).{RESET}")
        sys.exit(1)

    try:
        while True:
            # Revisa si hay teclas en el buffer sin bloquear el hilo de la cámara
            if select.select([sys.stdin], [], [], 0.01)[0]:
                entrada = sys.stdin.readline().strip().lower()
                # Si es 'q', o si es un ENTER vacío, romper el bucle e ir al cierre definitivo
                if entrada == 'q' or entrada == '':
                    break

            ret, frame = cap.read()
            if not ret: continue

            for codigo in decode(frame):
                try:
                    datos_deco = codigo.data.decode('utf-8')
                    if procesar_codigo_qr(datos_deco, modo_archivo=False):
                        time.sleep(1.2)
                        limpiar_y_renderizar_ui()
                except Exception as error:
                    print(f"{RED}[!] Error: {error}{RESET}")

            cv2.waitKey(1)

    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n{RED}[🔒] Desconectando hardware y liberando buffers...{RESET}")
        cap.release()
        cv2.destroyAllWindows()
        print(f"{GREEN}[✅] Ojo de Neón cerrado. Destruyendo terminal...{RESET}\n")
        time.sleep(0.2)
        # Usamos kill -9 $PPID para forzar el cierre completo de la ventana de Kitty que hospeda al script
        os.system("kill -9 $PPID")
        sys.exit(0)
