# Importaciones básicas
from tkinter import messagebox
from threading import Thread, Lock, current_thread
from io import BytesIO
from datetime import datetime
import os
import time
import csv
import json
import traceback
import importlib
import pygame
import sys

class CerrarPrograma(Exception):
    """Excepción personalizada para cerrar el programa limpiamente"""
    pass
import subprocess
import tkinter as tk
import numpy as np
import glob
import math

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

# Constantes de colores
BLANCO = (255, 255, 255)
VERDE = (0, 255, 0)
GRIS = (128, 128, 128)
ROJO = (255, 0, 0)
VERDE_OSCURO = (0, 100, 0)
VERDE_CLARO = (180, 255, 180)
VERDE_BOTON = (0, 150, 0)
AZUL = (0, 120, 255)
VERDE_BORDE = (0, 200, 0)
AMARILLO = (255, 255, 0)
CYAN = (0, 255, 255)
NEGRO = (0, 0, 0)
MORADO = (128, 0, 128)
DORADO = (255, 215, 0)
NARANJA = (255, 140, 0)
ROSA = (255, 20, 147)
GRIS_CLARO = (200, 200, 200)

# Clase para leer datos de sensores ECG del Arduino
class ArduinoSensorReader:
    def __init__(self, puerto=None, baudrate=115200):
        self.puerto = puerto
        self.baudrate = baudrate
        self.conexion = None
        self.conectado = False
        self.data_buffer_hombro = []  # Canal ECG Hombro (A0)
        self.data_buffer_antebrazo = []  # Canal ECG Antebrazo (A1)
        self.lock = Lock()
        self.thread = None
        self.running = False

    def autodetectar_puerto(self):
        """Busca automáticamente el puerto donde está conectado el Arduino."""
        if not SERIAL_OK:
            print("[AVISO] pyserial no está instalado; no se puede autodetectar puertos.")
            return None
        try:
            import serial.tools.list_ports
        except Exception:
            print("[AVISO] No se pudo importar serial.tools.list_ports.")
            return None
        
        puertos = list(serial.tools.list_ports.comports())
        for puerto in puertos:
            if "ACM" in puerto.device or "USB" in puerto.device:
                print(f"Puerto Arduino detectado: {puerto.device}")
                return puerto.device
        if puertos:
            print(f"No se encontró un puerto Arduino específico, usando el primero: {puertos[0].device}")
            return puertos[0].device
        return None

    def conectar(self):
        if not SERIAL_OK:
            print("[AVISO] pyserial no está instalado.")
            return False
        if self.puerto is None:
            self.puerto = self.autodetectar_puerto()
            if self.puerto is None:
                print("No se pudo encontrar un puerto serial.")
                return False
        try:
            self.conexion = serial.Serial(self.puerto, self.baudrate, timeout=1)
            self.conectado = True
            self.running = True
            self.thread = Thread(target=self._leer_datos)
            self.thread.daemon = True
            self.thread.start()
            print(f"Conectado a Arduino en {self.puerto}")
            return True
        except serial.SerialException as e:
            print(f"Error al conectar a {self.puerto}: {e}")
            self.conectado = False
            return False

    def _leer_datos(self):
        while self.running and self.conexion:
            try:
                linea = self.conexion.readline().decode('utf-8').strip()
                if linea and "Musculo_1:" in linea and "Musculo_2:" in linea:
                    partes = linea.split(',')
                    valor_hombro_str = partes[0].split(':')[1]
                    valor_antebrazo_str = partes[1].split(':')[1]
                    
                    valor_hombro = float(valor_hombro_str)
                    valor_antebrazo = float(valor_antebrazo_str)

                    with self.lock:
                        self.data_buffer_hombro.append(valor_hombro)
                        self.data_buffer_antebrazo.append(valor_antebrazo)
                        
                        # Mantener los buffers con un tamaño máximo
                        if len(self.data_buffer_hombro) > 500:
                            self.data_buffer_hombro.pop(0)
                        if len(self.data_buffer_antebrazo) > 500:
                            self.data_buffer_antebrazo.pop(0)

            except (ValueError, UnicodeDecodeError, IndexError):
                # Ignorar líneas mal formadas o con errores
                pass
            except serial.SerialException:
                self._desconectar_interno()
                break

    def _desconectar_interno(self):
        """Desconexión interna sin join() - para llamar desde el mismo hilo"""
        self.running = False
        if self.conexion and self.conexion.is_open:
            self.conexion.close()
        self.conectado = False
        print("Desconectado de Arduino (error de conexión).")

    def desconectar(self):
        """Desconexión externa - para llamar desde otro hilo"""
        self.running = False
        if self.thread and self.thread != current_thread():
            self.thread.join()
        if self.conexion and self.conexion.is_open:
            self.conexion.close()
        self.conectado = False
        print("Desconectado de Arduino.")

    def obtener_datos_hombro(self):
        with self.lock:
            return list(self.data_buffer_hombro)

    def obtener_datos_antebrazo(self):
        with self.lock:
            return list(self.data_buffer_antebrazo)

# Constantes de configuración
INTERVALO_GUARDADO = 60  # segundos
TIEMPOS_RUTINAS = {
    'rutina1': 1.0,
    'rutina2': 1.0,
}

# Base directory for all app data files (CSV backups, patient data, etc.)
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')

# Intentar importar pyserial
SERIAL_OK = True
try:
    import serial
    import serial.tools.list_ports
except Exception:
    serial = None
    SERIAL_OK = False
    print("[AVISO] 'pyserial' no está instalado. La conexión con Arduino se deshabilitará.\n       Instale con: pip install pyserial")

# Matplotlib - importación perezosa
MATPLOTLIB_OK = False
plt = None
FigureCanvasAgg = None

def _try_import_matplotlib():
    """Intenta importar matplotlib de forma perezosa. Devuelve True si está disponible."""
    global MATPLOTLIB_OK, plt, FigureCanvasAgg
    if MATPLOTLIB_OK and plt is not None and FigureCanvasAgg is not None:
        return True
    try:
        m = importlib.import_module('matplotlib')
        try:
            getattr(m, 'use')('Agg')
        except Exception:
            pass
        plt_mod = importlib.import_module('matplotlib.pyplot')
        backend_agg = importlib.import_module('matplotlib.backends.backend_agg')
        plt = plt_mod
        FigureCanvasAgg = getattr(backend_agg, 'FigureCanvasAgg')
        
        # Configuración para mejorar el renderizado de texto
        try:
            plt.rcParams['font.size'] = 10
            plt.rcParams['axes.titlesize'] = 14
            plt.rcParams['axes.labelsize'] = 12
            plt.rcParams['xtick.labelsize'] = 10
            plt.rcParams['ytick.labelsize'] = 10
            plt.rcParams['text.antialiased'] = True
            plt.rcParams['axes.titleweight'] = 'bold'
        except Exception as e:
            print(f"[DEBUG] Error configurando matplotlib: {e}")
        
        MATPLOTLIB_OK = True
        return True
    except Exception:
        MATPLOTLIB_OK = False
        plt = None
        FigureCanvasAgg = None
        return False

# Pandas - importación perezosa
PANDAS_OK = False
pd = None

def _try_import_pandas():
    """Intenta importar pandas de forma perezosa. Devuelve True si está disponible."""
    global PANDAS_OK, pd
    if PANDAS_OK and pd is not None:
        return True
    try:
        pd = importlib.import_module('pandas')
        PANDAS_OK = True
        return True
    except Exception:
        PANDAS_OK = False
        pd = None
        return False

# Funciones auxiliares de Tkinter
def maximizar_tk(root):
    try:
        root.state('zoomed')  # Windows
    except Exception:
        try:
            root.attributes('-zoomed', True)  # Linux (algunos entornos)
        except Exception:
            root.attributes('-fullscreen', True)  # Fallback

# Clase GestorPacientes
class GestorPacientes:
    def __init__(self):
        self.pacientes = {}
        self.ruta_backup = os.path.join(BASE_DIR, 'backup_pacientes.csv')
        self._cargar_pacientes()

    def _cargar_pacientes(self):
        """Carga pacientes desde el archivo CSV de backup."""
        if not os.path.exists(self.ruta_backup):
            return
        
        try:
            import csv
            with open(self.ruta_backup, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for fila in reader:
                    nombre_completo = self._construir_nombre_completo(fila)
                    if nombre_completo:
                        nombre_normalizado = self._normalizar_nombre(nombre_completo)
                        self.pacientes[nombre_normalizado] = fila
                        print(f"[INFO] Paciente cargado: {nombre_completo}")
        except Exception as e:
            print(f"[ERROR] No se pudo cargar backup de pacientes: {e}")
    
    def _construir_nombre_completo(self, datos):
        """Construye el nombre completo desde un diccionario de datos."""
        partes = [
            datos.get('primer_nombre', '').strip(),
            datos.get('segundo_nombre', '').strip(),
            datos.get('primer_apellido', '').strip(),
            datos.get('segundo_apellido', '').strip()
        ]
        return ' '.join([p for p in partes if p])
    
    def _normalizar_nombre(self, nombre):
        """Normaliza un nombre eliminando espacios extras y convirtiendo a minúsculas."""
        return ' '.join(nombre.lower().split())

    def registrar_paciente(self, datos):
        """Registra un paciente usando los datos proporcionados. Devuelve (exito, resultado)."""
        primer_nombre = datos.get('primer_nombre', '').strip()
        primer_apellido = datos.get('primer_apellido', '').strip()
        
        if not primer_nombre or not primer_apellido:
            return False, 'Nombre y apellido son obligatorios'
        
        # Construir nombre completo y generar ID
        nombre_completo = self._construir_nombre_completo(datos)
        nombre_normalizado = self._normalizar_nombre(nombre_completo)
        
        id_paciente = self.generar_id_paciente(
            primer_nombre, 
            primer_apellido, 
            datos.get('año_nacimiento', '0000')
        )
        
        # Guardar en memoria y archivo
        self.guardar_paciente(nombre_normalizado, datos)
        
        print(f"[INFO] Paciente registrado: {nombre_completo} (ID: {id_paciente})")
        return True, id_paciente

    def guardar_paciente(self, nombre_completo, datos):
        """Guarda un paciente en el registro y en backup_pacientes.csv."""
        import csv
        self.pacientes[nombre_completo] = datos
        
        campos = ['primer_nombre', 'segundo_nombre', 'primer_apellido', 'segundo_apellido', 
                 'año_nacimiento', 'sexo', 'telefono', 'email', 'observaciones']
        
        try:
            # Leer pacientes existentes
            pacientes_existentes = self._leer_pacientes_csv(campos)
            
            # Agregar el nuevo paciente
            fila = [datos.get(campo, '') for campo in campos]
            pacientes_existentes.append(fila)
            
            # Escribir todos los pacientes al archivo
            self._escribir_pacientes_csv(campos, pacientes_existentes)
            
            print(f"[INFO] Paciente guardado en CSV")
        except Exception as e:
            print(f"[ERROR] No se pudo guardar backup de paciente: {e}")
        
        return True
    
    def _leer_pacientes_csv(self, campos):
        """Lee todos los pacientes existentes del CSV."""
        pacientes = []
        if os.path.exists(self.ruta_backup):
            import csv
            with open(self.ruta_backup, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pacientes.append([row.get(campo, '') for campo in campos])
        return pacientes
    
    def _escribir_pacientes_csv(self, campos, pacientes):
        """Escribe todos los pacientes al CSV."""
        import csv
        with open(self.ruta_backup, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(campos)
            writer.writerows(pacientes)

    def buscar_paciente_por_nombre(self, nombre_completo):
        """Busca paciente por coincidencia parcial, ignorando mayúsculas y espacios extra."""
        nombre_normalizado = self._normalizar_nombre(nombre_completo)
        
        print(f"[INFO] Buscando paciente: '{nombre_completo}' (normalizado: '{nombre_normalizado}')")
        print(f"[INFO] Pacientes en memoria: {len(self.pacientes)}")
        
        # Buscar coincidencia exacta
        if nombre_normalizado in self.pacientes:
            print(f"[INFO] Coincidencia exacta encontrada")
            return nombre_normalizado, self.pacientes[nombre_normalizado]
        
        # Buscar coincidencia parcial
        for nombre, datos in self.pacientes.items():
            if nombre_normalizado in nombre or nombre in nombre_normalizado:
                print(f"[INFO] Coincidencia parcial encontrada: {nombre}")
                return nombre, datos
        
        print(f"[INFO] No se encontró el paciente")
        return None, {}
    
    def generar_id_paciente(self, primer_nombre, primer_apellido, año_nacimiento):
        """Genera un ID basado en nombre/apellido/año."""
        pn = (primer_nombre or "").strip().upper()[:3] or "XXX"
        pa = (primer_apellido or "").strip().upper()[:3] or "XXX"
        anio = str(año_nacimiento).strip()
        anio = anio if anio.isdigit() and len(anio) == 4 else "0000"
        base = f"{pn}{pa}{anio}".replace(" ", "")
        return base
    
    def guardar_sesion(self, id_paciente, esfuerzo_hombro, esfuerzo_antebrazo, duracion, observaciones=""):
        """Guarda una sesión de forma simple. Wrapper para registrar_sesion."""
        datos_sesion = {
            'esfuerzo_hombro': esfuerzo_hombro,
            'esfuerzo_antebrazo': esfuerzo_antebrazo,
            'duracion': duracion,
            'observaciones': observaciones
        }
        exito, resultado = self.registrar_sesion(id_paciente, datos_sesion)
        return exito
    
    def registrar_sesion(self, id_paciente, datos_sesion):
        """Registra una nueva sesión para un paciente (método simplificado)"""
        try:
            # Usar el id_paciente tal como viene (puede ser nombre completo o ID)
            # Normalizar para asegurar consistencia
            id_normalizado = id_paciente.strip()
            
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            nombre_archivo = f"sesion_{id_normalizado}_{timestamp}.csv"
            
            # Guardar datos en el directorio de backups
            ruta_sesion = os.path.join(BASE_DIR, f'sesiones_{id_normalizado}.csv')
            print(f"[DEBUG] Guardando sesión en: {ruta_sesion}")
            
            import csv
            # Verificar si el archivo existe y está vacío para escribir encabezados
            escribir_encabezados = not os.path.exists(ruta_sesion) or os.path.getsize(ruta_sesion) == 0
            
            with open(ruta_sesion, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                if escribir_encabezados:
                    writer.writerow(['fecha', 'esfuerzo_hombro', 'esfuerzo_antebrazo', 'duracion', 'observaciones'])
                
                writer.writerow([
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    datos_sesion.get('esfuerzo_hombro', 0),
                    datos_sesion.get('esfuerzo_antebrazo', 0),
                    datos_sesion.get('duracion', 0),
                    datos_sesion.get('observaciones', '')
                ])
            
            print(f"[INFO] Sesión guardada exitosamente")
            return True, timestamp
        except Exception as e:
            print(f"[ERROR] No se pudo registrar sesión: {e}")
            import traceback
            traceback.print_exc()
            return False, str(e)
    
    def obtener_datos_progreso(self, id_paciente):
        """Obtiene los datos de progreso de un paciente (método simplificado)"""
        try:
            # Asegurar que pandas esté disponible
            if not _try_import_pandas():
                print("[ERROR] pandas no está disponible para cargar datos de progreso")
                return None
            
            # Normalizar el id_paciente
            id_normalizado = id_paciente.strip()
            
            ruta_sesion = os.path.join(BASE_DIR, f'sesiones_{id_normalizado}.csv')
            print(f"[DEBUG] Buscando archivo: {ruta_sesion}")
            print(f"[DEBUG] ID del paciente: '{id_normalizado}'")
            
            if not os.path.exists(ruta_sesion):
                print(f"[INFO] No hay sesiones registradas para {id_normalizado}")
                print(f"[INFO] Archivo no encontrado: {ruta_sesion}")
                
                # Listar archivos disponibles en el directorio para diagnóstico
                print(f"[DEBUG] Archivos disponibles en {BASE_DIR}:")
                try:
                    import glob
                    archivos_sesiones = glob.glob(os.path.join(BASE_DIR, 'sesiones_*.csv'))
                    for archivo in archivos_sesiones:
                        print(f"  - {os.path.basename(archivo)}")
                except Exception:
                    pass
                
                return None
            
            # Leer el archivo CSV con pandas
            print(f"[DEBUG] Leyendo archivo CSV...")
            df = pd.read_csv(ruta_sesion)
            print(f"[DEBUG] Datos leídos exitosamente: {len(df)} filas")
            print(f"[DEBUG] Columnas: {list(df.columns)}")
            
            if len(df) == 0:
                print(f"[INFO] El archivo existe pero está vacío")
                return None
            
            # Transformar los datos al formato esperado por las gráficas
            df_transformado = pd.DataFrame({
                'Fecha': pd.to_datetime(df['fecha']),
                'Numero_Sesion': range(1, len(df) + 1),
                'Esfuerzo_Hombro_Promedio': pd.to_numeric(df['esfuerzo_hombro'], errors='coerce'),
                'Esfuerzo_Antebrazo_Promedio': pd.to_numeric(df['esfuerzo_antebrazo'], errors='coerce'),
                'Duracion_Minutos': pd.to_numeric(df['duracion'], errors='coerce'),
                'Observaciones': df['observaciones'] if 'observaciones' in df.columns else ''
            })
            
            print(f"[DEBUG] Datos transformados exitosamente")
            print(f"[DEBUG] Primeras filas:")
            print(df_transformado.head())
            
            return df_transformado
                
        except Exception as e:
            print(f"[ERROR] Error al obtener datos de progreso: {e}")
            import traceback
            traceback.print_exc()
            return None


class CheckBox:
    def __init__(self, x, y, texto, fuente):
        self.rect = pygame.Rect(x, y, 20, 20)
        self.texto = texto
        self.fuente = fuente
        self.marcado = False
        self.texto_rect = None
        
        # Calcular posición del texto
        texto_surface = self.fuente.render(self.texto, True, NEGRO)
        self.texto_rect = pygame.Rect(x + 25, y, texto_surface.get_width(), texto_surface.get_height())

    def dibujar(self, superficie):
        # Dibujar checkbox
        pygame.draw.rect(superficie, BLANCO, self.rect)
        pygame.draw.rect(superficie, NEGRO, self.rect, 2)
        
        # Dibujar marca si está marcado
        if self.marcado:
            pygame.draw.line(superficie, VERDE, 
                           (self.rect.x + 4, self.rect.y + 10),
                           (self.rect.x + 8, self.rect.y + 14), 3)
            pygame.draw.line(superficie, VERDE,
                           (self.rect.x + 8, self.rect.y + 14),
                           (self.rect.x + 16, self.rect.y + 6), 3)
        
        # Dibujar texto
        texto_surface = self.fuente.render(self.texto, True, NEGRO)
        superficie.blit(texto_surface, (self.texto_rect.x, self.texto_rect.y))

    def verificar_clic(self, pos):
        return self.rect.collidepoint(pos) or self.texto_rect.collidepoint(pos)

    def alternar(self):
        self.marcado = not self.marcado

class CampoTexto:
    def __init__(self, x, y, ancho, alto, etiqueta, fuente, separacion_checkbox=4, desfase_etiqueta=18):
        self.rect = pygame.Rect(x, y, ancho, alto)
        self.etiqueta = etiqueta
        self.fuente = fuente
        self.texto = ""
        self.activo = False
        self.tachado = False
        # Separación vertical configurable entre el campo y el checkbox
        self.separacion_checkbox = separacion_checkbox
        # Desfase vertical de la etiqueta respecto al campo (mayor valor = más separado)
        self.desfase_etiqueta = desfase_etiqueta
        # Posicionar checkbox debajo del campo con espaciado configurable
        self.checkbox = CheckBox(x, y + alto + self.separacion_checkbox, "No tengo este dato", fuente)

    def dibujar(self, superficie):
        # Dibujar etiqueta arriba del campo con desfase configurable
        etiqueta_surface = self.fuente.render(self.etiqueta, True, NEGRO)
        superficie.blit(etiqueta_surface, (self.rect.x, self.rect.y - self.desfase_etiqueta))
        
        # Dibujar campo
        color_borde = AZUL if self.activo else NEGRO
        pygame.draw.rect(superficie, BLANCO, self.rect)
        pygame.draw.rect(superficie, color_borde, self.rect, 2)
        
        # Dibujar texto
        texto_mostrar = self.texto if not self.checkbox.marcado else "*"
        color_texto = GRIS if self.checkbox.marcado else NEGRO
        
        texto_surface = self.fuente.render(texto_mostrar, True, color_texto)
        superficie.blit(texto_surface, (self.rect.x + 5, self.rect.y + (self.rect.height - texto_surface.get_height()) // 2))
        
        # Dibujar línea tachada si está marcado el checkbox
        if self.checkbox.marcado:
            pygame.draw.line(superficie, ROJO, 
                           (self.rect.x + 5, self.rect.centery),
                           (self.rect.right - 5, self.rect.centery), 2)
        
        # Posicionar checkbox con separación configurable y dibujarlo
        self.checkbox.rect.y = self.rect.y + self.rect.height + self.separacion_checkbox
        self.checkbox.texto_rect.y = self.checkbox.rect.y + (self.checkbox.rect.height - self.checkbox.texto_rect.height) // 2
        self.checkbox.dibujar(superficie)

    def manejar_clic(self, pos):
        if self.rect.collidepoint(pos):
            self.activo = True
            return True
        elif self.checkbox.verificar_clic(pos):
            self.checkbox.alternar()
            if self.checkbox.marcado:
                self.texto = "*"
            else:
                self.texto = ""
            return True
        else:
            self.activo = False
            return False

    def agregar_caracter(self, caracter):
        if not self.checkbox.marcado and len(self.texto) < 20:
            self.texto += caracter

    def borrar_caracter(self):
        if not self.checkbox.marcado and self.texto:
            self.texto = self.texto[:-1]

    def obtener_valor(self):
        return self.texto if not self.checkbox.marcado else "*"

class CampoTextoSimple:
    """Campo de texto simple sin checkbox"""
    def __init__(self, x, y, ancho, alto, etiqueta, fuente):
        self.rect = pygame.Rect(x, y, ancho, alto)
        self.etiqueta = etiqueta
        self.fuente = fuente
        self.texto = ""
        self.activo = False

    def dibujar(self, superficie):
        # Espaciado entre etiqueta y campo
        etiqueta_surface = self.fuente.render(self.etiqueta, True, NEGRO)
        superficie.blit(etiqueta_surface, (self.rect.x, self.rect.y - 18))
        
        # Dibujar campo
        color_borde = AZUL if self.activo else NEGRO
        pygame.draw.rect(superficie, BLANCO, self.rect)
        pygame.draw.rect(superficie, color_borde, self.rect, 2)
        
        # Dibujar texto
        texto_surface = self.fuente.render(self.texto, True, NEGRO)
        superficie.blit(texto_surface, (self.rect.x + 5, self.rect.y + (self.rect.height - texto_surface.get_height()) // 2))

    def manejar_clic(self, pos):
        if self.rect.collidepoint(pos):
            self.activo = True
            return True
        else:
            self.activo = False
            return False

    def agregar_caracter(self, caracter):
        if len(self.texto) < 50:  # Límite más alto para nombres completos
            self.texto += caracter

    def borrar_caracter(self):
        if self.texto:
            self.texto = self.texto[:-1]

    def obtener_valor(self):
        return self.texto

class ControladorCNC:
    def set_cmd_en_progreso(self, valor):
        self._cmd_en_progreso = valor

    def __init__(self, puerto=None, baudrate=115200):
        self.puerto = puerto
        self.baudrate = baudrate
        self.conexion = None
        self.conectado = False
        self.paso = 1.0
        self.posicion_x = 0.0
        self.posicion_y = 0.0
        self.modo_relativo = False
        self.velocidad_actual = 50
        self.override_actual = 100  # Override de feed/velocidad en %
        self.archivo_velocidad = os.path.join(BASE_DIR, 'velocidad_cnc.json')
        self.ov_feed = 100
        self.ov_rapid = 100
        self.ov_spindle = 100
        self.feed_reportado = 0.0
        self._last_status_poll = 0.0
        self._status_poll_interval = 0.15
        self._serial_lock = Lock()
        self.firmware = 'desconocido'  # 'grbl' | 'marlin' | 'desconocido'
        self.firmware_info = ""
        self._ultimo_ping = 0.0
        self._intervalo_ping = 2.0
        self._fallos_ping = 0
        self.ejecutando_rutina = False
        self._cmd_en_progreso = False
        self._ultimo_aplicar_ov = 0.0
        self._intervalo_aplicar_ov = 0.08
        self.mascara_direccion = None
        self.junction_deviation = None
        self.feed_base = 600
        self._eventos = []
        self._event_lock = Lock()
        self.ultimo_tiempo_verificacion = time.time()
        self.intervalo_verificacion = 1.0  # segundos, ajustar según necesidad
        self.ultimo_guardado = time.time()
        self.thread_monitor = None
        self.origen_establecido = False
        self.limites_activos = False
        self.debug_limites = False
        self.ultimo_limite = ""
        self.limite_x_min = -20.0
        self.limite_x_max = 20.0
        self.limite_y_min = -20.0
        self.limite_y_max = 20.0
        self.abortado_por_limite = False
        self.en_hold = False
        self._ultimo_dir_x = 1.0
        self._ultimo_dir_y = 1.0
        self.archivo_grbl_config = os.path.join(BASE_DIR, 'grbl_config.json')

    def aplicar_mascara_direccion(self, mascara: int | None = None):
        """Aplica $3 (Direction port invert mask) en GRBL. X=1, Y=2, Z=4. Rango 0..7.
        Si mascara es None, usa la cargada en self.mascara_direccion.
        """
        try:
            if mascara is None:
                mascara = self.mascara_direccion
            if mascara is None:
                return False
            mascara = max(0, min(7, int(mascara)))
            ok = self.enviar_comando(f"$3={mascara}")
            if ok:
                print(f"GRBL $3 (mascara de dirección) aplicada: {mascara}")
                self.mascara_direccion = mascara
            return ok
        except Exception as e:
            print(f"Error aplicando máscara de dirección $3: {e}")
            return False

    def set_mascara_direccion(self, mascara: int):
        """Actualiza y persiste la máscara $3 y la aplica en GRBL."""
        try:
            mascara = max(0, min(7, int(mascara)))
            # Persistir
            os.makedirs(os.path.dirname(self.archivo_grbl_config), exist_ok=True)
            with open(self.archivo_grbl_config, 'w') as f:
                json.dump({'mascara_direccion': mascara}, f)
            self.mascara_direccion = mascara
            # Aplicar inmediatamente si conectado
            if self.conectado:
                return self.aplicar_mascara_direccion(mascara)
            return True
        except Exception as e:
            print(f"Error guardando/aplicando máscara $3: {e}")
            return False

    def aplicar_junction_deviation(self, jd: float | None = None):
        """Aplica $11 (junction deviation) en GRBL para suavizar esquinas sin bajar velocidad.
        Valores típicos: 0.02 (fino), 0.05, 0.1 (más redondo)."""
        try:
            if self.firmware != 'grbl':
                return False
            if jd is None:
                jd = self.junction_deviation
            if jd is None:
                # Valor recomendado para suavizar sin perder precisión excesiva (un poco más suave)
                jd = 0.15
            jd = max(0.005, min(1.0, float(jd)))
            ok = self.enviar_comando(f"$11={jd}")
            if ok:
                print(f"GRBL $11 (junction deviation) aplicada: {jd} mm")
                self.junction_deviation = jd
            return ok
        except Exception as e:
            print(f"Error aplicando junction deviation $11: {e}")
            return False

    def set_junction_deviation(self, jd: float):
        """Actualiza y persiste junction deviation ($11)."""
        try:
            jd = max(0.005, min(1.0, float(jd)))
            os.makedirs(os.path.dirname(self.archivo_grbl_config), exist_ok=True)
            data = {}
            if os.path.exists(self.archivo_grbl_config):
                try:
                    with open(self.archivo_grbl_config, 'r') as f:
                        data = json.load(f) or {}
                except Exception:
                    data = {}
            data['junction_deviation'] = jd
            with open(self.archivo_grbl_config, 'w') as f:
                json.dump(data, f)
            self.junction_deviation = jd
            if self.conectado and self.firmware == 'grbl':
                return self.aplicar_junction_deviation(jd)
            return True
        except Exception as e:
            print(f"Error guardando/aplicando $11: {e}")
            return False
        
    def autodetectar_puerto(self):
        """Busca automáticamente el puerto donde está conectado el Arduino."""
        if not SERIAL_OK:
            print("[AVISO] pyserial no está instalado; no se puede autodetectar puertos.")
            return None
        try:
            import serial.tools.list_ports
        except Exception:
            print("[AVISO] No se pudo importar serial.tools.list_ports.")
            return None
        
        puertos = list(serial.tools.list_ports.comports())
        if not puertos:
            print("No se encontraron puertos seriales.")
            return None
        
        candidatos = []
        for puerto in puertos:
            port_str = str(puerto.device)
            if "ACM" in port_str or "USB" in port_str or "tty" in port_str:
                candidatos.append(puerto.device)
        
        for candidato in candidatos:
            if "ACM" in candidato:
                print(f"Puerto Arduino detectado: {candidato}")
                return candidato
        
        if candidatos:
            print(f"Puerto posible: {candidatos[0]}")
            return candidatos[0]
        
        for puerto in puertos:
            if "COM" in puerto.device:
                print(f"Puerto Windows detectado: {puerto.device}")
                return puerto.device
        
        print("No se pudo identificar un puerto Arduino.")
        return None
            
    def conectar(self):
        try:
            if not SERIAL_OK:
                print("[AVISO] pyserial no está instalado; no se puede establecer conexión serie.")
                return False
            # Al conectar, asumir que no hay origen de trabajo establecido aún
            self.origen_establecido = False
            self.limites_activos = False
            if self.puerto is None:
                self.puerto = self.autodetectar_puerto()
                if self.puerto is None:
                    print("No se pudo detectar un puerto para Arduino.")
                    return False
            
            self.conexion = serial.Serial(self.puerto, self.baudrate, timeout=1)
            time.sleep(2)
            try:
                # Limpiar buffers iniciales
                with self._serial_lock:
                    self.conexion.reset_input_buffer()
                    self.conexion.reset_output_buffer()
            except Exception as e:
                pass
            # Intentar identificar firmware con handshake real
            handshake_ok = False
            try:
                with self._serial_lock:
                    self.conexion.write(b"$I\n")  # Info de GRBL
                time.sleep(0.2)
                buf = []
                inicio = time.time()
                # Leer hasta 1s esperando alguna respuesta significativa
                while time.time() - inicio < 1.0:
                    with self._serial_lock:
                        if self.conexion.in_waiting:
                            linea = self.conexion.readline().decode(errors='ignore').strip()
                        else:
                            linea = ''
                    if linea:
                        buf.append(linea)
                        if 'Grbl' in linea or linea.lower().startswith('ok'):
                            handshake_ok = True
                            self.firmware = 'grbl'
                            if 'Grbl' in linea:
                                self.firmware_info = linea
                            break
                    else:
                        time.sleep(0.05)
            except Exception as e:
                handshake_ok = False

            # Intentar Marlin si no fue GRBL
            if not handshake_ok:
                try:
                    with self._serial_lock:
                        self.conexion.write(b"M115\n")
                    inicio = time.time()
                    while time.time() - inicio < 1.0 and not handshake_ok:
                        with self._serial_lock:
                            if self.conexion.in_waiting:
                                linea = self.conexion.readline().decode(errors='ignore').strip()
                            else:
                                linea = ''
                        if linea:
                            if 'FIRMWARE_NAME' in linea or linea.lower().startswith('ok'):
                                handshake_ok = True
                                self.firmware = 'marlin'
                                if 'FIRMWARE_NAME' in linea:
                                    self.firmware_info = linea
                                break
                        else:
                            time.sleep(0.05)
                except Exception as e:
                    handshake_ok = False

            if not handshake_ok:
                try:
                    self.conexion.close()
                except Exception as e:
                    pass
                self.conectado = False
                return False

            # Marcar como conectado y configurar según firmware
            self.conectado = True
            if self.firmware == 'grbl':
                self.enviar_comando("$X")
                self.enviar_comando("$21=0")  # Desactiva límites duros
                self.enviar_comando("$20=0")  # Desactiva límites blandos
                self.override_actual = 100
                self.aplicar_mascara_direccion()
                if not self.aplicar_junction_deviation(self.junction_deviation):
                    try:
                        self.aplicar_junction_deviation(0.15)
                    except Exception:
                        pass
            self.cargar_velocidad()
            self.aplicar_velocidad()
            return True
        except Exception as e:
            self.conectado = False
            return False


    def _leer_parametros_grbl(self) -> dict:
        """Lee $$ y devuelve un dict { 'n': 'valor' } con parámetros de GRBL."""
        out = {}
        if not (self.conectado and self.firmware == 'grbl' and self.conexion and self.conexion.is_open):
            return out
        try:
            with self._serial_lock:
                try:
                    self.conexion.reset_input_buffer()
                except Exception:
                    pass
                self.conexion.write(b"$$\n")
            limite = time.time() + 1.2
            while time.time() < limite:
                with self._serial_lock:
                    hay = self.conexion.in_waiting if self.conexion else 0
                if hay <= 0:
                    time.sleep(0.02)
                    continue
                with self._serial_lock:
                    linea = self.conexion.readline().decode(errors='ignore').strip()
                if not linea:
                    continue
                if linea.lower() == 'ok':
                    break
                if linea.startswith('$') and '=' in linea:
                    try:
                        s = linea.split('(')[0].strip()
                        k, v = s.split('=', 1)
                        k = k.lstrip('$').strip()
                        v = v.strip()
                        if k:
                            out[k] = v
                    except Exception:
                        continue
        except Exception:
            pass
        return out

    def consultar_info_firmware(self) -> str:
        """Consulta y devuelve una cadena con la información del firmware detectado."""
        try:
            if self.firmware == 'grbl':
                with self._serial_lock:
                    if self.conexion and self.conexion.is_open:
                        self.conexion.reset_input_buffer()
                        self.conexion.write(b"$I\n")
                time.sleep(0.2)
                info_line = ""
                limite = time.time() + 0.6
                while time.time() < limite:
                    with self._serial_lock:
                        if not (self.conexion and self.conexion.in_waiting):
                            break
                        linea = self.conexion.readline().decode(errors='ignore').strip()
                    if 'Grbl' in linea or linea.lower().startswith('['):
                        info_line = linea
                        break
                if info_line:
                    self.firmware_info = info_line
                return self.firmware_info or 'GRBL (sin detalles)'
            elif self.firmware == 'marlin':
                with self._serial_lock:
                    if self.conexion and self.conexion.is_open:
                        self.conexion.reset_input_buffer()
                        self.conexion.write(b"M115\n")
                time.sleep(0.2)
                info_line = ""
                limite = time.time() + 0.6
                while time.time() < limite:
                    with self._serial_lock:
                        if not (self.conexion and self.conexion.in_waiting):
                            break
                        linea = self.conexion.readline().decode(errors='ignore').strip()
                    if 'FIRMWARE_NAME' in linea:
                        info_line = linea
                        break
                if info_line:
                    self.firmware_info = info_line
                return self.firmware_info or 'Marlin (sin detalles)'
            else:
                return self.firmware_info or 'Firmware desconocido'
        except Exception as e:
            return self.firmware_info or f"No se pudo consultar firmware: {e}"
            
    def desconectar(self):
        if self.conexion and self.conexion.is_open:
            self.conexion.close()
            self.conectado = False
        # Al desconectar, desactivar límites y origen
        self.origen_establecido = False
        self.limites_activos = False

    def esta_conectado(self):
        """Devuelve True solo si hay un puerto serie abierto y operativo.
        Realiza un ping suave no intrusivo cada ~1s para validar que el dispositivo responde.
        """
        if not SERIAL_OK:
            self.conectado = False
            return False
        if not self.conexion or not getattr(self.conexion, 'is_open', False):
            self.conectado = False
            return False
        # Si estamos ejecutando una rutina, evitar pings que puedan interferir
        if getattr(self, 'ejecutando_rutina', False):
            self.conectado = True
            return True
        ahora = time.time()
        if (ahora - self._ultimo_ping) < self._intervalo_ping and self.conectado:
            return True  # usar estado reciente solo si seguía conectado
        try:
            # Evitar competir por el puerto mientras se procesa un comando
            if self._cmd_en_progreso:
                return self.conectado
            with self._serial_lock:
                # Usar un ping seguro y verificar respuesta breve
                if self.firmware == 'grbl':
                    self.conexion.write(b"?\n")
                elif self.firmware == 'marlin':
                    self.conexion.write(b"M114\n")  # reporte de posición
                else:
                    self.conexion.write(b"\n")
            # Intentar leer algo durante un corto periodo
            inicio = time.time()
            recibio = False
            while time.time() - inicio < 0.4:
                with self._serial_lock:
                    hay = self.conexion.in_waiting if self.conexion else 0
                if hay:
                    with self._serial_lock:
                        linea = self.conexion.readline().decode(errors='ignore').strip()
                    if linea:
                        if self.firmware == 'grbl':
                            # GRBL responde con línea de estado <...> o ok
                            if linea.startswith('<') or linea.lower().startswith('ok'):
                                recibio = True
                                break
                        elif self.firmware == 'marlin':
                            # Marlin suele responder con posiciones y 'ok'
                            if 'ok' in linea.lower() or 'x:' in linea.lower():
                                recibio = True
                                break
                        else:
                            recibio = True
                            break
                time.sleep(0.05)
            self._ultimo_ping = ahora
            if not recibio:
                # Debounce de fallos de ping: no cerrar el puerto, mantener estado
                self._fallos_ping += 1
                # Solo si hay muchos fallos seguidos, marcar desconexión lógica
                if self._fallos_ping >= 10:
                    self.conectado = False
                    return False
                # Mantener estado anterior y asumir conexión si el puerto sigue abierto
                self.conectado = True
                return True
            # Éxito: resetear contador de fallos
            self._fallos_ping = 0
            return True
        except Exception:
            try:
                self.conexion.close()
            except Exception:
                pass
            self.conectado = False
            return False

    def cargar_velocidad(self):
        """Carga el valor de velocidad desde el archivo temporal."""
        try:
            if os.path.exists(self.archivo_velocidad):
                with open(self.archivo_velocidad, 'r') as f:
                    datos = json.load(f)
                    nueva_velocidad = datos.get('velocidad', 50)
                    if nueva_velocidad != self.velocidad_actual:
                        self.velocidad_actual = nueva_velocidad
                        return True
        except Exception as e:
            print(f"Error al cargar velocidad: {e}")
        return False

    def aplicar_velocidad(self):
        """Aplica la velocidad actual al CNC."""
        # Permitir aplicar si el puerto serie está abierto aunque 'conectado' esté desfasado
        # No modificar la velocidad mientras una rutina esté en ejecución
        if getattr(self, 'ejecutando_rutina', False):
            return False
        try:
            puerto_abierto = bool(self.conexion) and bool(getattr(self.conexion, 'is_open', False))
        except Exception:
            puerto_abierto = False
        if not (self.conectado or puerto_abierto):
            return False
        try:
            # Tratar firmware desconocido como GRBL por defecto para permitir override en la mayoría de controladores
            if self.firmware == 'grbl' or self.firmware == 'desconocido':
                # Ajustar override de feed en GRBL v1.1 con comandos en tiempo real
                objetivo = max(10, min(200, int(self.velocidad_actual)))
                # Limitar rango razonable 10%-200%
                diff = objetivo - self.override_actual
                # Atajo: reset a 100 si cambio grande y objetivo cercano a 100
                if objetivo == 100 and self.override_actual != 100:
                    try:
                        with self._serial_lock:
                            self.conexion.write(b"\x93")  # Reset feed override
                    except Exception:
                        pass
                    self.override_actual = 100
                    return True
                paso10 = 0
                paso1 = 0
                if diff > 0:
                    paso10 = diff // 10
                    paso1 = diff % 10
                    for _ in range(paso10):
                        with self._serial_lock:
                            self.conexion.write(b"\x91")  # +10%
                        time.sleep(0.02)
                    for _ in range(paso1):
                        with self._serial_lock:
                            self.conexion.write(b"\x94")  # +1%
                        time.sleep(0.01)
                elif diff < 0:
                    diff = -diff
                    paso10 = diff // 10
                    paso1 = diff % 10
                    for _ in range(paso10):
                        with self._serial_lock:
                            self.conexion.write(b"\x92")  # -10%
                        time.sleep(0.02)
                    for _ in range(paso1):
                        with self._serial_lock:
                            self.conexion.write(b"\x95")  # -1%
                        time.sleep(0.01)
                self.override_actual = objetivo
                return True
            elif self.firmware == 'marlin':
                # Marlin: M220 Sxx
                comando = f"M220 S{int(self.velocidad_actual)}"
                self.enviar_comando(comando)
                return True
            else:
                # Fallback conservador: intentar patrón GRBL
                objetivo = max(10, min(200, int(self.velocidad_actual)))
                diff = objetivo - self.override_actual
                if objetivo == 100 and self.override_actual != 100:
                    try:
                        with self._serial_lock:
                            self.conexion.write(b"\x93")
                    except Exception:
                        pass
                    self.override_actual = 100
                    return True
                if diff != 0:
                    if diff > 0:
                        paso10 = diff // 10
                        paso1 = diff % 10
                        for _ in range(paso10):
                            with self._serial_lock:
                                self.conexion.write(b"\x91")
                            time.sleep(0.02)
                        for _ in range(paso1):
                            with self._serial_lock:
                                self.conexion.write(b"\x94")
                            time.sleep(0.01)
                    else:
                        diff = -diff
                        paso10 = diff // 10
                        paso1 = diff % 10
                        for _ in range(paso10):
                            with self._serial_lock:
                                self.conexion.write(b"\x92")
                            time.sleep(0.02)
                        for _ in range(paso1):
                            with self._serial_lock:
                                self.conexion.write(b"\x95")
                            time.sleep(0.01)
                    self.override_actual = objetivo
                    return True
        except Exception as e:
            print(f"Error aplicando velocidad: {e}")
            return False
        return False

    # --- Estado GRBL: parseo y consulta ligera ---
    def _parsear_estado_grbl(self, linea: str):
        """Parsea una línea de estado de GRBL (<...>) para extraer Ov y F/FS.
        Actualiza self.ov_feed, self.ov_rapid, self.ov_spindle y self.feed_reportado.
        """
        try:
            if not linea or not linea.startswith('<'):
                return
            # Ejemplos:
            # <Run|MPos:0.000,0.000,0.000|FS:500,0|Ov:120,100,100>
            # <Idle|WPos:..|F:600|Ov:100,100,100>
            parts = linea.strip('<>').split('|')
            for p in parts:
                if p.startswith('Ov:'):
                    try:
                        vals = p[3:].split(',')
                        if len(vals) >= 3:
                            self.ov_feed = int(float(vals[0]))
                            self.ov_rapid = int(float(vals[1]))
                            self.ov_spindle = int(float(vals[2]))
                            # Mantener override_actual alineado al estado real reportado por GRBL
                            try:
                                if 0 < self.ov_feed <= 250:
                                    self.override_actual = int(self.ov_feed)
                            except Exception:
                                pass
                    except Exception:
                        pass
                elif p.startswith('FS:'):
                    try:
                        vals = p[3:].split(',')
                        if vals:
                            self.feed_reportado = float(vals[0])
                    except Exception:
                        pass
                elif p.startswith('F:'):
                    try:
                        self.feed_reportado = float(p[2:])
                    except Exception:
                        pass
        except Exception:
            pass

    def obtener_estado_velocidad(self):
        """Consulta (ligero) el estado para conocer override y feed actuales en GRBL.
        Devuelve (ov_feed:int, feed_reportado:float|0).
        """
        try:
            firmware_tipo = getattr(self, 'firmware', 'desconocido')
            
            if self.firmware != 'grbl':
                # Para firmware no-GRBL, usar override_actual si ejecutando rutina
                # Si no, usar velocidad_actual para reflejar el slider
                if getattr(self, 'ejecutando_rutina', False):
                    try:
                        ov = int(getattr(self, 'override_actual', 100))
                    except Exception:
                        ov = 100
                else:
                    try:
                        ov = int(getattr(self, 'velocidad_actual', 100))
                    except Exception:
                        ov = 100
                f = getattr(self, 'feed_reportado', 0.0)
                return ov, f
            
            # Para GRBL, usar lógica original
            ov = self.ov_feed if isinstance(getattr(self, 'ov_feed', None), int) else 0
            f = self.feed_reportado
            ahora = time.time()
            if (ahora - self._last_status_poll) < self._status_poll_interval:
                return ov, f
            self._last_status_poll = ahora
            # Enviar '?' y leer brevemente
            with self._serial_lock:
                if self.conexion and getattr(self.conexion, 'is_open', False):
                    self.conexion.write(b"?\n")
            time.sleep(0.03)
            limite = time.time() + 0.08
            while time.time() < limite:
                with self._serial_lock:
                    if not (self.conexion and self.conexion.in_waiting):
                        break
                    linea = self.conexion.readline().decode(errors='ignore').strip()
                if linea:
                    self._parsear_estado_grbl(linea)
            # Fallback a override_actual si GRBL no reporta Ov
            ov_local = self.ov_feed
            if not ov_local:
                try:
                    ov_local = int(getattr(self, 'override_actual', 0))
                except Exception:
                    ov_local = 0
            return ov_local, self.feed_reportado
        except Exception as e:
            # En caso de error, devolver velocidad_actual si no está ejecutando rutina
            if getattr(self, 'ejecutando_rutina', False):
                try:
                    ov = int(getattr(self, 'override_actual', 100))
                except Exception:
                    ov = 100
            else:
                try:
                    ov = int(getattr(self, 'velocidad_actual', 100))
                except Exception:
                    ov = 100
            f = getattr(self, 'feed_reportado', 0.0)
            return ov, f

    # --- Respaldo y restauración de configuración ($$) ---
    def guardar_configuracion_grbl(self, ruta: str | None = None):
        """Solicita $$ y guarda la configuración de GRBL en un archivo JSON.
        Si ruta no se especifica, crea un nombre con timestamp y además actualiza grbl_backup_last.json.
        Devuelve (ok: bool, mensaje_ruta_o_error: str)
        """
        try:
            if not (self.conectado and self.firmware == 'grbl' and self.conexion and self.conexion.is_open):
                return False, "CNC no conectada o firmware no es GRBL"
            # Limpiar buffer y pedir $$
            with self._serial_lock:
                try:
                    self.conexion.reset_input_buffer()
                except Exception:
                    pass
                self.conexion.write(b"$$\n")
            lineas = []
            limite = time.time() + 2.0
            while time.time() < limite:
                with self._serial_lock:
                    hay = self.conexion.in_waiting if self.conexion else 0
                if hay:
                    with self._serial_lock:
                        l = self.conexion.readline().decode(errors='ignore').strip()
                    if l:
                        # Termina con ok
                        if l.lower() == 'ok':
                            break
                        lineas.append(l)
                else:
                    time.sleep(0.02)
            # Parsear parámetros $n=v (desc)
            params = {}
            for l in lineas:
                if not l.startswith('$'):
                    continue
                try:
                    s = l.split('(')[0].strip()
                    if '=' in s:
                        k, v = s.split('=', 1)
                        k = k.lstrip('$').strip()
                        v = v.strip()
                        if k.isdigit():
                            params[k] = v
                except Exception:
                    continue
            if not params:
                return False, "No se pudo leer configuración $$"
            data = {
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'puerto': self.puerto,
                'firmware': self.firmware_info or self.firmware,
                'raw': lineas,
                'params': params,
            }
            # Ruta de salida
            try:
                os.makedirs(BASE_DIR, exist_ok=True)
            except Exception:
                pass
            if not ruta:
                stamp = time.strftime("%Y%m%d-%H%M%S")
                ruta = os.path.join(BASE_DIR, f"grbl_backup_{stamp}.json")
            with open(ruta, 'w') as f:
                json.dump(data, f, indent=2)
            # También actualizar puntero al último respaldo
            try:
                ruta_last = os.path.join(BASE_DIR, 'grbl_backup_last.json')
                with open(ruta_last, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass
            return True, ruta
        except Exception as e:
            return False, f"Error guardando $$: {e}"

    def restablecer_configuracion_grbl(self, ruta: str | None = None):
        """Lee un archivo JSON de respaldo y aplica los parámetros $n=v a GRBL.
        Si ruta es None, usa grbl_backup_last.json. Devuelve (ok, mensaje_detalle).
        """
        try:
            if not (self.conectado and self.firmware == 'grbl' and self.conexion and self.conexion.is_open):
                return False, "CNC no conectada o firmware no es GRBL"
            if not ruta:
                ruta = os.path.join(BASE_DIR, 'grbl_backup_last.json')
            if not os.path.exists(ruta):
                # Buscar el más reciente grbl_backup_*.json
                candidatos = [p for p in os.listdir(BASE_DIR) if p.startswith('grbl_backup_') and p.endswith('.json')]
                if candidatos:
                    candidatos.sort(reverse=True)
                    ruta = os.path.join(BASE_DIR, candidatos[0])
                else:
                    return False, "No hay respaldos para restaurar"
            with open(ruta, 'r') as f:
                data = json.load(f)
            params = (data or {}).get('params') or {}
            if not params:
                return False, "Respaldo inválido (sin params)"
            enviados = 0
            ok_count = 0
            for k, v in params.items():
                cmd = f"${k}={v}"
                enviados += 1
                try:
                    if self.enviar_comando(cmd):
                        ok_count += 1
                except Exception:
                    pass
                time.sleep(0.03)
            return True, f"Aplicados {ok_count}/{enviados} parámetros desde {os.path.basename(ruta)}"
        except Exception as e:
            return False, f"Error restaurando $$: {e}"
            
    def verificar_cambios_velocidad(self):
        """Verifica si hay cambios en el archivo de velocidad y los aplica."""
        tiempo_actual = time.time()
        if tiempo_actual - self.ultimo_tiempo_verificacion >= self.intervalo_verificacion:
            self.ultimo_tiempo_verificacion = tiempo_actual
            # Durante ejecución de rutina, verificar si velocidad_actual difiere de override_actual
            if getattr(self, 'ejecutando_rutina', False):
                objetivo = max(10, min(200, int(self.velocidad_actual)))
                if objetivo != self.override_actual:
                    try:
                        if self.firmware == 'grbl' or self.firmware == 'desconocido':
                            diff = objetivo - self.override_actual
                            if diff > 0:
                                paso10 = diff // 10
                                paso1 = diff % 10
                                for _ in range(paso10):
                                    with self._serial_lock:
                                        if self.conexion and getattr(self.conexion, 'is_open', False):
                                            self.conexion.write(b"\x91")  # +10%
                                    time.sleep(0.01)
                                for _ in range(paso1):
                                    with self._serial_lock:
                                        if self.conexion and getattr(self.conexion, 'is_open', False):
                                            self.conexion.write(b"\x94")  # +1%
                                    time.sleep(0.005)
                            elif diff < 0:
                                diff = -diff
                                paso10 = diff // 10
                                paso1 = diff % 10
                                for _ in range(paso10):
                                    with self._serial_lock:
                                        if self.conexion and getattr(self.conexion, 'is_open', False):
                                            self.conexion.write(b"\x92")  # -10%
                                    time.sleep(0.01)
                                for _ in range(paso1):
                                    with self._serial_lock:
                                        if self.conexion and getattr(self.conexion, 'is_open', False):
                                            self.conexion.write(b"\x95")  # -1%
                                    time.sleep(0.005)
                            self.override_actual = objetivo
                            return True, self.velocidad_actual
                        elif self.firmware == 'marlin':
                            comando = f"M220 S{int(self.velocidad_actual)}"
                            self.enviar_comando(comando)
                            self.override_actual = objetivo
                            return True, self.velocidad_actual
                    except Exception as e:
                        print(f"Error aplicando velocidad durante rutina: {e}")
                return False, self.velocidad_actual
            # Fuera de rutina, usar cargar_velocidad y aplicar_velocidad
            if self.cargar_velocidad():
                return self.aplicar_velocidad(), self.velocidad_actual
        return False, self.velocidad_actual

    def guardar_posicion(self, forzar=False):
        """Guarda la posición actual en un archivo de texto."""
        tiempo_actual = time.time()
        if forzar or (tiempo_actual - self.ultimo_guardado >= INTERVALO_GUARDADO):
            self.ultimo_guardado = tiempo_actual
            try:
                with open(os.path.join(BASE_DIR, 'save.txt'), 'w') as f:
                    f.write(f"{self.posicion_x},{self.posicion_y}")
                print(f"Posición guardada: X={self.posicion_x}, Y={self.posicion_y}")
                return True
            except Exception as e:
                print(f"Error al guardar posición: {e}")
        return False

    def cargar_posicion(self):
        """Carga la última posición guardada desde el archivo."""
        try:
            save_path = os.path.join(BASE_DIR, 'save.txt')
            if os.path.exists(save_path):
                with open(save_path, 'r') as f:
                    contenido = f.read().strip()
                    if ',' in contenido:
                        x, y = map(float, contenido.split(','))
                        return x, y
        except Exception as e:
            print(f"Error al cargar posición: {e}")
        return None, None

    def establecer_posicion_guardada(self):
        """Establece el origen en la última posición guardada."""
        x, y = self.cargar_posicion()
        if x is not None and y is not None:
            dx = x - self.posicion_x
            dy = y - self.posicion_y
            
            comando = f"G92 X{x} Y{y}"
            if self.enviar_comando(comando):
                self.posicion_x = x
                self.posicion_y = y
                return True
        return False




    def _leer_status_line(self, timeout: float = 0.2) -> str:
        """Envía '?' y devuelve una línea de estado <...> si se recibe dentro del timeout."""
        if not (self.conectado and self.conexion and self.conexion.is_open):
            return ""
        try:
            with self._serial_lock:
                self.conexion.write(b"?\n")
            fin = time.time() + timeout
            while time.time() < fin:
                with self._serial_lock:
                    hay = self.conexion.in_waiting if self.conexion else 0
                if hay:
                    with self._serial_lock:
                        linea = self.conexion.readline().decode(errors='ignore').strip()
                    if linea.startswith('<'):
                        return linea
                time.sleep(0.02)
        except Exception:
            return ""
        return ""

    def _publicar_evento(self, tipo: str, datos: dict | None = None):
        try:
            with self._event_lock:
                self._eventos.append({'tipo': tipo, 'datos': datos or {}, 'ts': time.time()})
        except Exception:
            pass

    def consumir_eventos(self) -> list:
        try:
            with self._event_lock:
                evs = list(self._eventos)
                self._eventos.clear()
                return evs
        except Exception:
            return []
            
    def enviar_comando(self, comando):
        # Control extra: asegurar que _cmd_en_progreso nunca quede activado indefinidamente
        self.set_cmd_en_progreso(True)
        try:
            if not self.conectado:
                if self.conexion and getattr(self.conexion, 'is_open', False):
                    self.conectado = True
                else:
                    self.set_cmd_en_progreso(False)
                    return False
            comando = comando.strip() + "\n"
            # Control de modos G90/G91 si vienen en el comando
            try:
                tokens = comando.strip().split()
                if any(t.upper() == 'G91' for t in tokens):
                    self.modo_relativo = True
                elif any(t.upper() == 'G90' for t in tokens):
                    self.modo_relativo = False
            except Exception:
                pass
            # Enforce soft-limits si origen establecido y límites activos, solo para G0/G1 (sin inversiones)
            try:
                if not self._movimiento_permitido(comando):
                    self.set_cmd_en_progreso(False)
                    return False
            except Exception:
                pass
            with self._serial_lock:
                self.conexion.write(comando.encode())
            # Leer hasta 'ok' o agotar timeout
            respuesta = ""
            ok_recibido = False
            alarm_detectada = False
            inicio = time.time()
            while time.time() - inicio < 1.5:
                with self._serial_lock:
                    linea = self.conexion.readline().decode(errors='ignore').strip()
                if not linea:
                    continue
                respuesta = linea
                # Detección de alarmas o límites duros
                lcl = linea.lower()
                if lcl.startswith('alarm') or 'hard limit' in lcl or ('alarm' in lcl and '<' not in linea):
                    alarm_detectada = True
                    break
                if linea.lower().startswith('ok') or 'ok' == linea.lower():
                    ok_recibido = True
                    break
            print(f"Enviado: {comando.strip()}, Respuesta: {respuesta}")
            if alarm_detectada or '[MSG:Reset to continue]' in respuesta:
                print("[ALARM] Detectada. Enviando $X para desbloquear GRBL.")
                with self._serial_lock:
                    self.conexion.write(b'$X\n')
                # Leer respuesta de desbloqueo
                time.sleep(0.2)
                try:
                    linea = self.conexion.readline().decode(errors='ignore').strip()
                    print(f"Respuesta a $X: {linea}")
                except Exception:
                    pass
            if ok_recibido and (comando.startswith("G0") or comando.startswith("G1")):
                self.actualizar_posicion(comando)
            return ok_recibido
        except (OSError, IOError) as e:
            # Error de I/O: probablemente se desconectó el Arduino
            print(f"Error de I/O al enviar comando: {e}")
            self.conectado = False
            try:
                if self.conexion:
                    self.conexion.close()
            except:
                pass
            return False
        except Exception as e:
            print(f"Error al enviar comando: {e}")
            return False
        finally:
            # Bloque finally vacío, ya no se usa _cmd_en_progreso
            pass

    def _movimiento_permitido(self, cmd: str) -> bool:
        """Valida que un comando G0/G1 no salga de los límites lógicos [-20..20]."""
        try:
            cmd_str = cmd.strip()
            if not (self.origen_establecido and self.limites_activos):
                return True
            if not (cmd_str.upper().startswith('G0') or cmd_str.upper().startswith('G1')):
                return True
            objetivo_x = self.posicion_x
            objetivo_y = self.posicion_y
            x_presente = False
            y_presente = False
            for parte in cmd_str.split():
                up = parte.upper()
                if up.startswith('X'):
                    x_presente = True
                    try:
                        val = float(parte[1:])
                    except Exception:
                        val = 0.0
                    if self.modo_relativo:
                        objetivo_x = self.posicion_x + val
                    else:
                        objetivo_x = val
                elif up.startswith('Y'):
                    y_presente = True
                    try:
                        val = float(parte[1:])
                    except Exception:
                        val = 0.0
                    if self.modo_relativo:
                        objetivo_y = self.posicion_y + val
                    else:
                        objetivo_y = val
            lim_x_min = self.limite_x_min
            lim_x_max = self.limite_x_max
            lim_y_min = self.limite_y_min
            lim_y_max = self.limite_y_max
            check_x = objetivo_x
            check_y = objetivo_y
            violacion = False
            detalles = []
            if x_presente and (check_x < lim_x_min or check_x > lim_x_max):
                violacion = True
                detalles.append(f"X={check_x:.2f} fuera de [{lim_x_min:.2f}, {lim_x_max:.2f}]")
            if y_presente and (check_y < lim_y_min or check_y > lim_y_max):
                violacion = True
                detalles.append(f"Y={check_y:.2f} fuera de [{lim_y_min:.2f}, {lim_y_max:.2f}]")
            if violacion:
                msg = "Movimiento bloqueado por límites: " + "; ".join(detalles)
                self.ultimo_limite = msg
                if self.debug_limites:
                    print(msg)
                return False
            return True
        except Exception:
            return True

    def _write_line_fast(self, linea: str) -> bool:
        """Escribe una línea al puerto sin esperar 'ok'."""
        try:
            if not (self.conectado and self.conexion and getattr(self.conexion, 'is_open', False)):
                return False
            with self._serial_lock:
                self.conexion.write((linea.strip() + "\n").encode())
            return True
        except (OSError, IOError) as e:
            # Error de I/O: probablemente se desconectó el Arduino
            print(f"Error de I/O en _write_line_fast: {e}")
            self.conectado = False
            try:
                if self.conexion:
                    self.conexion.close()
            except:
                pass
            return False
        except Exception as e:
            print(f"Error en _write_line_fast: {e}")
            return False

    def _drain_ok_nonblock(self, max_ms: float = 60.0) -> int:
        """Lee respuestas disponibles sin bloquear mucho tiempo. Devuelve cuántos 'ok' se leyeron."""
        if not (self.conectado and self.conexion and getattr(self.conexion, 'is_open', False)):
            return 0
        ok_count = 0
        fin = time.time() + (max_ms / 1000.0)
        while time.time() < fin:
            try:
                with self._serial_lock:
                    hay = self.conexion.in_waiting if self.conexion else 0
            except Exception:
                hay = 0
            if hay <= 0:
                time.sleep(0.002)
                continue
            try:
                with self._serial_lock:
                    linea = self.conexion.readline().decode(errors='ignore').strip()
            except Exception:
                linea = ''
            if not linea:
                continue
            if linea.lower().startswith('ok') or ' ok' in linea.lower():
                ok_count += 1
        return ok_count

    def paro_emergencia(self):
        """Detiene la máquina preservando el origen (sin reset de GRBL).
        Enviar '!' (Feed Hold) como comando en tiempo real y cancelar jog (0x85) si aplica.
        """
        if not (self.conectado and self.conexion and self.conexion.is_open):
            print("paro_emergencia(): No hay conexión activa")
            return False
        try:
            # Feed hold: pausa segura sin perder G92 ni offsets
            with self._serial_lock:
                self.conexion.write(b"!")
            # Si estuviera en jogging, enviar cancel (0x85)
            try:
                with self._serial_lock:
                    self.conexion.write(b"\x85")
            except Exception:
                pass
            print("Paro de emergencia enviado: Feed Hold ('!') + Cancel Jog (0x85)")
            self.en_hold = True
            return True
        except Exception as e:
            print(f"Error en paro_emergencia(): {e}")
            return False

    def reanudar_movimiento(self):
        """Reanuda el movimiento después de un Feed Hold enviando '~' (Cycle Start)."""
        if not (self.conectado and self.conexion and self.conexion.is_open):
            print("reanudar_movimiento(): No hay conexión activa")
            return False
        try:
            with self._serial_lock:
                self.conexion.write(b"~")
            self.en_hold = False
            print("Reanudar enviado: '~' (Cycle Start)")
            return True
        except Exception as e:
            print(f"Error en reanudar_movimiento(): {e}")
            return False
            
    def actualizar_posicion(self, comando):
        partes = comando.split()
        dx_calc = None
        dy_calc = None
        for parte in partes:
            if parte.startswith("X"):
                try:
                    val = float(parte[1:])
                    if self.modo_relativo:
                        self.posicion_x += val
                        dx_calc = val
                    else:
                        dx_calc = val - self.posicion_x
                        self.posicion_x = val
                except ValueError:
                    pass
            elif parte.startswith("Y"):
                try:
                    val = float(parte[1:])
                    if self.modo_relativo:
                        self.posicion_y += val
                        dy_calc = val
                    else:
                        dy_calc = val - self.posicion_y
                        self.posicion_y = val
                except ValueError:
                    pass
        try:
            if dx_calc is not None and dx_calc != 0:
                self._ultimo_dir_x = 1.0 if dx_calc > 0 else -1.0
            if dy_calc is not None and dy_calc != 0:
                self._ultimo_dir_y = 1.0 if dy_calc > 0 else -1.0
        except Exception:
            pass
        
    def mover(self, direccion_x=0, direccion_y=0):
        """
        Mueve el CNC en modo relativo.
        Construye correctamente comandos GRBL solo con ejes que se mueven y coord. [-20..20] desde el origen.
        """
        if not self.conectado:
            print("mover(): No hay conexión activa")
            return False
        if getattr(self, 'abortado_por_limite', False) or getattr(self, 'en_hold', False):
            print("mover(): Bloqueado por activación de límite o hold")
            return False
        if direccion_x == 0 and direccion_y == 0:
            print("mover(): Sin movimiento (ambos ejes en 0)")
            return False
        # Validación de límites suaves si están activos y se ha establecido el origen
        if self.origen_establecido and self.limites_activos:
            # Calcular posición futura física en el mismo espacio [-20..20] desde el origen
            futuro_x = self.posicion_x
            futuro_y = self.posicion_y
            if direccion_x != 0:
                futuro_x += direccion_x * self.paso
            if direccion_y != 0:
                futuro_y += direccion_y * self.paso
            lim_x_min = self.limite_x_min
            lim_x_max = self.limite_x_max
            lim_y_min = self.limite_y_min
            lim_y_max = self.limite_y_max
            if (
                futuro_x < lim_x_min or futuro_x > lim_x_max or
                futuro_y < lim_y_min or futuro_y > lim_y_max
            ):
                print("mover(): Movimiento bloqueado por límites suaves")
                # No mostrar popup modal; sólo cancelar la acción
                return False
        
        self.enviar_comando("G91")
        self.modo_relativo = True
        
        partes_comando = ["G0"]
        
        if direccion_x != 0:
            desplazamiento_x = direccion_x * self.paso
            partes_comando.append(f"X{desplazamiento_x}")
            print(f"Movimiento en X: {desplazamiento_x}")
        
        if direccion_y != 0:
            desplazamiento_y = direccion_y * self.paso
            partes_comando.append(f"Y{desplazamiento_y}")
            print(f"Movimiento en Y: {desplazamiento_y}")
        
        comando = " ".join(partes_comando)
        print(f"Comando GRBL generado: {comando}")
        
        resultado = self.enviar_comando(comando)
        if not resultado:
            print("[PARO DE EMERGENCIA] Fallo al enviar comando de movimiento")
            self.paro_emergencia()
        self.enviar_comando("G90")
        self.modo_relativo = False
        return resultado
        
    def ir_a_home(self):
        if not self.conectado:
            print("ir_a_home(): No hay conexión activa")
            return False
        self.enviar_comando("G90")
        self.modo_relativo = False
        resultado = self.enviar_comando("G0 X0 Y0")
        if resultado:
            self.posicion_x = self.posicion_y = 0.0
            # No cambies origen_establecido aquí; Home no crea G92
        return resultado
        
    def establecer_origen(self):
        if not self.conectado:
            print("establecer_origen(): No hay conexión activa")
            return False
        resultado = self.enviar_comando("G92 X0 Y0")
        if resultado:
            self.posicion_x = self.posicion_y = 0.0
            self.guardar_posicion(forzar=True)
            self.origen_establecido = True
            # Activar límites estándar lógicos [-20..20] al fijar origen
            try:
                self.activar_limites_estandar()
            except Exception:
                self.limites_activos = True
        return resultado

    def activar_limites_estandar(self, xmin: float = -20.0, ymin: float = -20.0, xmax: float = 20.0, ymax: float = 20.0):
        """Activa límites lógicos relativos al origen en el rango [-20..20] por eje."""
        self.limite_x_min = float(xmin)
        self.limite_y_min = float(ymin)
        self.limite_x_max = float(xmax)
        self.limite_y_max = float(ymax)
        self.limites_activos = True

    def obtener_posicion_logica(self):
        """Devuelve (X, Y) en [-20..20] desde el punto de origen establecido (sin inversión).
        Si no hay límites activos/origen, devuelve la posición actual.
        """
        try:
            if not getattr(self, 'origen_establecido', False) or not getattr(self, 'limites_activos', False):
                return float(self.posicion_x), float(self.posicion_y)
            lim_x_min = float(getattr(self, 'limite_x_min', -20.0) or -20.0)
            lim_x_max = float(getattr(self, 'limite_x_max', 20.0) or 20.0)
            lim_y_min = float(getattr(self, 'limite_y_min', -20.0) or -20.0)
            lim_y_max = float(getattr(self, 'limite_y_max', 20.0) or 20.0)
            x_log = max(lim_x_min, min(lim_x_max, float(self.posicion_x)))
            y_log = max(lim_y_min, min(lim_y_max, float(self.posicion_y)))
            return x_log, y_log
            return x_log, y_log
        except Exception:
            # Fallback seguro
            return float(self.posicion_x), float(self.posicion_y)
        
    def _invertir_linea_abs(self, linea: str, lim_max: float = 40.0) -> str:
        """Invierte la coordenada X en modo absoluto (para sistema centrado en 0).
        Para coordenadas centradas [-20, 20]: X_invertido = -X
        """
        try:
            # Buscar coordenada X en la línea
            partes = linea.split()
            nueva_linea = []
            
            for parte in partes:
                if parte.upper().startswith('X'):
                    try:
                        # Extraer el valor de X
                        x_str = parte[1:]  # Quitar la 'X'
                        x_val = float(x_str)
                        # Invertir: X_nuevo = -X_original
                        x_invertido = -x_val
                        # Reemplazar con el valor invertido
                        nueva_linea.append(f'X{x_invertido:.3f}')
                    except ValueError:
                        # Si no se puede convertir, dejar como está
                        nueva_linea.append(parte)
                else:
                    nueva_linea.append(parte)
            
            return ' '.join(nueva_linea)
        except Exception as e:
            print(f"Error al invertir línea absoluta: {e}")
            return linea

    def _invertir_linea_rel(self, linea: str) -> str:
        """Invierte la coordenada X en modo relativo.
        Para movimientos relativos: X_invertido = -X
        """
        try:
            # Buscar coordenada X en la línea
            partes = linea.split()
            nueva_linea = []
            
            for parte in partes:
                if parte.upper().startswith('X'):
                    try:
                        # Extraer el valor de X
                        x_str = parte[1:]  # Quitar la 'X'
                        x_val = float(x_str)
                        # Invertir: X_nuevo = -X_original
                        x_invertido = -x_val
                        # Reemplazar con el valor invertido
                        nueva_linea.append(f'X{x_invertido:.3f}')
                    except ValueError:
                        # Si no se puede convertir, dejar como está
                        nueva_linea.append(parte)
                else:
                    nueva_linea.append(parte)
            
            return ' '.join(nueva_linea)
        except Exception as e:
            print(f"Error al invertir línea relativa: {e}")
            return linea

    def ejecutar_archivo_gcode(self, ruta_archivo, base_tiempo=1, es_rutina_1_1=False, invert: bool = False):
        if not self.conectado:
            print("ejecutar_archivo_gcode(): No hay conexión con el Arduino")
            return False
        # Guardar: no ejecutar rutinas si no se ha establecido el origen
        if not getattr(self, 'origen_establecido', False):
            print("ejecutar_archivo_gcode(): Bloqueado. Aún no se ha establecido Punto de Origen (G92)")
            try:
                mostrar_aviso_sistema("Aviso", "Aún no se ha establecido Punto de Origen")
            except Exception:
                pass
            return False
        try:
            self.ejecutando_rutina = True
            # Ir al punto de origen antes de comenzar la rutina
            try:
                self.enviar_comando("G90")
                self.enviar_comando("G0 X0 Y0")
                # Asegurar feed definido para G1
                try:
                    self.enviar_comando(f"G1 F{int(self.feed_base)}")
                except Exception:
                    pass
            except Exception:
                pass
            with open(ruta_archivo, 'r') as archivo:
                crudas = archivo.readlines()
                lineas = []
                for l in crudas:
                    s = limpiar_linea_gcode(l)
                    if s:
                        lineas.append(s)
            linea_actual = circulo_actual = 0
            # Seguir modo para invertir solo en absolutas
            absoluto = True
            inflight = 0
            ventana = 12
            for linea in lineas:
                if getattr(self, 'abortado_por_limite', False):
                    print("Ejecución abortada por límite")
                    break
                # Pausa reactiva si hay feed hold activo
                while getattr(self, 'en_hold', False):
                    time.sleep(0.05)
                # Aplicar cambios de velocidad ocasionalmente
                if (linea_actual % 5) == 0:
                    self.verificar_cambios_velocidad()
                
                linea_actual += 1
                if es_rutina_1_1 and ("G2" in linea or "G3" in linea):
                    circulo_actual += 1
                token0 = linea.split()[0] if linea else ""
                if token0.upper() == 'G90':
                    absoluto = True
                elif token0.upper() == 'G91':
                    absoluto = False
                to_send = linea
                if invert and (token0.upper() in ('G0', 'G1')):
                    if absoluto:
                        to_send = self._invertir_linea_abs(linea)
                    else:
                        to_send = self._invertir_linea_rel(linea)
                if token0.upper() == 'G1':
                    # Extraer feed rate si está presente en el comando
                    try:
                        import re
                        match = re.search(r'F([\d.]+)', to_send, re.IGNORECASE)
                        if match:
                            self.feed_reportado = float(match.group(1))
                    except Exception:
                        pass
                    if self._write_line_fast(to_send):
                        inflight += 1
                    if inflight >= ventana:
                        okc = self._drain_ok_nonblock(80)
                        if okc:
                            inflight = max(0, inflight - okc)
                else:
                    # Antes de comandos bloqueantes, drenar pendientes
                    if inflight > 0:
                        tlim = time.time() + 1.0
                        while inflight > 0 and time.time() < tlim:
                            okc = self._drain_ok_nonblock(80)
                            if okc:
                                inflight = max(0, inflight - okc)
                            else:
                                time.sleep(0.01)
                    self.enviar_comando(to_send)
                if (linea_actual % 10) == 0:
                    self.guardar_posicion()
            # Regresar al punto de origen al finalizar la rutina
            try:
                # Drenar 'ok' pendientes
                if inflight > 0:
                    tlim = time.time() + 2.0
                    while inflight > 0 and time.time() < tlim:
                        okc = self._drain_ok_nonblock(120)
                        if okc:
                            inflight = max(0, inflight - okc)
                        else:
                            time.sleep(0.01)
                self.enviar_comando("G90")
                self.enviar_comando("G0 X0 Y0")
            except Exception:
                pass
            return False if getattr(self, 'abortado_por_limite', False) else True
        except Exception as e:
            print(f"Error al ejecutar archivo G-code: {e}")
            return False
        finally:
            self.ejecutando_rutina = False

    def ejecutar_lineas_gcode(self, lineas, base_tiempo=0.5, invert: bool = False):
        """Ejecuta una lista de líneas G-code en memoria.
        Respeta el override de velocidad (M220) y verifica cambios en tiempo real.
        Aplica guard de origen.
        """
        if not self.conectado:
            print("ejecutar_lineas_gcode(): No hay conexión con el Arduino")
            return False
        if not getattr(self, 'origen_establecido', False):
            print("ejecutar_lineas_gcode(): Bloqueado. Aún no se ha establecido Punto de Origen (G92)")
            try:
                mostrar_aviso_sistema("Aviso", "Aún no se ha establecido Punto de Origen")
            except Exception:
                pass
            return False
        try:
            self.ejecutando_rutina = True
            # Ir al punto de origen antes de comenzar la rutina
            try:
                self.enviar_comando("G90")
                self.enviar_comando("G0 X0 Y0")
                # Asegurar feed definido para G1
                try:
                    self.enviar_comando(f"G1 F{int(self.feed_base)}")
                except Exception:
                    pass
            except Exception:
                pass
            linea_actual = 0
            absoluto = True
            inflight = 0
            ventana = 12
            for raw in lineas:
                if getattr(self, 'abortado_por_limite', False):
                    print("Ejecución (memoria) abortada por límite")
                    break
                linea = limpiar_linea_gcode(raw)
                if not linea:
                    continue
                # Pausa reactiva si hay feed hold activo
                while getattr(self, 'en_hold', False):
                    time.sleep(0.05)
                if (linea_actual % 5) == 0:
                    self.verificar_cambios_velocidad()
                linea_actual += 1
                token0 = linea.split()[0] if linea else ""
                if token0.upper() == 'G90':
                    absoluto = True
                elif token0.upper() == 'G91':
                    absoluto = False
                to_send = linea
                if invert and (token0.upper() in ('G0', 'G1')):
                    if absoluto:
                        to_send = self._invertir_linea_abs(linea)
                    else:
                        to_send = self._invertir_linea_rel(linea)
                if token0.upper() == 'G1':
                    # Extraer feed rate si está presente en el comando
                    try:
                        import re
                        match = re.search(r'F([\d.]+)', to_send, re.IGNORECASE)
                        if match:
                            self.feed_reportado = float(match.group(1))
                    except Exception:
                        pass
                    if self._write_line_fast(to_send):
                        inflight += 1
                    if inflight >= ventana:
                        okc = self._drain_ok_nonblock(80)
                        if okc:
                            inflight = max(0, inflight - okc)
                else:
                    if inflight > 0:
                        tlim = time.time() + 1.0
                        while inflight > 0 and time.time() < tlim:
                            okc = self._drain_ok_nonblock(80)
                            if okc:
                                inflight = max(0, inflight - okc)
                            else:
                                time.sleep(0.01)
                    self.enviar_comando(to_send)
                if (linea_actual % 10) == 0:
                    self.guardar_posicion()
            # Regresar al punto de origen al finalizar la rutina
            try:
                if inflight > 0:
                    tlim = time.time() + 2.0
                    while inflight > 0 and time.time() < tlim:
                        okc = self._drain_ok_nonblock(120)
                        if okc:
                            inflight = max(0, inflight - okc)
                        else:
                            time.sleep(0.01)
                self.enviar_comando("G90")
                self.enviar_comando("G0 X0 Y0")
            except Exception:
                pass
            return False if getattr(self, 'abortado_por_limite', False) else True
        except Exception as e:
            print(f"Error al ejecutar G-code en memoria: {e}")
            return False
        finally:
            self.ejecutando_rutina = False

class Boton:
    def __init__(self, x, y, ancho, alto, texto, color=VERDE_CLARO, fuente_personalizada=None, texto_color=BLANCO):
        self.rect = pygame.Rect(x, y, ancho, alto)
        self.texto = texto
        self.color = color
        self.color_hover = AZUL
        self.texto_color = texto_color
        self.activo = False
        self.fuente_personalizada = fuente_personalizada
        self.proporcion_x = 0  # Para redimensionamiento
        self.proporcion_y = 0  # Para redimensionamiento
        self.proporcion_ancho = 0  # Para redimensionamiento
        self.proporcion_alto = 0  # Para redimensionamiento
        
    def actualizar_proporciones(self, ancho_ventana, alto_ventana):
        """Actualiza las proporciones del botón respecto al tamaño de la ventana."""
        self.proporcion_x = self.rect.x / ancho_ventana
        self.proporcion_y = self.rect.y / alto_ventana
        self.proporcion_ancho = self.rect.width / ancho_ventana
        self.proporcion_alto = self.rect.height / alto_ventana
        
    def redimensionar(self, ancho_ventana, alto_ventana):
        """Redimensiona el botón según el nuevo tamaño de la ventana."""
        if self.proporcion_x > 0:  # Solo si ya se han calculado las proporciones
            nuevo_x = int(self.proporcion_x * ancho_ventana)
            nuevo_y = int(self.proporcion_y * alto_ventana)
            nuevo_ancho = int(self.proporcion_ancho * ancho_ventana)
            nuevo_alto = int(self.proporcion_alto * alto_ventana)
            self.rect = pygame.Rect(nuevo_x, nuevo_y, nuevo_ancho, nuevo_alto)
        
    def dibujar(self, superficie):
        color_actual = self.color_hover if self.activo else self.color
        pygame.draw.rect(superficie, color_actual, self.rect)
        pygame.draw.rect(superficie, VERDE_BORDE, self.rect, 2)
        
        # Calcular el mejor color de texto basado en el color del botón
        def calcular_luminancia(color):
            r, g, b = color[:3]  # En caso de que el color tenga alpha
            return (0.299 * r + 0.587 * g + 0.114 * b) / 255
        
        luminancia = calcular_luminancia(color_actual)
        color_texto_optimo = NEGRO if luminancia > 0.5 else BLANCO
        color_texto_final = self.texto_color if hasattr(self, '_color_personalizado') else color_texto_optimo
        
        # Ajustar tamaño de fuente según el tamaño del botón
        tamano_fuente = min(30, max(12, int(self.rect.width / 10)))
        fuente = self.fuente_personalizada or pygame.font.Font(None, tamano_fuente)
        
        # Dividir el texto en palabras para ajustarlo al botón
        palabras = self.texto.split()
        if len(palabras) > 1:
            # Si hay varias palabras, dividir en líneas
            lineas = []
            linea_actual = palabras[0]
            for palabra in palabras[1:]:
                prueba = linea_actual + " " + palabra
                ancho_prueba = fuente.size(prueba)[0]
                if ancho_prueba < self.rect.width - 10:
                    linea_actual = prueba
                else:
                    lineas.append(linea_actual)
                    linea_actual = palabra
            lineas.append(linea_actual)
            
            # Renderizar cada línea
            altura_total = len(lineas) * fuente.get_height()
            y_inicial = self.rect.centery - altura_total // 2
            
            for i, linea in enumerate(lineas):
                texto_surface = fuente.render(linea, True, color_texto_final)
                texto_rect = texto_surface.get_rect(centerx=self.rect.centerx, y=y_inicial + i * fuente.get_height())
                superficie.blit(texto_surface, texto_rect)
        else:
            # Renderizar texto en una sola línea
            texto_surface = fuente.render(self.texto, True, color_texto_final)
            texto_rect = texto_surface.get_rect(center=self.rect.center)
            superficie.blit(texto_surface, texto_rect)
        
    def verificar_hover(self, pos):
        self.activo = self.rect.collidepoint(pos)
        return self.activo
        
    def verificar_clic(self, pos):
        return self.rect.collidepoint(pos)

class RadioButton:
    def __init__(self, x, y, radio, texto, color=BLANCO, seleccionado=False):
        self.x = x
        self.y = y
        self.radio = radio
        self.texto = texto
        self.color = color
        self.seleccionado = seleccionado
        self.fuente = pygame.font.Font(None, 30)
        
    def dibujar(self, superficie):
        pygame.draw.circle(superficie, NEGRO, (self.x, self.y), self.radio, 2)
        pygame.draw.circle(superficie, self.color, (self.x, self.y), self.radio - 2)
        
        if self.seleccionado:
            pygame.draw.circle(superficie, VERDE_OSCURO, (self.x, self.y), self.radio - 6)
        
        texto_surface = self.fuente.render(self.texto, True, NEGRO)
        superficie.blit(texto_surface, (self.x + self.radio + 10, self.y - texto_surface.get_height() // 2))
        
    def verificar_clic(self, pos):
        distancia = ((pos[0] - self.x) ** 2 + (pos[1] - self.y) ** 2) ** 0.5
        return distancia <= self.radio

class Dropdown:
    def __init__(self, x, y, ancho, alto, opciones, color=BLANCO, color_seleccionado=VERDE):
        self.rect = pygame.Rect(x, y, ancho, alto)
        self.opciones = opciones
        self.color = color
        self.color_seleccionado = color_seleccionado
        self.seleccionado = opciones[0] if opciones else ""
        self.abierto = False
        self.fuente = pygame.font.Font(None, 30)
        
        self.rects_opciones = []
        for i, _ in enumerate(opciones):
            self.rects_opciones.append(pygame.Rect(x, y + alto * (i + 1), ancho, alto))

    def dibujar(self, superficie):
        pygame.draw.rect(superficie, self.color, self.rect)
        pygame.draw.rect(superficie, NEGRO, self.rect, 2)
        
        texto_surface = self.fuente.render(self.seleccionado, True, NEGRO)
        texto_rect = texto_surface.get_rect(midleft=(self.rect.x + 10, self.rect.centery))
        superficie.blit(texto_surface, texto_rect)
        
        pygame.draw.polygon(superficie, NEGRO, [
            (self.rect.right - 20, self.rect.centery - 5),
            (self.rect.right - 10, self.rect.centery + 5),
            (self.rect.right - 30, self.rect.centery + 5)
        ])
        
        if self.abierto:
            for i, opcion in enumerate(self.opciones):
                rect = self.rects_opciones[i]
                color = self.color_seleccionado if opcion == self.seleccionado else self.color
                pygame.draw.rect(superficie, color, rect)
                pygame.draw.rect(superficie, NEGRO, rect, 2)
                
                texto_surface = self.fuente.render(opcion, True, NEGRO)
                texto_rect = texto_surface.get_rect(midleft=(rect.x + 10, rect.centery))
                superficie.blit(texto_surface, texto_rect)

    def verificar_clic(self, pos):
        if self.rect.collidepoint(pos):
            self.abierto = not self.abierto
            return True
        
        if self.abierto:
            for i, rect in enumerate(self.rects_opciones):
                if rect.collidepoint(pos):
                    self.seleccionado = self.opciones[i]
                    self.abierto = False
                    return True
        
        if self.abierto:
            self.abierto = False
        
        return False

class Slider:
    def __init__(self, x, y, ancho, alto, valor_min=0, valor_max=100, valor_inicial=50, color_barra=GRIS, color_indicador=VERDE, unidad="%"):
        self.rect = pygame.Rect(x, y, ancho, alto)
        self.valor_min = valor_min
        self.valor_max = valor_max
        self.valor = valor_inicial
        self.color_barra = color_barra
        self.color_indicador = color_indicador
        self.unidad = unidad
        self.arrastrando = False
        self.fuente = pygame.font.Font(None, 30)
        
    def dibujar(self, superficie):
        pygame.draw.rect(superficie, self.color_barra, self.rect)
        pygame.draw.rect(superficie, NEGRO, self.rect, 2)
        
        porcentaje = (self.valor - self.valor_min) / (self.valor_max - self.valor_min)
        ancho_indicador = int(porcentaje * self.rect.width)
        rect_indicador = pygame.Rect(self.rect.x, self.rect.y, ancho_indicador, self.rect.height)
        
        pygame.draw.rect(superficie, self.color_indicador, rect_indicador)
        # Mostrar texto solo si se define una unidad no vacía
        try:
            unidad_str = str(self.unidad) if self.unidad is not None else ""
        except Exception:
            unidad_str = ""
        if unidad_str.strip():
            texto_surface = self.fuente.render(f"{self.valor} {unidad_str}".strip(), True, NEGRO)
            superficie.blit(texto_surface, (self.rect.right + 10, self.rect.centery - texto_surface.get_height() // 2))

    def verificar_clic(self, pos):
        if self.rect.collidepoint(pos):
            self.arrastrando = True
            self.actualizar_valor(pos[0])
            return True
        return False

    def verificar_soltar(self):
        self.arrastrando = False

    def verificar_arrastre(self, pos):
        if self.arrastrando:
            self.actualizar_valor(pos[0])
            return True
        return False

    def actualizar_valor(self, x):
        if x <= self.rect.x:
            self.valor = self.valor_min
        elif x >= self.rect.right:
            self.valor = self.valor_max
        else:
            porcentaje = (x - self.rect.x) / self.rect.width
            self.valor = int(self.valor_min + porcentaje * (self.valor_max - self.valor_min))

class VentanaConfiguracionRutina:
    def __init__(self, controlador_cnc=None, conexion_activa=False):
        self.controlador_cnc = controlador_cnc
        self.conexion_activa = conexion_activa

        # Iniciar maximizada en modo ventana (no fullscreen) y redimensionable
        info = pygame.display.Info()
        self.ancho, self.alto = info.current_w, info.current_h
        self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
        pygame.display.set_caption("Configuración de Rutina")
        # Forzar maximizar en Linux si wmctrl está disponible
        try:
            import subprocess
            subprocess.Popen(['wmctrl', '-r', ':ACTIVE:', '-b', 'add,maximized_vert,maximized_horz'])
        except Exception:
            pass
        self.fullscreen = False

        self.fuente_titulo = pygame.font.Font(None, 40)
        self.fuente_subtitulo = pygame.font.Font(None, 36)
        self.fuente_normal = pygame.font.Font(None, 30)

        self.color_header = VERDE_OSCURO
        self.color_fondo = BLANCO

        # Márgenes y espaciados ligeramente mayores para evitar solapamientos
        self.margen = 36
        self.espaciado = 28

        # Crear controles con posiciones iniciales (se recalcularán para el tamaño actual)
        self.radio_buttons_zona = [
            RadioButton(0, 0, 15, "Hombro", seleccionado=True),
            RadioButton(0, 0, 15, "Antebrazo")
        ]

        self.slider_nivel = Slider(
            0, 0,
            100, 34,
            valor_min=0, valor_max=10, valor_inicial=5,
            color_barra=GRIS, color_indicador=VERDE_OSCURO, unidad="level"
        )

        self.slider_velocidad = Slider(
            0, 0,
            100, 34,
            valor_inicial=50
        )

        # Botones inferiores más grandes y con fuente más visible
        ancho_boton = 200
        alto_boton = 60
        fuente_bot_inf = pygame.font.Font(None, 30)

        # Crear botones con posiciones provisionales (se recalcularán)
        self.boton_aplicar = Boton(0, 0, ancho_boton, alto_boton, "Aplicar", VERDE_OSCURO, fuente_bot_inf, NEGRO)
        self.boton_restablecer = Boton(0, 0, ancho_boton, alto_boton, "Restablecer", BLANCO, fuente_bot_inf)
        self.boton_regresar = Boton(0, 0, ancho_boton, alto_boton, "Regresar", ROJO, fuente_bot_inf)

        # Posicionar controles de acuerdo al tamaño actual de la ventana
        self.recalcular_layout()

        self.zona_seleccionada = "Hombro"
        self.velocidad = 50

        self.mensaje = ""
        self.color_mensaje = VERDE
        self.mostrar_mensaje_tiempo = 0
        
    def ejecutar(self):
        # Respetar configuración al iniciar ejecución (maximizada y resizable)
        info = pygame.display.Info()
        self.ancho, self.alto = info.current_w, info.current_h
        self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
        self.recalcular_layout()
        
        clock = pygame.time.Clock()
        ejecutando = True
        
        while ejecutando:
            self.pantalla.fill(self.color_fondo)
            pos_mouse = pygame.mouse.get_pos()
            tiempo_actual = pygame.time.get_ticks()
            
            if self.conexion_activa and self.controlador_cnc:
                cambio, nueva_velocidad = self.controlador_cnc.verificar_cambios_velocidad()
                if cambio:
                    self.velocidad = nueva_velocidad
                    self.slider_velocidad.valor = nueva_velocidad
            
            # Consumir eventos del controlador (mostrar popups desde el hilo principal)
            try:
                if self.controlador_cnc:
                    for ev in self.controlador_cnc.consumir_eventos():
                        if ev.get('tipo') == 'limite':
                            m = (ev.get('datos') or {}).get('mensaje') or "Se activó un limite físico, se volverá al origen automaticamente en 3 segundos."
                            try:
                                mostrar_aviso_sistema("Límite activado", m)
                            except Exception:
                                print(f"[AVISO] {m}")
            except Exception:
                pass

            for evento in pygame.event.get():
                if evento.type == pygame.QUIT:
                    raise CerrarPrograma("Usuario cerró ventana configuración")
                if evento.type == pygame.VIDEORESIZE:
                    info = pygame.display.Info()
                    w, h = info.current_w, info.current_h
                    self.ancho, self.alto = w, h
                    info = pygame.display.Info()
                    w, h = info.current_w, info.current_h
                    self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                    self.redimensionar(w, h)
                if evento.type == pygame.KEYDOWN:
                    if evento.key == pygame.K_F11:
                        self.fullscreen = not self.fullscreen
                        if self.fullscreen:
                            info = pygame.display.Info()
                            w, h = info.current_w, info.current_h
                            self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                            self.ancho, self.alto = w, h
                            self.redimensionar(w, h)
                        else:
                            info = pygame.display.Info()
                            w, h = info.current_w, info.current_h
                            self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                            self.ancho, self.alto = w, h
                            self.redimensionar(w, h)
                        continue
                    if evento.key == pygame.K_ESCAPE and self.fullscreen:
                        self.fullscreen = False
                        info = pygame.display.Info()
                        w, h = info.current_w, info.current_h
                        self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                        self.ancho, self.alto = w, h
                        self.redimensionar(w, h)
                        continue
                
                if evento.type == pygame.MOUSEBUTTONDOWN:
                    if self.boton_regresar.verificar_clic(pos_mouse):
                        return
                    
                    if self.boton_aplicar.verificar_clic(pos_mouse):
                        self.aplicar_configuracion()
                        self.mensaje = "Configuración aplicada"
                        self.color_mensaje = VERDE
                        self.mostrar_mensaje_tiempo = tiempo_actual + 3000
                    
                    if self.boton_restablecer.verificar_clic(pos_mouse):
                        self.restablecer_configuracion()
                        self.mensaje = "Configuración restablecida"
                        self.color_mensaje = AZUL
                        self.mostrar_mensaje_tiempo = tiempo_actual + 3000
                    
                    for radio_button in self.radio_buttons_zona:
                        if radio_button.verificar_clic(pos_mouse):
                            for rb in self.radio_buttons_zona:
                                rb.seleccionado = False
                            radio_button.seleccionado = True
                            self.zona_seleccionada = radio_button.texto
                    
                    if self.slider_nivel.verificar_clic(pos_mouse):
                        nivel = self.slider_nivel.valor
                        nueva_velocidad = 5 + (nivel * 9.5)
                        self.velocidad = int(nueva_velocidad)
                        self.slider_velocidad.valor = self.velocidad
                        if self.conexion_activa and self.controlador_cnc:
                            self.controlador_cnc.velocidad_actual = self.velocidad
                            if not getattr(self.controlador_cnc, 'ejecutando_rutina', False):
                                self.controlador_cnc.aplicar_velocidad()
                            try:
                                with open(self.controlador_cnc.archivo_velocidad, 'w') as f:
                                    json.dump({'velocidad': self.velocidad}, f)
                            except Exception as e:
                                print(f"Error al guardar velocidad: {e}")
                    
                    if self.slider_velocidad.verificar_clic(pos_mouse):
                        self.velocidad = self.slider_velocidad.valor
                        if self.conexion_activa and self.controlador_cnc:
                            self.controlador_cnc.velocidad_actual = self.velocidad
                            if not getattr(self.controlador_cnc, 'ejecutando_rutina', False):
                                self.controlador_cnc.aplicar_velocidad()
                            try:
                                with open(self.controlador_cnc.archivo_velocidad, 'w') as f:
                                    json.dump({'velocidad': self.velocidad}, f)
                            except Exception as e:
                                print(f"Error al guardar velocidad: {e}")
                
                if evento.type == pygame.MOUSEBUTTONUP:
                    self.slider_velocidad.verificar_soltar()
                    self.slider_nivel.verificar_soltar()
                
                if evento.type == pygame.MOUSEMOTION:
                    if self.slider_velocidad.verificar_arrastre(pos_mouse):
                        self.velocidad = self.slider_velocidad.valor
                        if self.conexion_activa and self.controlador_cnc:
                            self.controlador_cnc.velocidad_actual = self.velocidad
                            if not getattr(self.controlador_cnc, 'ejecutando_rutina', False):
                                self.controlador_cnc.aplicar_velocidad()
                            try:
                                with open(self.controlador_cnc.archivo_velocidad, 'w') as f:
                                    json.dump({'velocidad': self.velocidad}, f)
                            except Exception as e:
                                print(f"Error al guardar velocidad: {e}")
                    
                    if self.slider_nivel.verificar_arrastre(pos_mouse):
                        nivel = self.slider_nivel.valor
                        nueva_velocidad = 5 + (nivel * 9.5)
                        self.velocidad = int(nueva_velocidad)
                        self.slider_velocidad.valor = self.velocidad
                        if self.conexion_activa and self.controlador_cnc:
                            self.controlador_cnc.velocidad_actual = self.velocidad
                            if not getattr(self.controlador_cnc, 'ejecutando_rutina', False):
                                self.controlador_cnc.aplicar_velocidad()
                            try:
                                with open(self.controlador_cnc.archivo_velocidad, 'w') as f:
                                    json.dump({'velocidad': self.velocidad}, f)
                            except Exception as e:
                                print(f"Error al guardar velocidad: {e}")
            
            self.boton_aplicar.verificar_hover(pos_mouse)
            self.boton_restablecer.verificar_hover(pos_mouse)
            self.boton_regresar.verificar_hover(pos_mouse)
            
            self.dibujar_interfaz()
            
            if tiempo_actual < self.mostrar_mensaje_tiempo:
                self.mostrar_mensaje()
            
            pygame.display.flip()
            clock.tick(60)
        
        return not ejecutando  # Retorna True si salió normalmente, False si se cerró la ventana

    def dibujar_interfaz(self):
        pygame.draw.rect(self.pantalla, self.color_header, (0, 0, self.ancho, 60))
        
        titulo = self.fuente_titulo.render("Configuración de Rutina", True, BLANCO)
        rect_titulo = titulo.get_rect(center=(self.ancho // 2, 30))
        self.pantalla.blit(titulo, rect_titulo)
        
        subtitulo_zona = self.fuente_subtitulo.render("Zona de rehabilitación", True, NEGRO)
        self.pantalla.blit(subtitulo_zona, (self.margen, self.margen + 70))
        
        for radio_button in self.radio_buttons_zona:
            radio_button.dibujar(self.pantalla)
        
        subtitulo_nivel = self.fuente_subtitulo.render("Nivel de rehabilitación", True, NEGRO)
        self.pantalla.blit(subtitulo_nivel, (self.margen, self.margen + 180))
        
        self.slider_nivel.dibujar(self.pantalla)
        
        subtitulo_velocidad = self.fuente_subtitulo.render("Velocidad", True, NEGRO)
        self.pantalla.blit(subtitulo_velocidad, (self.margen, self.margen + 310))
        
        self.slider_velocidad.dibujar(self.pantalla)
        
        self.boton_aplicar.dibujar(self.pantalla)
        self.boton_restablecer.dibujar(self.pantalla)
        self.boton_regresar.dibujar(self.pantalla)
        
        # Barra inferior permanente de estado
        dibujar_barra_inferior(
            self.pantalla, self.ancho, self.alto,
            bool(self.controlador_cnc and self.controlador_cnc.esta_conectado()),
            None,
            getattr(self, 'controlador_cnc', None)
        )

    def mostrar_mensaje(self):
        # Mostrar mensaje por encima de la barra inferior
        texto = self.fuente_normal.render(self.mensaje, True, self.color_mensaje)
        reserva_barra = alto_barra_inferior(self.alto) + 10
        rect = texto.get_rect(center=(self.ancho // 2, self.alto - reserva_barra - 40))
        self.pantalla.blit(texto, rect)

    def recalcular_layout(self):
        # Reposicionar controles según el tamaño actual y reservar espacio para la barra inferior
        barra = alto_barra_inferior(self.alto)
        header_h = 60
        
        # Radio buttons zona
        y_radio = self.margen + 120
        self.radio_buttons_zona[0].x = self.margen + 20
        self.radio_buttons_zona[0].y = y_radio
        self.radio_buttons_zona[1].x = self.ancho // 2 + 20
        self.radio_buttons_zona[1].y = y_radio
        
        # Sliders (anchos adaptados)
        self.slider_nivel.rect = pygame.Rect(
            self.margen, self.margen + 240,
            max(100, self.ancho - 2 * self.margen - 80), 34
        )
        self.slider_velocidad.rect = pygame.Rect(
            self.margen, self.margen + 380,
            max(100, self.ancho - 2 * self.margen - 80), 34
        )
        
        # Botones inferiores anclados arriba de la barra inferior
        ancho_boton = self.boton_aplicar.rect.width
        alto_boton = self.boton_aplicar.rect.height
        y_bot = self.alto - barra - self.margen - alto_boton
        
        self.boton_regresar.rect.topleft = (self.margen, y_bot)
        self.boton_restablecer.rect.topright = (self.ancho - self.margen, y_bot)
        sep = 10
        self.boton_aplicar.rect.topright = (self.boton_restablecer.rect.left - sep, y_bot)

    def redimensionar(self, nuevo_ancho, nuevo_alto):
        info = pygame.display.Info()
        self.ancho, self.alto = info.current_w, info.current_h
        self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
        self.recalcular_layout()

    def aplicar_configuracion(self):
        if self.conexion_activa and self.controlador_cnc:
            self.controlador_cnc.velocidad_actual = self.velocidad
            self.controlador_cnc.aplicar_velocidad()
            try:
                with open(self.controlador_cnc.archivo_velocidad, 'w') as f:
                    json.dump({'velocidad': self.velocidad}, f)
            except Exception as e:
                print(f"Error al guardar velocidad: {e}")
        
        print(f"Configuración aplicada: Zona={self.zona_seleccionada}, Nivel={self.slider_nivel.valor}, Velocidad={self.velocidad}%")

    def restablecer_configuracion(self):
        self.zona_seleccionada = "Hombro"
        self.velocidad = 50
        
        for rb in self.radio_buttons_zona:
            rb.seleccionado = rb.texto == "Hombro"
        
        self.slider_nivel.valor = 5
        self.slider_velocidad.valor = 50
        
        if self.conexion_activa and self.controlador_cnc:
            self.controlador_cnc.velocidad_actual = self.velocidad
            self.controlador_cnc.aplicar_velocidad()
            try:
                with open(self.controlador_cnc.archivo_velocidad, 'w') as f:
                    json.dump({'velocidad': self.velocidad}, f)
            except Exception as e:
                print(f"Error al guardar velocidad: {e}")

def calcular_ancho_texto(texto, fuente):
    return fuente.render(texto, True, NEGRO).get_width() + 20

def centrar_ventana(ancho, alto):
    """Función mejorada para centrar ventana"""
    info = pygame.display.Info()
    pos_x, pos_y = (info.current_w - ancho) // 2, (info.current_h - alto) // 2
    os.environ['SDL_VIDEO_WINDOW_POS'] = f"{pos_x},{pos_y}"

def ajustar_a_pantalla(ancho, alto, min_w=480, min_h=360, margen=20):
    """Devuelve (ancho, alto) ajustados para caber en la pantalla con márgenes."""
    try:
        info = pygame.display.Info()
        max_w = max(min_w, info.current_w - margen * 2)
        max_h = max(min_h, info.current_h - margen * 2)
        nuevo_ancho = max(min_w, min(ancho, max_w))
        nuevo_alto = max(min_h, min(alto, max_h))
        return nuevo_ancho, nuevo_alto
    except Exception:
        # Si no se puede obtener info de pantalla, devolver originales limitados por mínimos
        return max(min_w, ancho), max(min_h, alto)

def mostrar_aviso_sistema(titulo, mensaje):
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(titulo, mensaje)
        root.destroy()
    except Exception as e:
        print(f"[AVISO] {titulo}: {mensaje} (No se pudo mostrar ventana: {e})")
    finally:
        try:
            pygame.event.pump()
            pygame.display.flip()
        except Exception:
            pass

def recortar_con_ellipsis(texto, fuente, ancho_max):
    """Recorta el texto añadiendo … si excede ancho_max."""
    if fuente.size(texto)[0] <= ancho_max:
        return texto
    if ancho_max <= 0:
        return ""
    ell = "…"
    # Búsqueda decreciente simple
    for n in range(len(texto), 0, -1):
        t = texto[:n] + ell
        if fuente.size(t)[0] <= ancho_max:
            return t
    return ell
def ajustar_fuente_a_ancho(texto, ancho_max, tamaño_inicial, tamaño_min=12):
    """Devuelve una fuente cuyo texto cabe en ancho_max, reduciendo tamaño si es necesario."""
    tamaño = max(tamaño_min, int(tamaño_inicial))
    fuente = pygame.font.Font(None, tamaño)
    while tamaño > tamaño_min and fuente.size(texto)[0] > ancho_max:
        tamaño -= 1
        fuente = pygame.font.Font(None, tamaño)
    return fuente

def limpiar_linea_gcode(linea: str) -> str:
    """Elimina comentarios de una línea G-code y normaliza espacios.
    - Quita comentarios entre paréntesis (...)
    - Quita comentarios con ';' desde el punto y coma hacia el final
    - Retorna la línea limpia con espacios normalizados o cadena vacía
    """
    try:
        s = str(linea).strip()
        if not s:
            return ""
        # Quitar comentarios entre paréntesis (anidados simple)
        out = []
        depth = 0
        for ch in s:
            if ch == '(':
                depth += 1
                continue
            if ch == ')':
                if depth > 0:
                    depth -= 1
                continue
            if depth > 0:
                continue
            out.append(ch)
        s = ''.join(out)
        # Quitar desde ';' al final
        if ';' in s:
            s = s.split(';', 1)[0]
        # Normalizar espacios
        s = ' '.join(s.strip().split())
        return s
    except Exception:
        return ""

# === Utilidades de barra inferior de estado (permanente) ===
def alto_barra_inferior(alto):
    """Calcula la altura de la barra inferior según el alto de la ventana."""
    try:
        return int(max(30, min(alto * 0.08, alto * 0.16)))
    except Exception:
        return 40

def dibujar_barra_inferior(pantalla, ancho, alto, conexion_activa, estado_conexion=None, controlador_cnc=None, offset_px=0):
    """Dibuja una barra inferior permanente con color según conexión y texto centrado.

    - Verde si conectado, rojo si no.
    - Texto blanco centrado; incluye firmware/puerto si hay controlador y está conectado.
    """
    # Barra de estado de conexión CNC eliminada según solicitud

class VentanaPrincipal:
    def __init__(self):
        # Tamaño de diseño base (proporciones ideales)
        self.ancho_base = 1400
        self.alto_base = 1700
        
        # Tamaño mínimo absoluto
        self.ancho_min = 480
        self.alto_min = 480
        
        # Tamaño inicial maximizado (no fullscreen)
        self.ancho, self.alto = ajustar_a_pantalla(self.ancho_base, self.alto_base, self.ancho_min, self.alto_min)
        self.fullscreen = False
        
        # Crear pantalla con tamaño ajustado
        self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE | pygame.DOUBLEBUF)
        pygame.display.set_caption("Registro de Pacientes - Escalado Uniforme")
        
        # Forzar maximizar en Linux si wmctrl está disponible
        try:
            import subprocess
            subprocess.Popen(['wmctrl', '-r', ':ACTIVE:', '-b', 'add,maximized_vert,maximized_horz'])
        except Exception:
            pass

        # Inicializar gestor de pacientes
        self.gestor_pacientes = GestorPacientes()

        # Factor de escala global
        self.escala = 1.0

        # Cargar configuración de layout (JSON o módulo de objetos)
        self.config_layout = None
        self._layout_module = None
        self.cargar_layout()

        # Modo edición removido

        self.crear_elementos()

        # Mensajes de estado
        self.mensaje = ""
        self.color_mensaje = ROJO
        self.mostrar_mensaje_tiempo = 0
        self.paciente_actual = None
        self.nombre_paciente_guardado = ""

    def calcular_escala(self):
        """Calcula la escala considerando tanto el ancho como la altura disponible"""
        escala_x = self.ancho / self.ancho_base
        escala_y = self.alto / self.alto_base
        
        # Usar la escala menor para asegurar que todo quepa, pero con más flexibilidad
        self.escala = min(escala_x, escala_y)
        
        # Permitir un poco más de flexibilidad en pantallas anchas
        if escala_x > escala_y * 1.3:
            self.escala = min(escala_y * 1.1, escala_x * 0.9)
        
        # Limitar la escala para mantener legibilidad
        self.escala = max(0.4, min(self.escala, 1.5))

    def escalar_coord(self, valor):
        """Escala una coordenada individual"""
        return int(valor * self.escala)

    def escalar_fuente(self, tamaño_base):
        """Escala el tamaño de fuente con mejor progresión"""
        tamaño_escalado = int(tamaño_base * self.escala)
        # Asegurar tamaños mínimos y máximos más apropiados
        if tamaño_base <= 20:  # Fuentes pequeñas
            return max(12, min(tamaño_escalado, 28))
        elif tamaño_base <= 30:  # Fuentes medianas
            return max(16, min(tamaño_escalado, 44))
        else:  # Fuentes grandes (títulos)
            return max(22, min(tamaño_escalado, 200))

    def crear_elementos(self):
        """Crea todos los elementos de la interfaz con espaciado optimizado"""
        self.calcular_escala()

        # Crear fuentes escaladas (permite overrides por JSON)
        fcfg = (self.config_layout or {}).get('fuentes', {})
        self._fcfg = fcfg
        self.fuente = pygame.font.Font(None, self.escalar_fuente(fcfg.get('general', 42)))
        self.fuente_titulo = pygame.font.Font(None, self.escalar_fuente(fcfg.get('titulo', 100)))
        self.fuente_pequeña = pygame.font.Font(None, self.escalar_fuente(fcfg.get('pequena', 32)))
        self.fuente_descripcion = pygame.font.Font(None, self.escalar_fuente(fcfg.get('descripcion', 38)))

        # Dimensiones base escaladas
        margcfg = (self.config_layout or {}).get('margenes', {})
        self._margcfg = margcfg
        margen = self.escalar_coord(margcfg.get('margen_externo', 25))
        # Margen de secciones usado para marcos y alineaciones a la derecha
        self.margen_seccion = self.escalar_coord(margcfg.get('margen_seccion', 15))
        ancho_disponible = self.ancho - 2 * margen
        camposcfg = (self.config_layout or {}).get('campos', {})
        self._camposcfg = camposcfg
        ancho_campo = min(self.escalar_coord(camposcfg.get('ancho_max', 1000)), int(ancho_disponible * 0.95))
        # Altura de campo por perfiles
        alto_perfiles = camposcfg.get('alto', {"grande": 50, "medio": 55, "chico": 60})
        alto_campo_base = alto_perfiles.get('grande', 50) if self.escala >= 0.9 else (alto_perfiles.get('medio', 55) if self.escala >= 0.7 else alto_perfiles.get('chico', 60))
        alto_campo = self.escalar_coord(alto_campo_base)

        # Cálculo de posiciones Y (compacto)
        y_actual = self.escalar_coord(25)  # Margen superior

        # Título
        y_titulo = y_actual
        y_actual += self.escalar_coord(80)

        # Sección de búsqueda
        y_desc_busqueda = y_actual
        y_actual += self.escalar_coord(55)

        y_busqueda = y_actual
        y_actual += alto_campo + self.escalar_coord(18)

        y_boton_buscar = y_actual
        y_actual += self.escalar_coord(60) + self.escalar_coord(35)

        # Separador
        y_separador = y_actual
        y_actual += self.escalar_coord(40)

        # Sección de registro
        y_desc_registro = y_actual
        y_actual += self.escalar_coord(60)

        # Campos de registro con espaciado compacto
        y_inicio_campos = y_actual
        esp_perfiles = camposcfg.get('espaciado_base', {"grande": 140, "medio": 150, "chico": 160})
        base_esp = esp_perfiles.get('grande', 140) if self.escala >= 0.9 else (esp_perfiles.get('medio', 150) if self.escala >= 0.7 else esp_perfiles.get('chico', 160))
        espaciado_campo = self.escalar_coord(base_esp)

        # Centrar horizontalmente
        x_inicio = (self.ancho - ancho_campo) // 2

        # Crear campo de búsqueda
        self.campo_busqueda = CampoTextoSimple(
            x_inicio, y_busqueda, ancho_campo, alto_campo,
            "Nombre completo:", self.fuente
        )

        # Crear botón de búsqueda
        ancho_boton_buscar = min(self.escalar_coord(350), int(ancho_campo * 0.6))
        self.boton_buscar = Boton(
            x_inicio, y_boton_buscar,
            ancho_boton_buscar, self.escalar_coord(55),
            "Buscar Paciente", AMARILLO, self.fuente
        )

        # Crear campos de registro (permite override de orden y etiquetas)
        self.campos = {}
        orden_defecto = ['primer_nombre', 'segundo_nombre', 'primer_apellido', 'segundo_apellido', 'año_nacimiento']
        nombres_campos = (camposcfg.get('orden_campos') or orden_defecto)
        etiquetas_map = camposcfg.get('etiquetas') or {}
        etiquetas = [etiquetas_map.get(n, e) for n, e in zip(nombres_campos, [
            "Primer Nombre:", "Segundo Nombre:", "Primer Apellido:", "Segundo Apellido:", "Año de Nacimiento:"
        ])]

        # Separación ampliada por defecto entre campos y checkbox (configurable)
        sep_chk = camposcfg.get('separacion_checkbox', 8)
        separacion_ampliada = self.escalar_coord(sep_chk)
        # Desfase etiqueta general y por campo (configurable)
        desfase_etq_general = camposcfg.get('desfase_etiqueta', 35)
        desfase_por_campo = camposcfg.get('desfase_etiqueta_por_campo', {})
        # Extra de separación superior por campo para alejarlo del checkbox superior
        extra_sup_por_campo = camposcfg.get('extra_separacion_superior_por_campo', {})

        extra_acumulado = 0
        for i, (nombre, etiqueta) in enumerate(zip(nombres_campos, etiquetas)):
            extra_este = self.escalar_coord(int(extra_sup_por_campo.get(nombre, 0)))
            y_campo = y_inicio_campos + i * espaciado_campo + extra_acumulado + extra_este
            desfase_etq = desfase_por_campo.get(nombre, desfase_etq_general)
            self.campos[nombre] = CampoTexto(
                x_inicio, y_campo, ancho_campo, alto_campo,
                etiqueta, self.fuente, separacion_checkbox=separacion_ampliada, desfase_etiqueta=self.escalar_coord(desfase_etq)
            )
            # El extra agregado a este campo también desplaza los siguientes para mantener el flujo
            extra_acumulado += extra_este

        # Actualizar y_actual después de los campos considerando el extra acumulado
        y_actual = y_inicio_campos + len(nombres_campos) * espaciado_campo + extra_acumulado + self.escalar_coord(35)

        # Crear botones principales en una sola fila (parte inferior de la sección)
        y_botones = y_actual + self.escalar_coord(25)
        # Tamaño responsivo de botones (configurable)
        bcfg = (self.config_layout or {}).get('botones', {})
        self._bcfg = bcfg
        alto_boton = min(
            max(self.escalar_coord(bcfg.get('alto_min', 40)), int(self.alto * 0.06)),
            self.escalar_coord(bcfg.get('alto_max', 60))
        )
        espaciado_botones_h = self.escalar_coord(bcfg.get('espaciado_horizontal', 30))  # separación horizontal entre botones
        # Ancho objetivo por botón y ajuste si no caben dos
        min_ancho_btn = self.escalar_coord(bcfg.get('ancho_min', 140))
        ancho_objetivo = min(
            max(self.escalar_coord(bcfg.get('ancho_obj_min', 200)), int(self.ancho * bcfg.get('ancho_obj_pct', 0.25))),
            self.escalar_coord(bcfg.get('ancho_obj_max', 400))
        )
        ancho_dispo = self.ancho - 2 * self.margen_seccion
        if 2 * ancho_objetivo + espaciado_botones_h > ancho_dispo:
            ancho_boton = max(min_ancho_btn, (ancho_dispo - espaciado_botones_h) // 2)
        else:
            ancho_boton = ancho_objetivo
        # Posicionar centrados horizontalmente dentro del ancho disponible
        ancho_total_botones = 2 * ancho_boton + espaciado_botones_h
        alineacion = bcfg.get('alineacion', 'centrado')
        if alineacion == 'derecha':
            x_inicio_bot = max(self.margen_seccion, self.ancho - self.margen_seccion - ancho_total_botones)
        elif alineacion == 'izquierda':
            x_inicio_bot = self.margen_seccion
        else:
            x_inicio_bot = max(self.margen_seccion, (self.ancho - ancho_total_botones) // 2)
        x_boton_izquierdo = x_inicio_bot
        x_boton_derecho = x_inicio_bot + ancho_boton + espaciado_botones_h

        self.boton_registrar = Boton(
            x_boton_izquierdo, y_botones,
            ancho_boton, alto_boton,
            "Registrar Paciente", VERDE, self.fuente
        )
        self.boton_continuar = Boton(
            x_boton_derecho, y_botones,
            ancho_boton, alto_boton,
            "Continuar al Sistema", AZUL, self.fuente
        )

        # Botón "Salir del programa" dentro del marco azul (sección registro)
        # Alinear a la derecha de la sección; misma fila que los botones principales si cabe, de lo contrario en la fila siguiente
        alto_barra_px = alto_barra_inferior(self.alto)
        margen_inferior = self.escalar_coord(12)
        ancho_boton_salir = max(self.escalar_coord(260), int(self.ancho * 0.18))
        alto_boton_salir = max(self.escalar_coord(50), alto_boton)
        padding_marco_local = self.escalar_coord((self._margcfg or {}).get('padding_marco', 10))
        # Lado derecho interior del marco azul
        x_salir = max(
            self.margen_seccion + padding_marco_local,
            (self.ancho - self.margen_seccion) - padding_marco_local - ancho_boton_salir
        )
        # Intentar colocar en la misma línea que los botones principales
        y_salir = y_botones
        # Evitar solapamientos con el botón derecho existente
        sep_chequeo = max(espaciado_botones_h, self.escalar_coord(10))
        min_x_libre = x_boton_derecho + ancho_boton + sep_chequeo
        if x_salir < min_x_libre:
            # Si no cabe en la misma fila, colocarlo en una fila siguiente dentro de la sección
            y_salir = y_botones + alto_boton + self.escalar_coord(10)
        self.boton_salir = Boton(
            x_salir, y_salir,
            ancho_boton_salir, alto_boton_salir,
            "Salir del programa", ROJO, self.fuente, BLANCO
        )

        # Guardar posiciones para dibujo
        self.pos_titulo = (self.ancho // 2, y_titulo + self.escalar_coord(20))
        self.y_separador = y_separador
        # self.margen_seccion ya fue definido arriba para evitar errores de atributo

        # Calcular rectángulos de las secciones con padding configurable
        padding_marco = self.escalar_coord(margcfg.get('padding_marco', 10))

        self.rect_busqueda = pygame.Rect(
            self.margen_seccion,
            y_desc_busqueda - padding_marco,
            self.ancho - 2 * self.margen_seccion,
            self.boton_buscar.rect.bottom - y_desc_busqueda + padding_marco * 2
        )

        # Altura de la sección debe abarcar hasta el contenido más bajo (botón continuar o salir)
        bottom_contenido = max(self.boton_continuar.rect.bottom, getattr(self, 'boton_salir', self.boton_continuar).rect.bottom)
        self.rect_registro = pygame.Rect(
            self.margen_seccion,
            y_desc_registro - padding_marco,
            self.ancho - 2 * self.margen_seccion,
            bottom_contenido - y_desc_registro + padding_marco * 3
        )

    # Posiciones absolutas no aplicadas (edit mode deshabilitado)

    def cargar_layout(self):
        """Carga configuración de layout desde un módulo Python (objetos) o JSON como fallback."""
        self.config_layout = None
        self._layout_module = None
        # 1) Intentar módulo de objetos
        try:
            # Import dinámico del módulo si existe
            mod_name = 'config.layout_objetos'
            if mod_name in sys.modules:
                self._layout_module = importlib.reload(sys.modules[mod_name])
            else:
                self._layout_module = importlib.import_module(mod_name)
            if hasattr(self._layout_module, 'get_layout'):
                cfg = self._layout_module.get_layout()
                if isinstance(cfg, dict):
                    self.config_layout = cfg
                    return
            if hasattr(self._layout_module, 'CONFIG') and isinstance(self._layout_module.CONFIG, dict):
                self.config_layout = self._layout_module.CONFIG
                return
        except Exception:
            # Si falla el módulo, continuamos con JSON
            pass
        # 2) Fallback a JSON
        try:
            cfg_path = os.path.join(os.path.dirname(__file__), 'config', 'layout_principal.json')
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r') as f:
                    self.config_layout = json.load(f)
        except Exception as e:
            print(f"No se pudo cargar layout_principal.json: {e}")


    def redimensionar(self, nuevo_ancho, nuevo_alto):
        """Redimensiona todos los elementos de la interfaz - Método de VentanaSecundaria"""
        # Aplicar tamaños mínimos
        nuevo_ancho = max(self.ancho_min, nuevo_ancho)
        nuevo_alto = max(self.alto_min, nuevo_alto)
        
        # Guardar estado actual de los campos ANTES de cambiar dimensiones
        estado_campos = {}
        for nombre, campo in self.campos.items():
            estado_campos[nombre] = {
                'texto': campo.texto,
                'activo': campo.activo
            }
        
        estado_busqueda = {
            'texto': self.campo_busqueda.texto,
            'activo': self.campo_busqueda.activo
        }
        
        # Actualizar dimensiones
        self.ancho = nuevo_ancho
        self.alto = nuevo_alto
        
        # Recrear elementos
        self.crear_elementos()
        
        # Restaurar estado de campos
        for nombre, estado in estado_campos.items():
            if nombre in self.campos:
                self.campos[nombre].texto = estado['texto']
                self.campos[nombre].activo = estado['activo']
        
        self.campo_busqueda.texto = estado_busqueda['texto']
        self.campo_busqueda.activo = estado_busqueda['activo']

    def buscar_paciente(self, tiempo_actual):
        """Busca un paciente por nombre completo"""
        try:
            nombre_completo = self.campo_busqueda.obtener_valor().strip()
            if not nombre_completo:
                self.mensaje = "Ingrese un nombre completo para buscar"
                self.color_mensaje = ROJO
                self.mostrar_mensaje_tiempo = tiempo_actual + 3000
                return
            # Buscar paciente
            id_paciente, resultado = self.gestor_pacientes.buscar_paciente_por_nombre(nombre_completo)
            if id_paciente and resultado:
                self.paciente_actual = id_paciente
                self.mensaje = f"Paciente encontrado: {id_paciente}"
                self.color_mensaje = VERDE
                # Limpiar campos de registro
                for campo in self.campos.values():
                    campo.texto = ""
            else:
                self.mensaje = "Paciente no encontrado."
                self.color_mensaje = ROJO
            self.mostrar_mensaje_tiempo = tiempo_actual + 5000
        except Exception as e:
            self.mensaje = f"Error al buscar paciente: {e}"
            self.color_mensaje = ROJO
            self.mostrar_mensaje_tiempo = tiempo_actual + 5000

    def registrar_paciente(self, tiempo_actual):
        try:
            # Recopilar datos
            datos = {}
            for nombre, campo in self.campos.items():
                valor = campo.obtener_valor()
                if valor and valor.strip() != "":
                    datos[nombre] = valor
            if not datos:
                self.mensaje = "No se ingresó ningún dato para registrar."
                self.color_mensaje = ROJO
                self.mostrar_mensaje_tiempo = tiempo_actual + 3000
                return
            # Registrar paciente
            exito, resultado = self.gestor_pacientes.registrar_paciente(datos)
            if exito:
                self.paciente_actual = resultado
                self.mensaje = f"Paciente registrado exitosamente. ID: {resultado}"
                self.color_mensaje = VERDE
                # Limpiar campos
                for campo in self.campos.values():
                    campo.texto = ""
                # Limpiar campo de búsqueda
                self.campo_busqueda.texto = ""
            else:
                self.mensaje = resultado
                self.color_mensaje = ROJO
            self.mostrar_mensaje_tiempo = tiempo_actual + 5000
        except Exception as e:
            self.mensaje = f"Error al registrar paciente: {e}"
            self.color_mensaje = ROJO
            self.mostrar_mensaje_tiempo = tiempo_actual + 5000

    

    def dibujar_interfaz(self):
        # Título centrado (usando fuente_titulo directamente)
        alto_barra = alto_barra_inferior(self.alto)
        titulo = self.fuente_titulo.render("Registro de Pacientes", True, NEGRO)
        titulo_rect = titulo.get_rect(center=self.pos_titulo)
        self.pantalla.blit(titulo, titulo_rect)
        
        # Sección de búsqueda
        pygame.draw.rect(self.pantalla, GRIS_CLARO, self.rect_busqueda)
        pygame.draw.rect(self.pantalla, VERDE_OSCURO, self.rect_busqueda, max(2, self.escalar_coord(3)))
        
        # Texto descriptivo de búsqueda centrado en el marco con espaciado aumentado (con ajuste)
        ancho_desc_busqueda = self.rect_busqueda.width - self.escalar_coord(28)
        base_desc = (getattr(self, '_fcfg', {}) or {}).get('descripcion', 20)
        fuente_desc_busq = ajustar_fuente_a_ancho("¿Ya tiene registro? Busque aquí:", ancho_desc_busqueda, self.escalar_fuente(base_desc), 14)
        desc_busqueda = fuente_desc_busq.render("¿Ya tiene registro? Busque aquí:", True, VERDE_OSCURO)
        desc_busqueda_rect = desc_busqueda.get_rect(centerx=self.rect_busqueda.centerx, 
                                                   y=self.rect_busqueda.top + self.escalar_coord(17))
        self.pantalla.blit(desc_busqueda, desc_busqueda_rect)
        
        # Campo de búsqueda y botón
        self.campo_busqueda.dibujar(self.pantalla)
        self.boton_buscar.dibujar(self.pantalla)
        
        # Línea separadora
        pygame.draw.line(self.pantalla, VERDE_OSCURO, 
                        (self.margen_seccion, self.y_separador), 
                        (self.ancho - self.margen_seccion, self.y_separador), 
                        max(2, self.escalar_coord(4)))
        
        # Sección de registro
        pygame.draw.rect(self.pantalla, GRIS_CLARO, self.rect_registro)
        pygame.draw.rect(self.pantalla, AZUL, self.rect_registro, max(2, self.escalar_coord(3)))
        
        # Texto descriptivo de registro centrado en el marco con espaciado aumentado (con ajuste)
        ancho_desc_registro = self.rect_registro.width - self.escalar_coord(28)
        base_desc = (getattr(self, '_fcfg', {}) or {}).get('descripcion', 20)
        fuente_desc_reg = ajustar_fuente_a_ancho("Registro de nuevo paciente:", ancho_desc_registro, self.escalar_fuente(base_desc), 14)
        desc_registro = fuente_desc_reg.render("Registro de nuevo paciente:", True, AZUL)
        desc_registro_rect = desc_registro.get_rect(centerx=self.rect_registro.centerx, 
                                                   y=self.rect_registro.top + self.escalar_coord(17))
        self.pantalla.blit(desc_registro, desc_registro_rect)
        
        # Campos de registro
        for campo in self.campos.values():
            campo.dibujar(self.pantalla)
        
        # Botones principales
        self.boton_registrar.dibujar(self.pantalla)
        self.boton_continuar.dibujar(self.pantalla)
        # Botón salir dentro del marco azul
        if hasattr(self, 'boton_salir'):
            self.boton_salir.dibujar(self.pantalla)
        
    # Información del paciente actual con espaciado aumentado
        if self.paciente_actual:
            texto_paciente_str = f"✓ Paciente actual: {self.paciente_actual}"
            max_px = self.ancho - 2 * self.margen_seccion - self.escalar_coord(28)
            fuente_paciente = ajustar_fuente_a_ancho(texto_paciente_str, max_px, self.escalar_fuente(24), 14)
            texto_paciente_fit = recortar_con_ellipsis(texto_paciente_str, fuente_paciente, max_px)
            texto_paciente = fuente_paciente.render(texto_paciente_fit, True, VERDE_OSCURO)
            y_paciente = self.boton_continuar.rect.bottom + self.escalar_coord(21)
            rect_paciente = pygame.Rect(
                self.margen_seccion, y_paciente,
                self.ancho - 2 * self.margen_seccion, self.escalar_coord(49)
            )
            pygame.draw.rect(self.pantalla, VERDE, rect_paciente)
            pygame.draw.rect(self.pantalla, VERDE_OSCURO, rect_paciente, max(1, self.escalar_coord(2)))
            texto_rect = texto_paciente.get_rect(center=rect_paciente.center)
            self.pantalla.blit(texto_paciente, texto_rect)

        # Dibujar barra inferior permanente elevada (subida) al final del frame
        offset_barra = self.escalar_coord(110)
        dibujar_barra_inferior(
            self.pantalla, self.ancho, self.alto,
            False,  # En esta ventana no hay conexión directa a la CNC
            "CNC no conectada",
            None,
            offset_px=offset_barra
        )

    def mostrar_mensaje(self):
        # Mensaje escalado y centrado, posicionado dinámicamente con espaciado aumentado
        texto = self.fuente_pequeña.render(self.mensaje, True, BLANCO)
        
        # Calcular posición Y dinámica con espaciado aumentado, reservando barra inferior
        y_base = self.boton_continuar.rect.bottom + self.escalar_coord(21)
        if self.paciente_actual:
            y_base += self.escalar_coord(70)
        
        # Asegurar que el mensaje no se salga de la ventana
        alto_mensaje = self.escalar_coord(49)
        # Reservar espacio considerando la barra elevada
        reserva_barra = alto_barra_inferior(self.alto) + self.escalar_coord(110) + self.escalar_coord(8)
        if y_base + alto_mensaje > self.alto - reserva_barra:
            y_base = self.alto - reserva_barra - alto_mensaje
        
        # Crear rectángulo del mensaje centrado
        padding = self.escalar_coord(14)
        ancho_mensaje = min(texto.get_width() + 2 * padding, self.ancho - 2 * self.margen_seccion)
        
        rect_mensaje = pygame.Rect(
            (self.ancho - ancho_mensaje) // 2, y_base,
            ancho_mensaje, alto_mensaje
        )
        
        pygame.draw.rect(self.pantalla, self.color_mensaje, rect_mensaje)
        pygame.draw.rect(self.pantalla, NEGRO, rect_mensaje, max(1, self.escalar_coord(2)))
        
        # Centrar texto en el rectángulo
        texto_rect = texto.get_rect(center=rect_mensaje.center)
        self.pantalla.blit(texto, texto_rect)

    def ejecutar(self):
        clock = pygame.time.Clock()
        ejecutando = True
        
        while ejecutando:
            tiempo_actual = pygame.time.get_ticks()
            
            # Limpiar pantalla ANTES de procesar eventos
            self.pantalla.fill(BLANCO)
            
            pos_mouse = pygame.mouse.get_pos()
            
            for evento in pygame.event.get():
                if evento.type == pygame.QUIT:
                    raise CerrarPrograma("Usuario cerró la ventana principal")
                
                # Manejar redimensionamiento de ventana - IGUAL QUE VENTANA SECUNDARIA
                elif evento.type == pygame.VIDEORESIZE:
                    nuevo_w, nuevo_h = ajustar_a_pantalla(evento.w, evento.h, self.ancho_min, self.alto_min)
                    self.redimensionar(nuevo_w, nuevo_h)
                
                elif evento.type == pygame.KEYDOWN:
                    if evento.key == pygame.K_F11:
                        # Alternar pantalla completa
                        self.fullscreen = not self.fullscreen
                        info = pygame.display.Info()
                        w = max(self.ancho_min, info.current_w)
                        h = max(self.alto_min, info.current_h)
                        self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE | pygame.DOUBLEBUF)
                        self.redimensionar(w, h)
                        continue
                    elif evento.key == pygame.K_F5:
                        # Recargar layout desde módulo/JSON y reconstruir elementos
                        self.cargar_layout()
                        self.crear_elementos()
                        continue
                    elif evento.key == pygame.K_ESCAPE and self.fullscreen:
                        # Salir de pantalla completa con ESC
                        self.fullscreen = False
                        w, h = ajustar_a_pantalla(self.ancho_base, self.alto_base, self.ancho_min, self.alto_min)
                        self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE | pygame.DOUBLEBUF)
                        self.redimensionar(w, h)
                        continue
                    # Manejar entrada de texto para campos activos
                    for campo in self.campos.values():
                        if campo.activo:
                            if evento.key == pygame.K_BACKSPACE:
                                campo.borrar_caracter()
                            elif hasattr(evento, 'unicode') and evento.unicode and evento.unicode.isprintable():
                                campo.agregar_caracter(evento.unicode)

                    # Campo de búsqueda (entrada de texto y acciones)
                    if self.campo_busqueda.activo:
                        if evento.key == pygame.K_BACKSPACE:
                            self.campo_busqueda.borrar_caracter()
                        elif evento.key == pygame.K_RETURN:
                            self.buscar_paciente(tiempo_actual)
                        elif hasattr(evento, 'unicode') and evento.unicode and evento.unicode.isprintable():
                            self.campo_busqueda.agregar_caracter(evento.unicode)
                
                elif evento.type == pygame.MOUSEBUTTONDOWN:
                    # Botón salir del programa
                    if hasattr(self, 'boton_salir') and self.boton_salir.verificar_clic(evento.pos):
                        raise CerrarPrograma("Usuario presionó salir del programa")

                    # Verificar clics en campos
                    for campo in self.campos.values():
                        campo.manejar_clic(evento.pos)
                    
                    # Campo de búsqueda
                    self.campo_busqueda.manejar_clic(evento.pos)
                    
                    # Verificar clics en botones
                    if self.boton_buscar.verificar_clic(evento.pos):
                        self.buscar_paciente(tiempo_actual)
                    
                    elif self.boton_registrar.verificar_clic(evento.pos):
                        self.registrar_paciente(tiempo_actual)
                    
                    elif self.boton_continuar.verificar_clic(evento.pos):
                        if self.paciente_actual:
                            # Guardar el nombre del paciente antes de cambiar de ventana
                            self.nombre_paciente_guardado = self.campo_busqueda.obtener_valor()
                            
                            # Abrir ventana del sistema con el diseño exacto de interfas1.py
                            ventana_sistema = VentanaSecundaria(self.paciente_actual)
                            resultado = ventana_sistema.ejecutar()
                            if resultado == False:
                                raise CerrarPrograma("Usuario cerró ventana sistema")
                            # Si no se cerró la ventana, continuar normalmente
                        else:
                            self.mensaje = "Debe buscar o registrar un paciente primero"
                            self.color_mensaje = ROJO
                            self.mostrar_mensaje_tiempo = tiempo_actual + 3000

                # Eventos de arrastre eliminados (modo edición)
            
            # Actualizar hover de botones DESPUÉS de eventos
            self.boton_buscar.verificar_hover(pos_mouse)
            self.boton_registrar.verificar_hover(pos_mouse)
            self.boton_continuar.verificar_hover(pos_mouse)
            
            # Dibujar interfaz
            self.dibujar_interfaz()
            # Overlay de edición eliminado
            
            # Mostrar mensaje si es necesario
            if tiempo_actual < self.mostrar_mensaje_tiempo:
                self.mostrar_mensaje()
            
            # Actualizar pantalla
            pygame.display.flip()
            clock.tick(60)

# CLASE VENTANASECUNDARIA EXACTA DEL ARCHIVO INTERFAS1.PY
class VentanaSecundaria:
    def __init__(self, id_paciente=None):
        self.id_paciente = id_paciente
        # Dimensiones iniciales
        self.ancho_inicial = 1280
        self.alto_inicial = 720
        
        self.ancho, self.alto = ajustar_a_pantalla(self.ancho_inicial, self.alto_inicial, 800, 600)
        # Iniciar en modo ventana maximizada (no fullscreen)
        self.fullscreen = False

        info = pygame.display.Info()
        self.ancho, self.alto = info.current_w, info.current_h
        centrar_ventana(self.ancho, self.alto)
        self.pantalla = pygame.display.set_mode((info.current_w, info.current_h), pygame.RESIZABLE)
        pygame.display.set_caption("Control de Robot Cartesiano")
        # Forzar maximizar en Linux si wmctrl está disponible
        try:
            import subprocess
            subprocess.Popen(['wmctrl', '-r', ':ACTIVE:', '-b', 'add,maximized_vert,maximized_horz'])
        except Exception:
            pass
        
        self.controlador_cnc = ControladorCNC()
        self.conexion_activa = False
        self.estado_conexion = "CNC no conectada"
        self.color_estado = ROJO
        
        # Inicializar gestor de pacientes
        self.gestor_pacientes = GestorPacientes()
        
        # Intentar cargar la fuente DejaVu Sans
        try:
            # Intentar diferentes nombres de fuente para DejaVu Sans
            fuentes_posibles = ["dejavusans", "DejaVuSans", "DejaVu Sans", "dejavu sans"]
            fuente_cargada = False
            
            for nombre_fuente in fuentes_posibles:
                try:
                    self.fuente_dejavu = pygame.font.SysFont(nombre_fuente, 30)
                    # Verificar si la fuente se cargó correctamente probando un carácter
                    test_render = self.fuente_dejavu.render("←", True, NEGRO)
                    fuente_cargada = True
                    print(f"Fuente cargada: {nombre_fuente}")
                    break
                except:
                    continue
            
            if not fuente_cargada:
                # Si no se pudo cargar ninguna variante, usar una fuente predeterminada
                self.fuente_dejavu = pygame.font.Font(None, 30)
                print("No se pudo cargar DejaVu Sans. Usando fuente predeterminada.")
        except:
            self.fuente_dejavu = pygame.font.Font(None, 30)
            print("Error al cargar fuentes. Usando fuente predeterminada.")
        
        # Inicializar botones
        self.inicializar_botones()
        
        # Definir movimientos para cada botón direccional
        # CORRECCIÓN: Estos valores se pasan correctamente al método mover()
        self.movimientos = {
            0: (-1, 1),   # ↖ diagonal superior izquierda
            1: (0, 1),    # +Y movimiento vertical arriba
            2: (1, 1),    # ↗ diagonal superior derecha
            3: (-1, 0),   # -X movimiento horizontal izquierda
            4: (0, 0),    # Home (sin movimiento relativo)
            5: (1, 0),    # +X movimiento horizontal derecha
            6: (-1, -1),  # ↙ diagonal inferior izquierda
            7: (0, -1),   # -Y movimiento vertical abajo
            8: (1, -1)    # ↘ diagonal inferior derecha
        }
        
        # Velocidad del motor
        self.velocidad_actual = 50
        
        # Último tiempo de guardado de posición
        self.ultimo_guardado = 0
        
        # Importar datetime para mostrar fecha y hora
        import datetime
        
    def inicializar_botones(self):
        """Inicializa los botones con las proporciones correctas."""
        # Altura de la barra verde superior
        altura_barra_verde = int(self.alto * 0.1)
        # Altura reservada para la barra inferior permanente
        altura_barra_inferior_px = alto_barra_inferior(self.alto)
        # Offset visual adicional para subir más la barra en esta ventana
        offset_barra_visual = max(48, int(self.alto * 0.10))
        
        # Definir tamaños y márgenes
        ancho_boton_direccional = int(self.ancho * 0.2)
        alto_util = max(altura_barra_verde, self.alto - altura_barra_inferior_px)
        alto_boton_direccional = int(alto_util * 0.08)
        margen = int(self.ancho * 0.02)
        
        # Crear botones de movimiento (3x3 grid)
        self.botones = []
        
        # Textos direccionales para botones de movimiento
        textos_direccion = ["↖", "+Y", "↗", "-X", "Home", "+X", "↙", "-Y", "↘"]
        
        # Posiciones de los botones según la imagen
        posiciones_x = [0, 1, 2, 0, 1, 2, 0, 1, 2]
        posiciones_y = [0, 0, 0, 1, 1, 1, 2, 2, 2]
        
        # Crear botones de movimiento
        for i in range(9):
            x = margen + posiciones_x[i] * (ancho_boton_direccional + margen)
            y = altura_barra_verde + margen + posiciones_y[i] * (alto_boton_direccional + margen)
            self.botones.append(Boton(x, y, ancho_boton_direccional, alto_boton_direccional, textos_direccion[i], VERDE_CLARO, self.fuente_dejavu, VERDE_BOTON))
        
        # Botones adicionales en columna izquierda
        ancho_boton_largo = ancho_boton_direccional * 2 + margen
        x_izquierda = margen
        y_fijar = altura_barra_verde + margen + 3 * (alto_boton_direccional + margen) + margen
        
        # Botón Fijar Origen
        self.boton_fijar_origen = Boton(x_izquierda, y_fijar, ancho_boton_largo, alto_boton_direccional, "Fijar Origen", VERDE_CLARO, self.fuente_dejavu, VERDE_BOTON)
        
        # Botón Paro de Emergencia
        y_emergencia = y_fijar + alto_boton_direccional + margen
        self.boton_emergencia = Boton(x_izquierda, y_emergencia, ancho_boton_largo, alto_boton_direccional, "Paro de Emergencia", ROJO, self.fuente_dejavu, BLANCO)
        
        # Botón Control de Velocidad (único botón debajo de Paro de Emergencia)
        y_velocidad = y_emergencia + alto_boton_direccional + margen
        self.boton_control_velocidad = Boton(x_izquierda, y_velocidad, ancho_boton_largo, alto_boton_direccional, "Control de Velocidad", VERDE_CLARO, self.fuente_dejavu, VERDE_BOTON)
        
        # Botón Reanudar (debajo de Control de Velocidad)
        y_reanudar = y_velocidad + alto_boton_direccional + margen
        self.boton_reanudar = Boton(x_izquierda, y_reanudar, ancho_boton_largo, alto_boton_direccional, "Reanudar", VERDE_CLARO, self.fuente_dejavu, VERDE_BOTON)
        
        # Botones de funciones (lado derecho)
        ancho_boton_derecha = int(self.ancho * 0.2)
        
        # Calcular la posición del panel central para usarla como referencia
        panel_central_x = self.botones[5].rect.x  # Alineado con el botón +X
        panel_central_y = self.botones[7].rect.bottom + 20  # Debajo del botón -Y
        panel_central_ancho = self.botones[5].rect.width  # Mismo ancho que el botón +X
        
        # Calcular el espacio total disponible a la derecha del panel central
        espacio_derecho_total = self.ancho - (panel_central_x + panel_central_ancho)
        
        # Calcular la posición x para centrar los botones de la derecha en el espacio disponible
        x_derecha = panel_central_x + panel_central_ancho + (espacio_derecho_total - ancho_boton_derecha) // 2
        
        # Botón Rutinas
        self.boton_rutinas = Boton(x_derecha, altura_barra_verde + margen, ancho_boton_derecha, alto_boton_direccional, "Rutinas", VERDE_CLARO, self.fuente_dejavu, VERDE_BOTON)
        self.boton_rutinas.fuente_personalizada = pygame.font.Font(None, 18)
        
        # Botón Gráficas
        y_graficas = altura_barra_verde + margen + alto_boton_direccional + margen
        self.boton_graficas = Boton(x_derecha, y_graficas, ancho_boton_derecha, alto_boton_direccional * 2, "Gráficas de Esfuerzo Muscular", VERDE_CLARO, self.fuente_dejavu, VERDE_BOTON)
        self.boton_graficas.fuente_personalizada = pygame.font.Font(None, 18)
        
        # Botón Progreso
        y_progreso = y_graficas + alto_boton_direccional * 2 + margen
        self.boton_progreso = Boton(x_derecha, y_progreso, ancho_boton_derecha, alto_boton_direccional, "Progreso del Paciente", VERDE_CLARO, self.fuente_dejavu, VERDE_BOTON)
        self.boton_progreso.fuente_personalizada = pygame.font.Font(None, 18)
        
        # Botón Conectar CNC
        y_conectar = y_progreso + alto_boton_direccional + margen
        self.boton_conectar = Boton(x_derecha, y_conectar, ancho_boton_derecha, alto_boton_direccional, "Conectar CNC", VERDE_CLARO, self.fuente_dejavu, VERDE_BOTON)
        self.boton_conectar.fuente_personalizada = pygame.font.Font(None, 18)
        
        # Botón Volver a Login
        y_volver = y_conectar + alto_boton_direccional + margen
        # Asegurar que no invada la barra inferior
        limite_inferior = self.alto - altura_barra_inferior_px - offset_barra_visual - alto_boton_direccional - margen
        if y_volver > limite_inferior:
            y_volver = max(altura_barra_verde + margen, limite_inferior)
        self.boton_volver = Boton(x_derecha, y_volver, ancho_boton_derecha, alto_boton_direccional, "Volver a Login", VERDE_CLARO, self.fuente_dejavu, VERDE_BOTON)
        self.boton_volver.fuente_personalizada = pygame.font.Font(None, 18)
        
        # Guardar proporciones para redimensionamiento
        for boton in self.botones:
            boton.actualizar_proporciones(self.ancho, self.alto)
            
        for boton in [self.boton_fijar_origen, self.boton_emergencia, self.boton_control_velocidad, 
                     self.boton_reanudar, self.boton_rutinas, self.boton_graficas, self.boton_progreso, 
                     self.boton_conectar, self.boton_volver]:
            boton.actualizar_proporciones(self.ancho, self.alto)
    
    def redimensionar(self, nuevo_ancho, nuevo_alto):
        """Redimensiona todos los elementos de la interfaz."""
        # Actualizar dimensiones y recalcular layout para mantener alineaciones
        self.ancho, self.alto = nuevo_ancho, nuevo_alto

        # Preservar el texto del botón conectar (puede cambiar a "Desconectar CNC")
        texto_conectar = getattr(self, 'boton_conectar', None).texto if hasattr(self, 'boton_conectar') else "Conectar CNC"

        # Reconstruir los botones con las nuevas dimensiones para evitar desajustes
        self.inicializar_botones()

        # Restaurar texto de conectar si cambió por estado de conexión
        if hasattr(self, 'boton_conectar') and texto_conectar:
            self.boton_conectar.texto = texto_conectar
        
    def ejecutar(self):
        # Respetar configuración al iniciar ejecución
        info = pygame.display.Info()
        self.ancho, self.alto = info.current_w, info.current_h
        centrar_ventana(self.ancho, self.alto)
        self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
        
        clock = pygame.time.Clock()
        import datetime
        margen_h = int(self.ancho * 0.02)
        texto_titulo = "Control de Robot Cartesiano"
        fuente_titulo = ajustar_fuente_a_ancho(texto_titulo, int(self.ancho * 0.7), int(self.alto * 0.06), 14)
        titulo = fuente_titulo.render(texto_titulo, True, BLANCO)
        ejecutando = True
        while ejecutando:
            self.pantalla.fill(VERDE_CLARO)
            altura_barra_verde = int(self.alto * 0.1)
            pygame.draw.rect(self.pantalla, VERDE_OSCURO, (0, 0, self.ancho, altura_barra_verde))
            # Solo actualizar la fecha/hora en cada frame
            fecha_hora = datetime.datetime.now().strftime("%d/%m/%Y - %H:%M:%S")
            fuente_fecha = ajustar_fuente_a_ancho(fecha_hora, int(self.ancho * 0.35), int(self.alto * 0.035), 12)
            texto_fecha = fuente_fecha.render(fecha_hora, True, BLANCO)
            rect_fecha = texto_fecha.get_rect(right=self.ancho - margen_h, centery=altura_barra_verde // 2)
            self.pantalla.blit(texto_fecha, rect_fecha)
            # Título ocupa el espacio restante
            espacio_titulo = self.ancho - (margen_h + texto_fecha.get_width() + margen_h)
            rect_titulo = titulo.get_rect(center=((espacio_titulo // 2) + margen_h, altura_barra_verde // 2))
            self.pantalla.blit(titulo, rect_titulo)
            pos_mouse = pygame.mouse.get_pos()
            for evento in pygame.event.get():
                if evento.type == pygame.QUIT:
                    if self.conexion_activa:
                        self.controlador_cnc.desconectar()
                    raise CerrarPrograma("Usuario cerró la ventana")
                if evento.type == pygame.VIDEORESIZE:
                    nuevo_w, nuevo_h = ajustar_a_pantalla(evento.w, evento.h, 800, 600)
                    self.redimensionar(nuevo_w, nuevo_h)
                if evento.type == pygame.KEYDOWN:
                    if evento.key == pygame.K_F11:
                        self.fullscreen = not self.fullscreen
                        if self.fullscreen:
                            self.pantalla = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                            info = pygame.display.Info()
                            self.redimensionar(info.current_w, info.current_h)
                        else:
                            w, h = ajustar_a_pantalla(self.ancho_inicial, self.alto_inicial, 800, 600)
                            self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                            self.redimensionar(w, h)
                        continue
                    if evento.key == pygame.K_ESCAPE and self.fullscreen:
                        self.fullscreen = False
                        w, h = ajustar_a_pantalla(self.ancho_inicial, self.alto_inicial, 800, 600)
                        self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                        self.redimensionar(w, h)
                        continue
                if evento.type == pygame.MOUSEBUTTONDOWN:
                    if self.boton_volver.verificar_clic(pos_mouse):
                        if self.conexion_activa:
                            self.controlador_cnc.desconectar()
                        # Cerrar esta ventana y volver a la principal (Registro del paciente)
                        ejecutando = False
                        break
                    
                    # Manejar clic en botón conectar
                    if self.boton_conectar.verificar_clic(pos_mouse):
                        # Re-evaluar conexión real antes de actuar
                        self.conexion_activa = bool(self.controlador_cnc and self.controlador_cnc.esta_conectado())
                        if not self.conexion_activa:
                            self.estado_conexion = "Conectando..."
                            self.color_estado = NARANJA
                            self.dibujar_interfaz(pos_mouse)
                            pygame.display.flip()
                            
                            if self.controlador_cnc.conectar():
                                self.conexion_activa = True
                                self.boton_conectar.texto = "Desconectar CNC"
                                self.estado_conexion = "CNC conectada"
                                self.color_estado = VERDE
                                self.velocidad_actual = self.controlador_cnc.velocidad_actual
                            else:
                                self.estado_conexion = "CNC no conectada"
                                self.color_estado = ROJO
                        else:
                            self.controlador_cnc.desconectar()
                            self.conexion_activa = False
                            self.boton_conectar.texto = "Conectar CNC"
                            self.estado_conexion = "CNC no conectada"
                            self.color_estado = ROJO
                    
                    # Manejar clic en botón fijar origen
                    if self.boton_fijar_origen.verificar_clic(pos_mouse):
                        if self.conexion_activa:
                            if self.controlador_cnc.establecer_origen():
                                mostrar_aviso_sistema("Éxito", "Origen establecido correctamente en la posición actual.")
                                try:
                                    # Sincronizar flags locales tras G92
                                    self.controlador_cnc.origen_establecido = True
                                    # Activar límites estándar (0..40) al fijar el origen
                                    if hasattr(self.controlador_cnc, 'activar_limites_estandar'):
                                        self.controlador_cnc.activar_limites_estandar()
                                    else:
                                        self.controlador_cnc.limites_activos = True
                                    # Actualizar el texto de estado para reflejar límites activos
                                    self.estado_conexion = "CNC conectada - Límites activos"
                                except Exception:
                                    pass
                                # Reenfocar la ventana de pygame tras cerrar el popup de Tk
                                try:
                                    centrar_ventana(self.ancho, self.alto)
                                    self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
                                except Exception:
                                    pass
                            else:
                                mostrar_aviso_sistema("Error", "No se pudo establecer el origen.")
                                try:
                                    centrar_ventana(self.ancho, self.alto)
                                    self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
                                except Exception:
                                    pass
                        else:
                            mostrar_aviso_sistema("Error", "CNC no conectada. Conéctese primero.")
                            try:
                                centrar_ventana(self.ancho, self.alto)
                                self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
                            except Exception:
                                pass
                    
                    # Manejar clic en botón control de velocidad
                    if self.boton_control_velocidad.verificar_clic(pos_mouse):
                        # Abrir la ventana de configuración interna en vez de depender de interfas2.py
                        ventana_config = VentanaConfiguracionRutina(self.controlador_cnc, self.conexion_activa)
                        ventana_config.ejecutar()
                        centrar_ventana(self.ancho, self.alto)
                        self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
                    
                    # Manejar clic en botón reanudar
                    if hasattr(self, 'boton_reanudar') and self.boton_reanudar.verificar_clic(pos_mouse):
                        if self.conexion_activa:
                            if self.controlador_cnc.reanudar_movimiento():
                                mostrar_aviso_sistema("Reanudar", "Movimiento reanudado (Cycle Start).")
                            else:
                                mostrar_aviso_sistema("Error", "No se pudo reanudar el movimiento.")
                        else:
                            mostrar_aviso_sistema("Error", "CNC no conectada. Conéctese primero.")
                    
                    # Manejar clic en botón de emergencia
                    if self.boton_emergencia.verificar_clic(pos_mouse):
                        if self.conexion_activa:
                            if self.controlador_cnc.paro_emergencia():
                                mostrar_aviso_sistema("Emergencia", "Movimiento detenido (Feed Hold). Origen preservado.")
                            else:
                                mostrar_aviso_sistema("Error", "No se pudo detener de forma segura.")
                        else:
                            mostrar_aviso_sistema("Error", "CNC no conectada. Conéctese primero.")
                    
                    # Manejar clics en botones de rutinas y funciones
                    if self.boton_rutinas.verificar_clic(pos_mouse):
                        # Abrir la ventana de Rutinas (menú 1) para mostrar las 5 rutinas por zona
                        try:
                            # Asegurar foco de la ventana principal antes de abrir Rutinas
                            centrar_ventana(self.ancho, self.alto)
                            self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
                            conexion_real = bool(self.controlador_cnc and self.controlador_cnc.esta_conectado())
                            ventana_rutina = VentanaRutina(1, self.controlador_cnc, conexion_real, self.id_paciente, self.gestor_pacientes)
                            ventana_rutina.ejecutar()
                        except CerrarPrograma:
                            # Propagar la excepción de cierre para cerrar el programa
                            raise
                        except Exception as e:
                            try:
                                mostrar_aviso_sistema("Error", f"No se pudo abrir Rutinas: {e}")
                            except Exception:
                                print(f"Error al abrir Rutinas: {e}")
                        finally:
                            centrar_ventana(self.ancho, self.alto)
                            self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)

                    if self.boton_graficas.verificar_clic(pos_mouse):
                        try:
                            conexion_real = bool(self.controlador_cnc and self.controlador_cnc.esta_conectado())
                            ventana_rutina = VentanaRutina(2, self.controlador_cnc, conexion_real, self.id_paciente, self.gestor_pacientes)
                            ventana_rutina.ejecutar()
                        except CerrarPrograma:
                            # Propagar la excepción de cierre para cerrar el programa
                            raise
                        except Exception as e:
                            try:
                                mostrar_aviso_sistema("Error", f"No se pudo abrir Gráficas: {e}")
                            except Exception:
                                print(f"Error al abrir Gráficas: {e}")
                        finally:
                            centrar_ventana(self.ancho, self.alto)
                            self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
                    
                    if self.boton_progreso.verificar_clic(pos_mouse):
                        try:
                            conexion_real = bool(self.controlador_cnc and self.controlador_cnc.esta_conectado())
                            ventana_rutina = VentanaRutina(3, self.controlador_cnc, conexion_real, self.id_paciente, self.gestor_pacientes)
                            ventana_rutina.ejecutar()
                        except CerrarPrograma:
                            # Propagar la excepción de cierre para cerrar el programa
                            raise
                        except Exception as e:
                            try:
                                mostrar_aviso_sistema("Error", f"No se pudo abrir Progreso: {e}")
                            except Exception:
                                print(f"Error al abrir Progreso: {e}")
                        finally:
                            centrar_ventana(self.ancho, self.alto)
                            self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
                    
                    # CORRECCIÓN: Manejar clics en botones de movimiento con debugging
                    for i, boton in enumerate(self.botones):
                        if boton.verificar_clic(pos_mouse):
                            if self.conexion_activa:
                                if i == 4:  # Botón ORIGEN (Home)
                                    if getattr(self.controlador_cnc, 'origen_establecido', False):
                                        print("Ejecutando comando Home")
                                        self.controlador_cnc.ir_a_home()
                                    else:
                                        print("Home bloqueado: origen no establecido")
                                        mostrar_aviso_sistema("Aviso", "Aún no se ha establecido Punto de Origen")
                                else:
                                    dir_x, dir_y = self.movimientos[i]
                                    # DEBUGGING: Imprimir valores para verificar
                                    print(f"Botón {i} presionado: dir_x={dir_x}, dir_y={dir_y}, texto='{boton.texto}'")
                                    # Llamar al método mover (el controlador validará límites)
                                    self.controlador_cnc.mover(dir_x, dir_y)
                            else:
                                print("CNC no conectada. No se puede mover.")
            
            self.dibujar_interfaz(pos_mouse)
            pygame.display.flip()
            clock.tick(60)
        
        return not ejecutando  # Retorna False si se cerró la ventana
    
    def dibujar_interfaz(self, pos_mouse):
        # Altura de la barra verde superior
        altura_barra_verde = int(self.alto * 0.1)
        margen = int(self.ancho * 0.02)
        
        # Actualizar estado hover de todos los botones
        for boton in self.botones:
            boton.verificar_hover(pos_mouse)
        
        # Verificar hover y dibujar botones
        botones_a_verificar = [
            self.boton_fijar_origen, self.boton_emergencia, self.boton_control_velocidad,
            getattr(self, 'boton_reanudar', None), self.boton_rutinas, self.boton_graficas, self.boton_progreso,
            self.boton_conectar, self.boton_volver
        ]
        
        # Verificar hover y dibujar solo los botones que no son None
        for btn in botones_a_verificar:
            if btn is not None:  # Asegurarse de que el botón existe
                btn.verificar_hover(pos_mouse)
                btn.dibujar(self.pantalla)
        
        # Dibujar botones de movimiento
        for boton in self.botones:
            boton.dibujar(self.pantalla)
        
        # Definir el área del panel central - MODIFICADO PARA UBICARLO EN LA POSICIÓN INDICADA
        # Ahora el panel se ubicará alineado con la columna de botones que contiene +X
        panel_central_x = self.botones[5].rect.x  # Alineado con el botón +X
        panel_central_y = self.botones[7].rect.bottom + 20  # Debajo del botón -Y
        
        # MODIFICACIÓN: Usar el mismo ancho que el botón +X
        panel_central_ancho = self.botones[5].rect.width
        
        # MODIFICACIÓN: Extender la altura hasta el botón Control de Velocidad
        panel_central_alto = (self.boton_control_velocidad.rect.bottom - panel_central_y + 20)
        # No invadir la barra inferior (considerando desplazamiento de la barra)
        # Mantener el mismo offset visual definido en inicializar_botones si existe
        try:
            offset_barra = max(48, int(self.alto * 0.10))
        except Exception:
            offset_barra = max(24, int(self.alto * 0.05))
        altura_barra_inferior_px = alto_barra_inferior(self.alto)
        max_alto_panel = max(50, self.alto - altura_barra_inferior_px - offset_barra - panel_central_y - 10)
        panel_central_alto = min(panel_central_alto, max_alto_panel)
        
        # Dibujar el panel central (área de trabajo)
        panel_central = pygame.Rect(panel_central_x, panel_central_y, panel_central_ancho, panel_central_alto)
        pygame.draw.rect(self.pantalla, VERDE_CLARO, panel_central)
        pygame.draw.rect(self.pantalla, VERDE_BORDE, panel_central, 2)
        
        # Mostrar información en el panel central
        fuente_info = pygame.font.Font(None, 24)  # Tamaño de fuente para ajustar al panel
        
        # Mostrar estado de conexión
        if not self.conexion_activa:
            texto_estado = fuente_info.render("CNC no conectada", True, ROJO)
            rect_estado = texto_estado.get_rect(center=(panel_central.centerx, panel_central.y + panel_central.height * 0.25))
            self.pantalla.blit(texto_estado, rect_estado)
            
            texto_instruccion = fuente_info.render("Presione 'Conectar CNC'", True, VERDE_BOTON)
            rect_instruccion = texto_instruccion.get_rect(center=(panel_central.centerx, panel_central.y + panel_central.height * 0.5))
            self.pantalla.blit(texto_instruccion, rect_instruccion)
            
            texto_coords = fuente_info.render("para ver coordenadas", True, VERDE_BOTON)
            rect_coords = texto_coords.get_rect(center=(panel_central.centerx, panel_central.y + panel_central.height * 0.75))
            self.pantalla.blit(texto_coords, rect_coords)
        
        # Mostrar coordenadas si está conectado
        if self.conexion_activa:
            # Usar coordenadas lógicas (0..40) para que el origen se muestre como 0,0
            try:
                x_log, y_log = self.controlador_cnc.obtener_posicion_logica()
            except Exception:
                x_log, y_log = self.controlador_cnc.posicion_x, self.controlador_cnc.posicion_y
            texto_coords = fuente_info.render(f"X: {x_log:.2f}", True, VERDE_BOTON)
            rect_coords = texto_coords.get_rect(center=(panel_central.centerx, panel_central.y + panel_central.height * 0.4))
            self.pantalla.blit(texto_coords, rect_coords)
            
            texto_coords_y = fuente_info.render(f"Y: {y_log:.2f}", True, VERDE_BOTON)
            rect_coords_y = texto_coords_y.get_rect(center=(panel_central.centerx, panel_central.y + panel_central.height * 0.6))
            self.pantalla.blit(texto_coords_y, rect_coords_y)
        
        # Barra inferior permanente con desplazamiento hacia arriba
        # Preparar estado para barra inferior con indicador HOLD si aplica
        estado_base = getattr(self, 'estado_conexion', None)
        if self.conexion_activa and getattr(self.controlador_cnc, 'en_hold', False):
            estado_base = f"{estado_base or 'CNC conectada'} - HOLD"
        
        dibujar_barra_inferior(
            self.pantalla, self.ancho, self.alto,
            self.conexion_activa,
            estado_base,
            getattr(self, 'controlador_cnc', None),
            offset_px=offset_barra
        )

class VentanaRutina:
    def __init__(self, boton_id, controlador_cnc=None, conexion_activa=False, id_paciente=None, gestor_pacientes=None):
        self.boton_id = boton_id
        self.controlador_cnc = controlador_cnc
        self.conexion_activa = conexion_activa
        self.id_paciente = id_paciente
        self.gestor_pacientes = gestor_pacientes
        # No invertir coordenadas por software; 0..40 crece desde el origen
        self.invertir_rutinas = False
        
        self.colores_fondo = {
            1: VERDE, 2: (20, 60, 40),
            3: NARANJA, 4: ROSA, 5: MORADO, 6: CYAN
        }
        
        if self.boton_id == 2:
            self.ancho, self.alto = ajustar_a_pantalla(1400, 800, 1000, 700)
            self.es_modo_grafica = True
            
            # Inicializar Arduino para sensores ECG
            self.arduino_reader = ArduinoSensorReader()
            if self.arduino_reader.conectar():
                print("[ECG] Arduino conectado correctamente")
            else:
                print("[ECG] Arduino no conectado - usando simulación")
            self.gpio_disponible = False  # Ya no usamos GPIO
            
            self.max_puntos = 100
            self.datos_hombro = np.zeros(self.max_puntos)
            self.datos_antebrazo = np.zeros(self.max_puntos)
            self.eje_tiempo = np.linspace(0, 10, self.max_puntos)
            
            self.color_fondo = (20, 60, 40)
            self.color_linea = DORADO
            
            self.superficie_grafica_hombro = None
            self.superficie_grafica_antebrazo = None
            
            self.ancho_boton, self.alto_boton = 180, 45
            self.margen, self.espaciado = 30, 15

            self.area_graficas_ancho = int(self.ancho * 0.68)
            self.inicio_botones_x = self.area_graficas_ancho + 20
            
            # Color de texto blanco para todos los botones
            color_texto_blanco = (255, 255, 255)

            self.boton_captura = Boton(
                self.inicio_botones_x,
                self.margen + 60,
                self.ancho_boton, self.alto_boton,
                "Iniciar Captura", VERDE, None, color_texto_blanco
            )

            self.boton_cambiar = Boton(
                self.inicio_botones_x,
                self.margen + 60 + self.alto_boton + self.espaciado,
                self.ancho_boton, self.alto_boton,
                "Mostrar Ambos", AZUL, None, color_texto_blanco
            )

            # Color café (marrón) para el botón Guardar Datos
            color_cafe = (139, 69, 19)  # Café/marrón
            
            self.boton_guardar = Boton(
                self.inicio_botones_x,
                self.margen + 60 + 2 * (self.alto_boton + self.espaciado),
                self.ancho_boton, self.alto_boton,
                "Guardar Datos", color_cafe, None, color_texto_blanco
            )

            self.boton_comparar = Boton(
                self.inicio_botones_x,
                self.margen + 60 + 3 * (self.alto_boton + self.espaciado),
                self.ancho_boton, self.alto_boton,
                "Comparar Progreso", MORADO, None, color_texto_blanco
            )

            self.boton_regresar = Boton(
                self.inicio_botones_x,
                max(60, self.alto - self.alto_boton - self.margen - alto_barra_inferior(self.alto) - 8),
                self.ancho_boton, self.alto_boton,
                "Regresar", ROJO, None, color_texto_blanco
            )
            # Guardar proporciones iniciales para responder mejor a redimensionamientos
            for btn in [self.boton_captura, self.boton_cambiar, self.boton_guardar, self.boton_comparar, self.boton_regresar]:
                btn.actualizar_proporciones(self.ancho, self.alto)
            
            # Iniciar captura automáticamente al abrir la ventana
            self.capturando = True  # Cambiado de False a True para iniciar automáticamente
            self.inicio_sesion = time.time()
            self.modo_visualizacion = "ambos"
            self.ultimo_tiempo_captura = 0
            self.intervalo_captura = 100
            
            self.datos_sesion_hombro = []
            self.datos_sesion_antebrazo = []
            
            # Actualizar texto del botón para reflejar que está capturando
            self.boton_captura.texto = "Detener Captura"
            self.boton_captura.color = ROJO
        else:
            # Dimensiones iniciales: maximizar ventana para Rutinas (id=1) y Progreso del Paciente (id=3)
            if self.boton_id in (1, 3):
                info = pygame.display.Info()
                self.ancho_inicial = max(900, info.current_w)
                self.alto_inicial = max(600, info.current_h)
            else:
                self.ancho_inicial = 400
                self.alto_inicial = 500

            self.ancho = self.ancho_inicial
            self.alto = self.alto_inicial

            # Iniciar ventana en tamaño de pantalla (no fullscreen) para Rutinas y Progreso
            if self.boton_id in (1, 3):
                self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
                self.fullscreen = False
            else:
                centrar_ventana(self.ancho, self.alto)
                self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
            
            # Intentar cargar la fuente DejaVu Sans
            try:
                # Intentar diferentes nombres de fuente para DejaVu Sans
                fuentes_posibles = ["dejavusans", "DejaVuSans", "DejaVu Sans", "dejavu sans"]
                fuente_cargada = False
                
                for nombre_fuente in fuentes_posibles:
                    try:
                        self.fuente_dejavu = pygame.font.SysFont(nombre_fuente, 30)
                        # Verificar si la fuente se cargó correctamente probando un carácter
                        test_render = self.fuente_dejavu.render("←", True, NEGRO)
                        fuente_cargada = True
                        print(f"Fuente cargada: {nombre_fuente}")
                        break
                    except:
                        continue
                
                if not fuente_cargada:
                    # Si no se pudo cargar ninguna variante, usar una fuente predeterminada
                    self.fuente_dejavu = pygame.font.Font(None, 30)
                    print("No se pudo cargar DejaVu Sans. Usando fuente predeterminada.")
            except:
                self.fuente_dejavu = pygame.font.Font(None, 30)
                print("Error al cargar fuentes. Usando fuente predeterminada.")
            
            # Nombres de menús
            self.nombres_menus = {
                1: "Rutinas",
                2: "Gráficas de Esfuerzo Muscular",
                3: "Progreso del Paciente",
                4: "Configuración",
                5: "Reportes",
                6: "Ayuda"
            }
            
            pygame.display.set_caption(f"{self.nombres_menus.get(boton_id, f'Menú {boton_id}')}")
            
            # Colores para los diferentes menús
            self.colores_fondo = {
                1: VERDE_CLARO, 2: VERDE_CLARO, 3: VERDE_CLARO,
                4: VERDE_CLARO, 5: VERDE_CLARO, 6: VERDE_CLARO
            }
            self.color_fondo = self.colores_fondo.get(boton_id, VERDE_CLARO)
            
            self.inicializar_botones()
            # Selector de zona (Hombro/Antebrazo) para Rutinas (boton_id==1)
            if self.boton_id == 1:
                fuente_sel = pygame.font.Font(None, 26)
                self.radio_hombro = RadioButton(0, 0, 12, "Hombro", seleccionado=True)
                self.radio_antebrazo = RadioButton(0, 0, 12, "Antebrazo", seleccionado=False)
                # Posiciones se ajustan en redimensionar()
                self.zona_actual = 'Hombro'
                # Selector de mano (Derecha/Izquierda)
                self.radio_derecha = RadioButton(0, 0, 12, "Mano Derecha", seleccionado=True)
                self.radio_izquierda = RadioButton(0, 0, 12, "Mano Izquierda", seleccionado=False)
                self.mano_actual = 'Derecha'
                # Dificultad 1..5
                self.dificultad = 3
                # No mostrar símbolo de porcentaje; solo número (se dibuja aparte)
                self.slider_dificultad = Slider(0, 0, 200, 28, valor_min=1, valor_max=5, valor_inicial=self.dificultad, unidad="")
                # Velocidad en tiempo real (10..200 %) para override de feed
                velocidad_ini = 50
                try:
                    if self.controlador_cnc:
                        velocidad_ini = int(getattr(self.controlador_cnc, 'velocidad_actual', 50))
                except Exception:
                    pass
                self.velocidad_actual = velocidad_ini
                # No mostrar texto de unidad/porcentaje en el dibujado del slider
                self.slider_velocidad_rutina = Slider(0, 0, 200, 22, valor_min=10, valor_max=200, valor_inicial=self.velocidad_actual, unidad="")
                # Botones de Paro y Reanudar en Rutinas con colores modernos y tamaño más grande
                try:
                    fuente_btn_accion = pygame.font.Font(None, 24)  # Fuente más grande
                except Exception:
                    fuente_btn_accion = None
                color_texto_blanco = (255, 255, 255)
                self.boton_paro = Boton(0, 0, 240, 38, "Paro Emergencia", (231, 76, 60), fuente_btn_accion, color_texto_blanco)  # Rojo moderno - más ancho
                self.boton_reanudar_mov = Boton(0, 0, 240, 38, "Reanudar", (46, 204, 113), fuente_btn_accion, color_texto_blanco)  # Verde brillante - más ancho
                # Botón para consultar/ver firmware
                try:
                    fuente_btn_fw = pygame.font.Font(None, 22)  # Fuente más grande
                except Exception:
                    fuente_btn_fw = None
                self.boton_ver_fw = Boton(0, 0, 160, 32, "Ver firmware", (155, 89, 182), fuente_btn_fw, color_texto_blanco)  # Morado - se reposicionará abajo
                # Botones para guardar y restablecer configuración $$
                try:
                    fuente_btn_cfg = pygame.font.Font(None, 22)  # Fuente más grande
                except Exception:
                    fuente_btn_cfg = None
                # Colores modernos para botones de configuración CNC
                color_texto_blanco = (255, 255, 255)
                self.boton_guardar_cfg = Boton(0, 0, 160, 32, "Guardar $$", (241, 196, 15), fuente_btn_cfg, color_texto_blanco)  # Amarillo dorado - más grande
                self.boton_rest_cfg = Boton(0, 0, 180, 32, "Restablecer $$", (52, 152, 219), fuente_btn_cfg, color_texto_blanco)  # Azul brillante - más grande
            self.es_modo_grafica = False
        # Micropaso por defecto para generadores (mm)
        try:
            if self.controlador_cnc is not None:
                setattr(self, 'micro_step_mm', 0.5)
            else:
                setattr(self, 'micro_step_mm', 0.5)
        except Exception:
            self.micro_step_mm = 0.5
        # Aviso discreto en UI (no modal) para cancelaciones por límite
        self._aviso_limite_mensaje = ""
        self._aviso_limite_expira_ms = 0
        
        # Carpeta para rutinas G-code
        self.carpeta_gcode = os.path.join(BASE_DIR, 'gcode')
        try:
            os.makedirs(self.carpeta_gcode, exist_ok=True)
        except Exception as e:
            print(f"No se pudo crear carpeta gcode: {e}")
        # Rutas de archivos gcode (deshabilitadas para rutinas predefinidas)
        self.rutas_gcode = {}
        # Archivo JSON para rutinas definidas por el usuario
        self.archivo_rutinas_usuario = os.path.join(BASE_DIR, 'rutinas_usuario.json')
        self.rutinas_usuario = {}
        try:
            if os.path.exists(self.archivo_rutinas_usuario):
                with open(self.archivo_rutinas_usuario, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.rutinas_usuario = data
        except Exception as e:
            print(f"No se pudo cargar rutinas de usuario: {e}")
        
        # Variables para captura de ECG durante rutinas
        self.captura_ecg_activa = False
        self.datos_ecg_hombro_rutina = []
        self.datos_ecg_antebrazo_rutina = []
        self.tiempo_inicio_rutina = None
        self.nombre_rutina_actual = ""
        self.sensor_ecg = None  # Instancia de ArduinoSensorReader

        # Inicializar sensor ECG si estamos en ventana de Rutinas (boton_id == 1)
        if self.boton_id == 1:
            self._inicializar_sensor_ecg()

    def _inicializar_sensor_ecg(self):
        """Inicializa el sensor ECG a través de Arduino."""
        if self.sensor_ecg is None:
            self.sensor_ecg = ArduinoSensorReader()
            self.sensor_ecg.conectar()
        if not self.sensor_ecg.conectado:
            print("[ECG] No se pudo conectar al sensor ECG.")
            self.sensor_ecg = None
        else:
            print("[ECG] Sensor conectado y listo para captura.")

    def _leer_sensor_ecg(self):
        """Lee los datos del sensor ECG y los agrega a las listas de captura."""
        if not self.captura_ecg_activa or not self.sensor_ecg:
            return
        
        try:
            # Los datos ya se están leyendo en un hilo separado.
            # Aquí solo los agregamos a la lista de la rutina si la captura está activa.
            # Para no duplicar datos, solo tomamos los más recientes que no hemos procesado.
            
            datos_hombro = self.sensor_ecg.obtener_datos_hombro()
            datos_antebrazo = self.sensor_ecg.obtener_datos_antebrazo()

            # Simplemente tomamos el último valor disponible para mantenerlo simple
            if datos_hombro:
                self.datos_ecg_hombro_rutina.append(datos_hombro[-1])
            if datos_antebrazo:
                self.datos_ecg_antebrazo_rutina.append(datos_antebrazo[-1])

        except Exception as e:
            print(f"[ECG] Error al leer sensores durante rutina: {e}")

    def _iniciar_captura_ecg(self, nombre_rutina):
        """Inicia la captura de datos ECG."""
        self.captura_ecg_activa = True
        self.datos_ecg_hombro_rutina = []
        self.datos_ecg_antebrazo_rutina = []
        self.tiempo_inicio_rutina = time.time()
        self.nombre_rutina_actual = nombre_rutina
        print(f"[ECG] Captura iniciada para rutina: {nombre_rutina}")

    def _detener_y_guardar_captura_ecg(self):
        """Detiene la captura y guarda los datos automáticamente."""
        if not self.captura_ecg_activa:
            return
        
        self.captura_ecg_activa = False
        
        # Calcular estadísticas
        if len(self.datos_ecg_hombro_rutina) > 0:
            esfuerzo_hombro_promedio = sum(self.datos_ecg_hombro_rutina) / len(self.datos_ecg_hombro_rutina)
        else:
            esfuerzo_hombro_promedio = 0
        
        if len(self.datos_ecg_antebrazo_rutina) > 0:
            esfuerzo_antebrazo_promedio = sum(self.datos_ecg_antebrazo_rutina) / len(self.datos_ecg_antebrazo_rutina)
        else:
            esfuerzo_antebrazo_promedio = 0
        
        duracion_minutos = (time.time() - self.tiempo_inicio_rutina) / 60.0 if self.tiempo_inicio_rutina else 0
        
        if self.gestor_pacientes and self.id_paciente:
            if len(self.datos_ecg_hombro_rutina) > 0 or len(self.datos_ecg_antebrazo_rutina) > 0:
                try:
                    observaciones = f"Rutina: {self.nombre_rutina_actual}"
                    exito = self.gestor_pacientes.guardar_sesion(
                        self.id_paciente,
                        esfuerzo_hombro_promedio,
                        esfuerzo_antebrazo_promedio,
                        duracion_minutos,
                        observaciones
                    )
                    
                    if exito:
                        print(f"[ECG] Sesión guardada - Hombro: {esfuerzo_hombro_promedio:.1f}, Antebrazo: {esfuerzo_antebrazo_promedio:.1f}, Duración: {duracion_minutos:.2f} min")
                        try:
                            mostrar_aviso_sistema("Datos Guardados", f"Sesión guardada automáticamente\nHombro: {esfuerzo_hombro_promedio:.1f}\nAntebrazo: {esfuerzo_antebrazo_promedio:.1f}")
                        except Exception:
                            pass
                    else:
                        print("[ECG] Error al guardar sesión")
                except Exception as e:
                    print(f"[ECG] Error al guardar sesión: {e}")
            else:
                print("[ECG] Rutina completada sin captura de datos (sensor no disponible o sin datos).")
        else:
            print("[ECG] Rutina completada sin paciente activo - datos no guardados.")

    def _key_rutina(self, boton_id: int, subrutina: int, zona: str | None = None) -> str:
        try:
            if zona and isinstance(zona, str) and zona.strip():
                return f"{int(boton_id)}-{int(subrutina)}-{zona}"
            return f"{int(boton_id)}-{int(subrutina)}"
        except Exception:
            return f"{boton_id}-{subrutina}-{zona or ''}"

    def obtener_rutina_usuario(self, boton_id: int, subrutina: int, zona: str | None = None):
        try:
            # Preferir clave específica por zona; si no existe, usar genérica
            key_z = self._key_rutina(boton_id, subrutina, zona)
            key_g = self._key_rutina(boton_id, subrutina, None)
            raw = self.rutinas_usuario.get(key_z)
            if raw is None:
                raw = self.rutinas_usuario.get(key_g, [])
            out = []
            for l in raw or []:
                s = limpiar_linea_gcode(l)
                if s:
                    out.append(s)
            return out
        except Exception:
            return []

    def guardar_rutina_usuario(self, boton_id: int, subrutina: int, lineas: list[str], zona: str | None = None):
        try:
            key = self._key_rutina(boton_id, subrutina, zona)
            self.rutinas_usuario[key] = list(lineas or [])
            with open(self.archivo_rutinas_usuario, 'w') as f:
                json.dump(self.rutinas_usuario, f, indent=2)
            return True
        except Exception as e:
            print(f"No se pudo guardar rutina de usuario {boton_id}-{subrutina} ({zona or 'genérica'}): {e}")
            return False

    def inicializar_botones(self):
        """Inicializa los botones con las proporciones correctas."""
        # Para Progreso del Paciente (id=3), usar botones centrados y más grandes
        if self.boton_id == 3:
            # Dimensiones mejoradas para "Progreso del Paciente"
            ancho_boton = 260
            alto_boton = 60
            espaciado = 25
            margen_superior = 120  # Más espacio para el título
            
            # Calcular posición centrada horizontalmente
            x_centrado = (self.ancho - ancho_boton) // 2
            
            # Fuente más legible
            fuente_botones = pygame.font.Font(None, 26)
            
            # Colores modernos y atractivos para fondos
            colores_fondo = [
                (46, 204, 113),   # Verde brillante - Ver Progreso
                (52, 152, 219),   # Azul brillante - Comparar Sesiones
                (155, 89, 182),   # Morado - Exportar Reporte
                (241, 196, 15)    # Amarillo dorado - Configurar Metas
            ]
            
            # Colores de texto contrastantes (blanco para todos)
            color_texto = (255, 255, 255)  # Blanco para mejor legibilidad
            
            # Nombres de botones
            nombres_subrutinas = ["Ver Progreso", "Comparar Sesiones", "Exportar Reporte", "Configurar Metas"]
            
            # Crear botones centrados
            self.botones = []
            for i in range(4):
                y = margen_superior + i * (alto_boton + espaciado)
                self.botones.append(
                    Boton(x_centrado, y, ancho_boton, alto_boton, 
                          nombres_subrutinas[i], colores_fondo[i], 
                          fuente_botones, color_texto)
                )
            
            # Botón "Volver" centrado en la parte inferior
            y_volver = self.alto - alto_boton - 80  # Espacio para la barra inferior
            self.boton_regresar = Boton(
                x_centrado, y_volver, ancho_boton, alto_boton,
                "Volver", (231, 76, 60), fuente_botones, (255, 255, 255)
            )
            
        else:
            # Configuración original para otros botones (id != 3)
            # Columna derecha para botones de rutinas: más grandes para Rutinas (id=1)
            if self.boton_id == 1:
                # Botones más grandes para Rutinas
                col_w = min(360, int(self.ancho * 0.32))
                ancho_boton = int(col_w * 0.92)
                alto_boton = max(50, int(self.alto * 0.08))  # Botones más altos
                margen = max(16, int(self.ancho * 0.04))
                espaciado = max(12, int(self.alto * 0.022))  # Más espaciado entre botones
            else:
                col_w = min(320, int(self.ancho * 0.28))
                ancho_boton = int(col_w * 0.9)
                alto_boton = max(32, int(self.alto * 0.06))
                margen = max(16, int(self.ancho * 0.04))
                espaciado = max(8, int(self.alto * 0.018))

            # Fuente para botones. Ajustar tamaños por menú:
            # - Rutinas (id=1): fuente más grande para botones más grandes
            fuente_botones = self.fuente_dejavu
            try:
                if getattr(self, 'boton_id', None) == 1:
                    fuente_botones = pygame.font.Font(None, 26)  # Fuente más grande para Rutinas
            except Exception:
                pass

            # Crear botones de rutinas (alineados a la derecha)
            self.botones = []
            x_columna = self.ancho - col_w + (col_w - ancho_boton) // 2
            y_inicio = max(margen, int(self.alto * 0.12))

            # Nombres de subrutinas según el botón principal
            nombres_subrutinas = {
                # Para Rutinas (id=1) ahora solo 3 botones con nombres acordes a su trayectoria
                1: ["Espiral Cuadrada", "Espiral Circular", "Zig Zag Vertical"],
                2: ["Gráfica Fuerza", "Gráfica Tiempo", "Gráfica Progreso", "Exportar Datos"],
                4: ["Configuración 1", "Configuración 2", "Configuración 3", "Configuración 4"],
                5: ["Reporte 1", "Reporte 2", "Reporte 3", "Reporte 4"],
                6: ["Ayuda 1", "Ayuda 2", "Ayuda 3", "Ayuda 4"]
            }

            if self.boton_id == 1:
                # Usar nombres según zona actual (Hombro/Antebrazo)
                subrutinas = self._nombres_rutinas_por_zona(getattr(self, 'zona_actual', 'Hombro'))
                # Colores modernos y atractivos para los botones de rutinas
                colores_rutinas = [
                    (46, 204, 113),   # Verde brillante - Espiral Cuadrada / Estrella 5 picos
                    (52, 152, 219),   # Azul brillante - Espiral Circular / Infinito
                    (155, 89, 182)    # Morado - Zig Zag Vertical / Línea curva
                ]
                color_texto_blanco = (255, 255, 255)  # Texto blanco para mejor contraste
                
                for i in range(3):
                    y = y_inicio + i * (alto_boton + espaciado)
                    texto = subrutinas[i] if i < len(subrutinas) else f"Rutina {i+1}"
                    self.botones.append(Boton(x_columna, y, ancho_boton, alto_boton, texto, colores_rutinas[i], fuente_botones, color_texto_blanco))
            else:
                subrutinas = nombres_subrutinas.get(self.boton_id, [f"Rutina {self.boton_id}-{i+1}" for i in range(4)])
                for i in range(4):
                    y = y_inicio + i * (alto_boton + espaciado)
                    self.botones.append(Boton(x_columna, y, ancho_boton, alto_boton, subrutinas[i], VERDE_CLARO, fuente_botones, VERDE_BOTON))

            # Botón regresar al final de la columna con color rojo moderno
            y_regresar = self.alto - alto_boton - margen - alto_barra_inferior(self.alto) - 8
            color_texto_blanco = (255, 255, 255)
            self.boton_regresar = Boton(x_columna, y_regresar, ancho_boton, alto_boton, "Volver", (231, 76, 60), fuente_botones, color_texto_blanco)

        # Guardar proporciones para redimensionamiento
        for boton in self.botones:
            boton.actualizar_proporciones(self.ancho, self.alto)

        self.boton_regresar.actualizar_proporciones(self.ancho, self.alto)

    def _nombres_rutinas_por_zona(self, zona: str):
        # Nombres por zona; Antebrazo con diseños propios
        if zona == 'Antebrazo':
            return ["Estrella 5 picos", "Infinito", "Línea curva"]
        return ["Espiral Cuadrada", "Espiral Circular", "Zig Zag Vertical"]

    def _actualizar_textos_rutinas(self):
        if getattr(self, 'boton_id', None) != 1:
            return
        nombres = self._nombres_rutinas_por_zona(getattr(self, 'zona_actual', 'Hombro'))
        for i, boton in enumerate(self.botones):
            if i < len(nombres):
                boton.texto = f"{nombres[i]}"

    def redimensionar(self, nuevo_ancho, nuevo_alto):
        """Redimensiona todos los elementos de la interfaz."""
        self.ancho, self.alto = nuevo_ancho, nuevo_alto
        
        # Para Progreso del Paciente (id=3), recalcular posiciones centradas
        if self.boton_id == 3:
            ancho_boton = 260
            alto_boton = 60
            espaciado = 25
            margen_superior = 120
            
            # Calcular posición centrada
            x_centrado = (self.ancho - ancho_boton) // 2
            
            # Reposicionar botones
            for i, boton in enumerate(self.botones):
                boton.rect.width = ancho_boton
                boton.rect.height = alto_boton
                boton.rect.x = x_centrado
                boton.rect.y = margen_superior + i * (alto_boton + espaciado)
                boton.actualizar_proporciones(self.ancho, self.alto)
            
            # Botón "Volver" centrado en la parte inferior
            y_volver = self.alto - alto_boton - 80
            self.boton_regresar.rect.width = ancho_boton
            self.boton_regresar.rect.height = alto_boton
            self.boton_regresar.rect.x = x_centrado
            self.boton_regresar.rect.y = y_volver
            self.boton_regresar.actualizar_proporciones(self.ancho, self.alto)
            
        else:
            # Recalcular geometría de la columna derecha de botones
            # Usar tamaños más grandes para Rutinas (id=1)
            if self.boton_id == 1:
                col_w = min(360, int(self.ancho * 0.32))
                ancho_boton = int(col_w * 0.92)
                alto_boton = max(50, int(self.alto * 0.08))
                espaciado = max(12, int(self.alto * 0.022))
            else:
                col_w = min(320, int(self.ancho * 0.28))
                ancho_boton = int(col_w * 0.9)
                alto_boton = max(32, int(self.alto * 0.06))
                espaciado = max(8, int(self.alto * 0.018))
            
            margen = max(16, int(self.ancho * 0.04))
            x_columna = self.ancho - col_w + (col_w - ancho_boton) // 2
            y_inicio = max(margen, int(self.alto * 0.12))

            # Redimensionar y reposicionar botones
            for i, boton in enumerate(self.botones):
                boton.rect.width = ancho_boton
                boton.rect.height = alto_boton
                boton.rect.x = x_columna
                boton.rect.y = y_inicio + i * (alto_boton + espaciado)
                boton.actualizar_proporciones(self.ancho, self.alto)

            # Botón 'Volver' al final de la columna
            self.boton_regresar.rect.width = ancho_boton
            self.boton_regresar.rect.height = alto_boton
            self.boton_regresar.rect.x = x_columna
            self.boton_regresar.rect.y = self.alto - alto_boton - margen - alto_barra_inferior(self.alto) - 8
            self.boton_regresar.actualizar_proporciones(self.ancho, self.alto)
        # Asegurar que el botón 'Volver' quede por encima de la barra inferior permanente
        bar_h = alto_barra_inferior(self.alto)
        if self.boton_regresar.rect.bottom > self.alto - bar_h - 6:
            self.boton_regresar.rect.bottom = self.alto - bar_h - 6
        # Posicionar selector zona/dificultad si aplica
        if getattr(self, 'boton_id', None) == 1:
            # Área de contenido a la izquierda de la columna de botones
            margen_izq = max(16, int(self.ancho * 0.04))
            col_w = min(360, int(self.ancho * 0.32))  # Usar el nuevo tamaño de columna
            area_w = self.ancho - col_w - margen_izq - 20
            # Colocar radios de zona arriba, dentro del área izquierda
            self.radio_hombro.x = margen_izq
            self.radio_hombro.y = max(30, int(self.alto * 0.12))
            # Separar más los radios entre sí
            self.radio_antebrazo.x = self.radio_hombro.x + 220
            self.radio_antebrazo.y = self.radio_hombro.y
            # Radios de mano debajo de los de zona - MUCHA MÁS SEPARACIÓN
            self.radio_derecha.x = margen_izq
            self.radio_derecha.y = self.radio_hombro.y + 60  # Aumentado de 45 a 60
            self.radio_izquierda.x = self.radio_derecha.x + 220
            self.radio_izquierda.y = self.radio_derecha.y
            # Slider dificultad debajo de radios de mano, ocupando parte del área izquierda
            slider_w = min(360, max(220, int(area_w * 0.5)))
            # Aumentar separación vertical respecto a los radios de mano
            self.slider_dificultad.rect = pygame.Rect(self.radio_hombro.x, self.radio_derecha.y + 60, slider_w, 28)  # Aumentado de 50 a 60
            # Slider velocidad debajo de dificultad
            vel_w = min(360, max(220, int(area_w * 0.5)))
            # Aumentar separación entre sliders
            self.slider_velocidad_rutina.rect = pygame.Rect(self.slider_dificultad.rect.x, self.slider_dificultad.rect.bottom + 35, vel_w, 22)  # Aumentado de 28 a 35
            # Posicionar botones de Paro/Reanudar debajo del slider de velocidad - MÁS GRANDES Y ANCHOS
            try:
                btn_w = min(280, vel_w)  # Ancho mayor (de 230 a 280)
                btn_h = 38  # Alto mayor
                x_btn = self.slider_velocidad_rutina.rect.x
                y_btn_paro = self.slider_velocidad_rutina.rect.bottom + 25  # Aumentado de 18 a 25
                y_btn_rean = y_btn_paro + btn_h + 15  # Aumentado de 12 a 15
                self.boton_paro.rect = pygame.Rect(x_btn, y_btn_paro, btn_w, btn_h)
                self.boton_reanudar_mov.rect = pygame.Rect(x_btn, y_btn_rean, btn_w, btn_h)
                self.boton_paro.actualizar_proporciones(self.ancho, self.alto)
                self.boton_reanudar_mov.actualizar_proporciones(self.ancho, self.alto)
                # Posicionar botones de Guardar $$ y Restablecer $$ debajo de 'Reanudar'
                y_cfg = self.boton_reanudar_mov.rect.bottom + 18  # Aumentado de 12 a 18
                x_cfg = self.boton_paro.rect.x
                self.boton_guardar_cfg.rect = pygame.Rect(x_cfg, y_cfg, 160, 32)  # Más grande
                self.boton_guardar_cfg.actualizar_proporciones(self.ancho, self.alto)
                self.boton_rest_cfg.rect = pygame.Rect(self.boton_guardar_cfg.rect.right + 12, y_cfg, 180, 32)  # Más grande
                self.boton_rest_cfg.actualizar_proporciones(self.ancho, self.alto)
                # Posicionar botón 'Ver firmware' DEBAJO de 'Guardar $$'
                fw_y = self.boton_guardar_cfg.rect.bottom + 18  # Aumentado de 12 a 18
                fw_x = self.boton_guardar_cfg.rect.x  # Alineado con Guardar $$
                self.boton_ver_fw.rect = pygame.Rect(fw_x, fw_y, 160, 32)  # Más grande
                self.boton_ver_fw.actualizar_proporciones(self.ancho, self.alto)
                # Posicionar botón 'Volver' DEBAJO de 'Ver firmware' - más arriba que antes
                boton_volver_w = 200
                boton_volver_h = 45
                boton_volver_x = margen_izq
                boton_volver_y = self.boton_ver_fw.rect.bottom + 25  # Justo debajo de Ver firmware
                self.boton_volver_izq = Boton(
                    boton_volver_x, boton_volver_y, boton_volver_w, boton_volver_h,
                    "← Volver", (231, 76, 60), pygame.font.Font(None, 26), (255, 255, 255)
                )
                self.boton_volver_izq.actualizar_proporciones(self.ancho, self.alto)
            except Exception:
                pass

    def leer_datos_sensores(self):
        """Lee los datos reales de los sensores ECG usando Arduino Nano"""
        try:
            # Inicializar calibración dinámica si no existe
            if not hasattr(self, '_ecg_initialized'):
                self._contador_debug = 0  # Para mostrar valores cada cierto tiempo
                
                # Calibración dinámica para señales ECG - rangos típicos del Arduino
                self._min_hombro = 0
                self._max_hombro = 700  # Valor inicial optimizado para ECG procesado
                self._min_antebrazo = 0
                self._max_antebrazo = 700
                
                self._ecg_initialized = True
                print(f"[ECG Arduino] Sistema inicializado")
                print(f"[ECG Arduino] Los valores se calibrarán automáticamente")
            
            # Verificar si el Arduino está conectado y tiene datos
            if hasattr(self, 'arduino_reader') and self.arduino_reader and self.arduino_reader.conectado:
                # Obtener los últimos datos del buffer del Arduino
                datos_hombro = self.arduino_reader.obtener_datos_hombro()
                datos_antebrazo = self.arduino_reader.obtener_datos_antebrazo()
                
                if datos_hombro and datos_antebrazo:
                    # Tomar el último valor de cada buffer
                    valor_hombro = datos_hombro[-1]
                    valor_antebrazo = datos_antebrazo[-1]
                    
                    # Actualizar calibración dinámica (aprendizaje de rangos)
                    if valor_hombro > self._max_hombro:
                        self._max_hombro = valor_hombro
                    if valor_antebrazo > self._max_antebrazo:
                        self._max_antebrazo = valor_antebrazo
                    
                    # Debug: mostrar valores cada 50 lecturas (~5 segundos)
                    self._contador_debug += 1
                    if self._contador_debug % 50 == 0:
                        print(f"[ECG Arduino DEBUG] Hombro: {valor_hombro:5.1f} (Rango: {self._min_hombro}-{self._max_hombro}) | "
                              f"Antebrazo: {valor_antebrazo:5.1f} (Rango: {self._min_antebrazo}-{self._max_antebrazo})")
                    
                    # Normalizar a rango 0-100 usando calibración dinámica
                    # Esto permite que valores pequeños (típicos de ECG) se vean en la gráfica
                    rango_hombro = max(1, self._max_hombro - self._min_hombro)
                    rango_antebrazo = max(1, self._max_antebrazo - self._min_antebrazo)
                    
                    norm_hombro = int(((valor_hombro - self._min_hombro) / rango_hombro) * 100)
                    norm_antebrazo = int(((valor_antebrazo - self._min_antebrazo) / rango_antebrazo) * 100)
                    
                    # Limitar a 0-100
                    norm_hombro = min(100, max(0, norm_hombro))
                    norm_antebrazo = min(100, max(0, norm_antebrazo))
                    
                    return norm_hombro, norm_antebrazo
                else:
                    return 0, 0
            else:
                # Si no hay conexión Arduino, devolver valores en 0
                print("[ECG Arduino] Sin conexión o sin datos")
                return 0, 0
                
        except Exception as e:
            print(f"[ERROR] Error leyendo sensores ECG de Arduino: {e}")
            import traceback
            traceback.print_exc()
            return 0, 0



    def _validar_lineas_en_rango(self, lineas, xmin: float = -20.0, xmax: float = 20.0, ymin: float = -20.0, ymax: float = 20.0):
        """Valida que todas las líneas G0/G1 con X/Y estén dentro del rango permitido.
        Devuelve (ok: bool, mensaje_error: str|None).
        """
        try:
            for raw in lineas:
                ln = limpiar_linea_gcode(raw)
                parts = ln.split() if ln else []
                if not parts:
                    continue
                if parts[0] not in ('G0', 'G1', 'G90', 'G91'):
                    continue
                xi = yi = None
                for p in parts[1:]:
                    up = p.upper()
                    if up.startswith('X'):
                        try:
                            xi = float(p[1:])
                        except Exception:
                            pass
                    elif up.startswith('Y'):
                        try:
                            yi = float(p[1:])
                        except Exception:
                            pass
                if xi is not None and (xi < xmin or xi > xmax):
                    return False, f"X fuera de rango [{xmin},{xmax}]: {xi:.3f}"
                if yi is not None and (yi < ymin or yi > ymax):
                    return False, f"Y fuera de rango [{ymin},{ymax}]: {yi:.3f}"
            return True, None
        except Exception as e:
            return False, f"Error validando rutina: {e}"

    def _validar_archivo_rutina_en_rango(self, ruta: str, invertir: bool = False, lim_min: float = -20.0, lim_max: float = 20.0):
        """Valida que un archivo G-code de rutina, simulando G90/G91 y la inversión opcional,
        quede dentro del rango [-20..20]. Devuelve (ok, msg).
        """
        try:
            if not os.path.exists(ruta):
                return False, f"No existe: {ruta}"
            # Simular trayectoria para validar
            absoluto = True
            x = 0.0
            y = 0.0
            with open(ruta, 'r') as f:
                for raw in f:
                    l = limpiar_linea_gcode(raw)
                    parts = l.split() if l else []
                    if not parts:
                        continue
                    cmd = parts[0].upper()
                    if cmd == 'G90':
                        absoluto = True
                        continue
                    if cmd == 'G91':
                        absoluto = False
                        continue
                    if cmd not in ('G0','G1'):
                        continue
                    xi = yi = None
                    for p in parts[1:]:
                        up = p.upper()
                        if up.startswith('X'):
                            try:
                                xi = float(p[1:])
                            except Exception:
                                pass
                        elif up.startswith('Y'):
                            try:
                                yi = float(p[1:])
                            except Exception:
                                pass
                    # aplicar movimiento
                    if absoluto:
                        tx = x if xi is None else xi
                        ty = y if yi is None else yi
                    else:
                        tx = x + (0.0 if xi is None else xi)
                        ty = y + (0.0 if yi is None else yi)
                    # sin inversión: mantener coordenadas tal cual
                    # validar rango
                    if tx < lim_min or tx > lim_max:
                        return False, f"X fuera de rango [{lim_min},{lim_max}]: {tx:.3f}"
                    if ty < lim_min or ty > lim_max:
                        return False, f"Y fuera de rango [{lim_min},{lim_max}]: {ty:.3f}"
                    # avanzar posición
                    x, y = tx, ty
            return True, None
        except Exception as e:
            return False, f"Error validando archivo: {e}"

    def generar_rutina_dinamica(self, zona: str, numero: int, dificultad: int = 5, invertir: bool = False):
        """Genera una lista de líneas G-code (G90) para una rutina en X/Y.
        zona: 'Hombro' o 'Antebrazo'
        numero: 1..5
        dificultad: 0..10 (escala amplitud/repeticiones)
        """
        # Workspace permitido [-20..20]; usar margen de seguridad 2 mm
        min_xy, max_xy = -20.0, 20.0
        margin = 2.0
        low, high = min_xy + margin, max_xy - margin
        # Escalas por dificultad
        amp = 5 + (dificultad * 2.5)  # 5..30 aprox
        amp = max(3.0, min(amp, (high - low)))
        rep = 3 + (dificultad // 2)   # 3..8
        # Centro de trabajo en el origen (0, 0)
        cx, cy = 0.0, 0.0
        lines = ["G90"]
        def clamp(v):
            return max(min_xy, min(max_xy, v))
        def _map_inv_x(v: float) -> float:
            return max(min_xy, min(max_xy, (max_xy - v)))
        def move(x, y, rapid=False):
            x = clamp(x); y = clamp(y)
            if invertir:
                x = _map_inv_x(x)
                # Y no se invierte cuando invertir=True
            g = 'G0' if rapid else 'G1'
            lines.append(f"{g} X{round(x,3)} Y{round(y,3)}")
        # Patrones por número
        if numero == 1:
            # Cuadrado/rectángulo alrededor del centro, con repeticiones
            w = amp; h = amp
            for k in range(rep):
                move(cx - w/2, cy - h/2, rapid=(k==0))
                move(cx + w/2, cy - h/2)
                move(cx + w/2, cy + h/2)
                move(cx - w/2, cy + h/2)
                move(cx - w/2, cy - h/2)
        elif numero == 2:
            # Zig-zag horizontal
            span = amp
            y0 = cy - span/2
            y1 = cy + span/2
            x_left = max(low, cx - span/2)
            x_right = min(high, cx + span/2)
            move(x_left, y0, rapid=True)
            for k in range(rep):
                move(x_right, y0)
                move(x_right, y1)
                move(x_left, y1)
                move(x_left, y0)
        elif numero == 3:
            # Espiral cuadrada hacia afuera
            step = max(2.0, amp / max(3, rep))
            x0, y0 = cx, cy
            move(x0, y0, rapid=True)
            length = step
            for i in range(1, rep*2+1):
                # derecha, abajo, izquierda, arriba...
                dx, dy = ((length, 0), (0, length), (-length, 0), (0, -length))[(i-1) % 4]
                x0 = clamp(x0 + dx)
                y0 = clamp(y0 + dy)
                move(x0, y0)
                if i % 2 == 0:
                    length += step
        elif numero == 4:
            # Barridos verticales
            span = amp
            x0 = clamp(cx - span/2)
            x1 = clamp(cx + span/2)
            y_bottom = low
            y_top = high
            move(x0, y_bottom, rapid=True)
            for k in range(rep):
                move(x0, y_top)
                move(x1, y_top)
                move(x1, y_bottom)
                move(x0, y_bottom)
        else:
            # numero == 5: L-steps en cuadrante
            step = max(2.0, amp / max(3, rep))
            x0, y0 = clamp(cx - amp/2), clamp(cy - amp/2)
            move(x0, y0, rapid=True)
            for k in range(rep):
                x1 = clamp(x0 + step)
                move(x1, y0)
                y1 = clamp(y0 + step)
                move(x1, y1)
                x0, y0 = x1, y1
        return lines

    def _map_dificultad_a_lado(self, dificultad: float | int) -> float:
        try:
            n = int(round(float(dificultad)))
        except Exception:
            n = 1
        n = max(1, min(5, n))
        return {1: 10.0, 2: 15.0, 3: 20.0, 4: 30.0, 5: 40.0}[n]

    def _generar_rutina_por_zona(self, zona: str, numero: int, dificultad: float | int):
        # Genera G-code (G90) para la rutina seleccionada, dimensionada por dificultad
        lines = ["G90"]
        # Centro de trabajo en el origen (0, 0) con límites [-20..20]
        cx, cy = 0.0, 0.0
        # Micropaso para suavidad (mm). Se puede exponer luego como ajuste en UI.
        micro = float(getattr(self, 'micro_step_mm', 0.5) or 0.5)
        micro = max(0.1, min(2.0, micro))
        lado = self._map_dificultad_a_lado(dificultad)
        half = lado / 2.0
        def clamp(v):
            return max(-20.0, min(20.0, v))
        def move(x, y, rapid=False):
            x = clamp(x); y = clamp(y)
            g = 'G0' if rapid else 'G1'
            lines.append(f"{g} X{round(x,3)} Y{round(y,3)}")
        if zona == 'Hombro':
            if numero == 1:
                # Espiral cuadrada desde 1x1 hasta lado final según dificultad
                half_ini = 0.5
                half_fin = max(half_ini, half)
                x, y = cx, cy
                move(x, y, rapid=True)
                # Longitud inicial de cada tramo en mm
                L = 1.0
                # Direcciones: +X, +Y, -X, -Y repetidamente
                dirs = [(1,0), (0,1), (-1,0), (0,-1)]
                di = 0
                # Continuar hasta alcanzar el radio cuadrado deseado
                # Incrementa L después de cada dos tramos para formar la espiral cuadrada
                pasos = 0
                while True:
                    for _ in range(2):
                        dx, dy = dirs[di % 4]
                        # Avanzar en micro-pasos para suavidad
                        pasos_segmento = max(1, int(round(L / micro)))
                        step = micro
                        for _ in range(pasos_segmento):
                            x = clamp(x + dx * step)
                            y = clamp(y + dy * step)
                            move(x, y)
                        di += 1
                        pasos += pasos_segmento
                        # Condición de salida: cuando alcanzamos o sobrepasamos half_fin
                        if max(abs(x - cx), abs(y - cy)) >= half_fin:
                            break
                    if max(abs(x - cx), abs(y - cy)) >= half_fin:
                        break
                    L += 1.0
            elif numero == 2:
                # Espiral circular: diámetro inicial 1 y final según mapa de dificultad (lado)
                # Trazo con paso angular adaptativo para que la cuerda sea ≈ micro
                d_ini = 1.0
                d_fin = max(d_ini, min(40.0, lado))
                r_ini = d_ini / 2.0
                r_fin = d_fin / 2.0
                try:
                    n = int(round(float(dificultad)))
                except Exception:
                    n = 1
                n = max(1, min(5, n))
                vueltas_map = {1: 2, 2: 3, 3: 3, 4: 4, 5: 4}
                vueltas = vueltas_map[n]
                ang_total = 2.0 * math.pi * vueltas
                ang = 0.0
                first = True
                while ang <= ang_total + 1e-6:
                    t = ang / ang_total if ang_total > 0 else 1.0
                    r = r_ini + (r_fin - r_ini) * t
                    x = cx + r * math.cos(ang)
                    y = cy + r * math.sin(ang)
                    move(x, y, rapid=first)
                    first = False
                    # Δángulo aproximando cuerda ≈ micro: delta = micro / r
                    if r <= 0.001:
                        d_ang = 0.2  # evitar demasiados puntos al inicio
                    else:
                        d_ang = micro / r
                    # Limitar paso angular para no exceder segmentos largos/cortos
                    d_ang = max(0.02, min(0.25, d_ang))
                    ang += d_ang
            elif numero == 3:
                # Zig Zag vertical: trazos principales verticales, con pasos horizontales entre columnas
                ancho = lado
                alto = lado
                x_left = clamp(cx - ancho/2.0)
                x_right = clamp(cx + ancho/2.0)
                y_bottom = clamp(cy - alto/2.0)
                y_top = clamp(cy + alto/2.0)
                # Densidad por dificultad: más columnas (pasos horizontales)
                try:
                    n = int(round(float(dificultad)))
                except Exception:
                    n = 1
                n = max(1, min(5, n))
                cols_map = {1: 4, 2: 6, 3: 8, 4: 12, 5: 16}
                cols = max(2, cols_map.get(n, 6))
                step_x = (x_right - x_left) / cols if cols > 0 else (x_right - x_left)
                # Iniciar abajo a la izquierda
                move(x_left, y_bottom, rapid=True)
                corner = min(micro * 1.2, abs(step_x) / 3.0) if step_x != 0 else micro * 1.2
                for c in range(cols):
                    xk = clamp(x_left + c * step_x)
                    # Trazo vertical principal en micro-pasos de 0.5 mm para suavidad
                    y_inicio = y_bottom if c % 2 == 0 else y_top
                    y_fin = y_top if c % 2 == 0 else y_bottom
                    dy = micro if y_fin > y_inicio else -micro
                    y = y_inicio
                    while (dy > 0 and y < y_fin) or (dy < 0 and y > y_fin):
                        y = clamp(y + dy)
                        move(xk, y)
                    # Curvita de enlace antes de mover horizontal (aproximación con 2 puntos)
                    if c < cols - 1:
                        x_next = clamp(x_left + (c + 1) * step_x)
                        y_cur = y_fin
                        # Pequeño offset para redondear la esquina
                        # Primero desplaza un poco en X manteniendo Y
                        mid1_x = clamp(xk + (corner if x_next > xk else -corner))
                        move(mid1_x, y_cur)
                        # Luego hasta la columna siguiente en Y constante
                        move(x_next, y_cur)
        else:
            # Antebrazo: nuevas trayectorias, mismas reglas ([-20..20], G90, G0/G1, suavidad con micro)
            # Helpers para trazar con suavidad
            last = {'x': None, 'y': None}
            def goto(x, y, rapid=False):
                move(x, y, rapid)
                last['x'], last['y'] = x, y
            def line_to(x, y):
                x = clamp(x); y = clamp(y)
                if last['x'] is None or last['y'] is None:
                    goto(x, y, rapid=True)
                    return
                x0, y0 = last['x'], last['y']
                dx = x - x0; dy = y - y0
                dist = math.hypot(dx, dy)
                pasos = max(1, int(math.ceil(dist / micro)))
                for i in range(1, pasos + 1):
                    px = x0 + dx * (i / pasos)
                    py = y0 + dy * (i / pasos)
                    move(px, py)
                last['x'], last['y'] = x, y
            if numero == 1:
                # Estrella de 5 picos dentro de un cuadro lado x lado
                R = half  # radio exterior
                r = max(half * 0.38, R * 0.38)  # radio interior aproximado a proporción áurea
                # Generar 10 vértices alternando radio exterior/interior
                pts = []
                ang0 = -math.pi / 2.0  # iniciar arriba
                for k in range(10):
                    ang = ang0 + k * (math.pi / 5.0)
                    rad = R if (k % 2 == 0) else r
                    xk = clamp(cx + rad * math.cos(ang))
                    yk = clamp(cy + rad * math.sin(ang))
                    pts.append((xk, yk))
                # Trazar estrella cerrando la figura
                if pts:
                    goto(pts[0][0], pts[0][1], rapid=True)
                    for p in pts[1:]:
                        line_to(p[0], p[1])
                    line_to(pts[0][0], pts[0][1])
            elif numero == 2:
                # Símbolo de infinito (Lissajous)
                ax = half
                ay = half
                # Paso paramétrico acorde a micro
                dt = max(0.02, min(0.12, micro / max(1e-3, half)))
                t = 0.0
                t_max = 2.0 * math.pi
                x0 = clamp(cx + ax * math.sin(0.0))
                y0 = clamp(cy + ay * math.sin(2.0 * 0.0))
                goto(x0, y0, rapid=True)
                while t <= t_max + 1e-6:
                    x = clamp(cx + ax * math.sin(t))
                    y = clamp(cy + ay * math.sin(2.0 * t))
                    move(x, y)
                    last['x'], last['y'] = x, y
                    t += dt
                # cerrar suave al inicio
                line_to(x0, y0)
            elif numero == 3:
                # Línea curva (S-curve) dentro del cuadro lado x lado
                x_start = cx - half
                x_end = cx + half
                A = half  # amplitud vertical
                # Muestras según micro
                long_x = max(1e-6, x_end - x_start)
                pasos = max(20, int(math.ceil(long_x / micro) * 2))
                for i in range(pasos + 1):
                    s = i / pasos
                    x = x_start + long_x * s
                    # Onda suave: seno de dos medias ondas (S)
                    y = cy + A * math.sin(math.pi * (2.0 * s - 1.0))
                    if i == 0:
                        goto(x, y, rapid=True)
                    else:
                        move(clamp(x), clamp(y))
                        last['x'], last['y'] = x, y
        return lines

    def dibujar_vista_previa(self, zona: str, numero: int, dificultad: int):
        """Dibuja una vista previa de la rutina en un panel.
        - Para la subrutina 1-1, si hay archivo en rutas_gcode, lo usa.
        - Para otras, genera rutina dinámica.
        - Aplica inversión visual si la mano seleccionada es izquierda.
        """
        try:
            if getattr(self, 'boton_id', None) == 1:
                lines = self._generar_rutina_por_zona(zona, numero, dificultad)
            else:
                zona_sel = getattr(self, 'zona_actual', None)
                lines = self.obtener_rutina_usuario(getattr(self, 'boton_id', 1), numero, zona_sel)
        except Exception:
            lines = []
        
        # Verificar si hay que invertir la vista previa
        invertir_preview = (getattr(self, 'mano_actual', 'Derecha') == 'Izquierda')
        
        # Convertir a puntos para renderizar (solo G0/G1 X Y)
        pts = []
        x, y = None, None
        for ln in lines:
            s = limpiar_linea_gcode(ln)
            parts = s.split() if s else []
            if not parts:
                continue
            if parts[0] not in ('G0', 'G1'):
                continue
            xi = yi = None
            for p in parts[1:]:
                if p.startswith('X'):
                    try:
                        xi = float(p[1:])
                    except Exception:
                        pass
                elif p.startswith('Y'):
                    try:
                        yi = float(p[1:])
                    except Exception:
                        pass
            x = xi if xi is not None else x
            y = yi if yi is not None else y
            if x is not None and y is not None:
                # Aplicar inversión X si corresponde (en el sistema centrado -20..20)
                px = (-x) if invertir_preview else x
                pts.append((px, y))
        if len(pts) < 2:
            # Dibujar panel con mensaje "Sin vista previa"
            # Usar tamaños más grandes para Rutinas (id=1)
            if getattr(self, 'boton_id', None) == 1:
                col_w = min(360, int(self.ancho * 0.32))
                ancho_boton = int(col_w * 0.92)
                alto_boton = max(50, int(self.alto * 0.08))
                espaciado = max(12, int(self.alto * 0.022))
            else:
                col_w = min(320, int(self.ancho * 0.28))
                ancho_boton = int(col_w * 0.9)
                alto_boton = max(32, int(self.alto * 0.06))
                espaciado = max(8, int(self.alto * 0.018))
            
            margen = max(16, int(self.ancho * 0.04))
            x_columna = self.ancho - col_w + (col_w - ancho_boton) // 2
            y_inicio = max(margen, int(self.alto * 0.12))
            altura_botones = 5 * alto_boton + 4 * espaciado
            panel_w = ancho_boton
            # Panel más alto para Rutinas
            if getattr(self, 'boton_id', None) == 1:
                panel_h = max(200, int(self.alto * 0.28))  # Más alto para Rutinas
            else:
                panel_h = max(80, int(self.alto * 0.18))
            panel_x = x_columna
            panel_y = y_inicio + altura_botones + espaciado
            
            # Dibujar título "Vista Previa" arriba del panel
            try:
                fuente_titulo_panel = pygame.font.Font(None, 26)
                titulo_preview = fuente_titulo_panel.render("Vista Previa", True, (0, 100, 0))
                titulo_rect = titulo_preview.get_rect(centerx=panel_x + panel_w // 2, bottom=panel_y - 8)
                self.pantalla.blit(titulo_preview, titulo_rect)
            except Exception:
                pass
            
            rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
            # Fondo blanco con borde verde más grueso
            pygame.draw.rect(self.pantalla, (255, 255, 255), rect)
            pygame.draw.rect(self.pantalla, (46, 204, 113), rect, 3)  # Borde verde brillante
            try:
                texto = self.fuente_titulo.render("Sin vista previa", True, (120, 120, 120))
                trect = texto.get_rect(center=rect.center)
                self.pantalla.blit(texto, trect)
            except Exception:
                pass
            return
        # Panel de vista previa debajo de la columna derecha de botones
        # Usar tamaños más grandes para Rutinas (id=1)
        if getattr(self, 'boton_id', None) == 1:
            col_w = min(360, int(self.ancho * 0.32))
            ancho_boton = int(col_w * 0.92)
            alto_boton = max(50, int(self.alto * 0.08))
            espaciado = max(12, int(self.alto * 0.022))
        else:
            col_w = min(320, int(self.ancho * 0.28))
            ancho_boton = int(col_w * 0.9)
            alto_boton = max(32, int(self.alto * 0.06))
            espaciado = max(8, int(self.alto * 0.018))
        
        margen = max(16, int(self.ancho * 0.04))
        x_columna = self.ancho - col_w + (col_w - ancho_boton) // 2
        y_inicio = max(margen, int(self.alto * 0.12))
        # Altura ocupada por los 5 botones
        altura_botones = 5 * alto_boton + 4 * espaciado
        panel_w = ancho_boton
        # Panel más alto para Rutinas
        if getattr(self, 'boton_id', None) == 1:
            panel_h = max(200, int(self.alto * 0.28))  # Más alto para Rutinas
        else:
            panel_h = max(80, int(self.alto * 0.18))
        panel_x = x_columna
        panel_y = y_inicio + altura_botones + espaciado
        
        # Dibujar título "Vista Previa" arriba del panel
        try:
            fuente_titulo_panel = pygame.font.Font(None, 26)
            titulo_preview = fuente_titulo_panel.render("Vista Previa", True, (0, 100, 0))
            titulo_rect = titulo_preview.get_rect(centerx=panel_x + panel_w // 2, bottom=panel_y - 8)
            self.pantalla.blit(titulo_preview, titulo_rect)
        except Exception:
            pass
        
        rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        # Fondo blanco con borde verde brillante más grueso
        pygame.draw.rect(self.pantalla, (255, 255, 255), rect)
        pygame.draw.rect(self.pantalla, (46, 204, 113), rect, 3)  # Borde verde brillante
        # Normalizar puntos al panel (workspace -20..20)
        def map_pt(px, py):
            # Convertir de [-20, 20] a [0, 1]
            u = (px + 20.0) / 40.0
            v = 1.0 - ((py + 20.0) / 40.0)
            sx = rect.x + int(u * (rect.width - 10)) + 5
            sy = rect.y + int(v * (rect.height - 10)) + 5
            return sx, sy
        # Dibujar ejes en el centro del panel (origen 0,0)
        center_x = rect.x + rect.width // 2
        center_y = rect.y + rect.height // 2
        # Eje X (horizontal por el centro)
        pygame.draw.line(self.pantalla, (150, 150, 150), (rect.x+5, center_y), (rect.right-5, center_y), 1)
        # Eje Y (vertical por el centro)
        pygame.draw.line(self.pantalla, (150, 150, 150), (center_x, rect.y+5), (center_x, rect.bottom-5), 1)
        # Dibujar trayectoria con líneas más gruesas y color azul brillante
        prev = map_pt(*pts[0])
        for pt in pts[1:]:
            cur = map_pt(*pt)
            pygame.draw.line(self.pantalla, (52, 152, 219), prev, cur, 3)  # Azul brillante, línea más gruesa
            prev = cur

    def actualizar_datos(self):
        """Actualiza los datos de las gráficas con nuevas lecturas"""
        if not self.capturando:
            return
        
        tiempo_actual = pygame.time.get_ticks()
        if tiempo_actual - self.ultimo_tiempo_captura >= self.intervalo_captura:
            self.ultimo_tiempo_captura = tiempo_actual
            
            # Intentar leer datos reales del Arduino ECG
            valor_hombro, valor_antebrazo = self.leer_datos_sensores()
            
            # Si no hay datos del Arduino, mantener valores en 0 (sin simulación)
            # Las gráficas permanecerán estáticas hasta que se conecte el Arduino
            
            self.datos_sesion_hombro.append(valor_hombro)
            self.datos_sesion_antebrazo.append(valor_antebrazo)
            
            self.datos_hombro = np.roll(self.datos_hombro, -1)
            self.datos_hombro[-1] = valor_hombro
            
            self.datos_antebrazo = np.roll(self.datos_antebrazo, -1)
            self.datos_antebrazo[-1] = valor_antebrazo
            
            self.generar_graficas()

    def generar_graficas(self):
        """Genera las gráficas de matplotlib y las convierte a superficies de pygame"""
        if not _try_import_matplotlib():
            # Sin matplotlib no se pueden generar superficies de gráficas
            return
        # Throttle: no más de ~4 fps para dibujar gráficos pesados
        ahora = pygame.time.get_ticks()
        if hasattr(self, '_ultimo_dibujo'):
            if ahora - getattr(self, '_ultimo_dibujo', 0) < 250:
                return
        self._ultimo_dibujo = ahora
        plt.style.use('dark_background')
        
        fig_hombro = plt.figure(figsize=(6.5, 3.5), dpi=100)
        ax_hombro = fig_hombro.add_subplot(111)
        ax_hombro.plot(self.eje_tiempo, self.datos_hombro, color='#E6BE64', linewidth=2)
        ax_hombro.set_facecolor('#14382C')
        ax_hombro.set_title('Señal ECG - Hombro', color='#E6BE64', fontsize=16, fontweight='bold')
        ax_hombro.set_xlabel('Tiempo (s)', color='#E6BE64', fontsize=12)
        ax_hombro.set_ylabel('Amplitud ECG', color='#E6BE64', fontsize=12)
        ax_hombro.tick_params(colors='#E6BE64', labelsize=10)
        ax_hombro.grid(True, alpha=0.3, color='#E6BE64')
        ax_hombro.set_ylim(-5, 105)
        fig_hombro.patch.set_facecolor('#14382C')
        fig_hombro.tight_layout(pad=2.0)
        
        canvas_hombro = FigureCanvasAgg(fig_hombro)
        canvas_hombro.draw()
        renderer = canvas_hombro.get_renderer()
        
        try:
            raw_data = renderer.buffer_rgba()
            if isinstance(raw_data, memoryview):
                raw_data = bytes(raw_data)
            size = canvas_hombro.get_width_height()
            self.superficie_grafica_hombro = pygame.image.fromstring(raw_data, size, "RGBA")
        except (AttributeError, TypeError) as e:
            print(f"[DEBUG] Error con buffer_rgba, intentando método alternativo: {e}")
            try:
                raw_data = renderer.tostring_argb()
                size = canvas_hombro.get_width_height()
                self.superficie_grafica_hombro = pygame.image.fromstring(raw_data, size, "ARGB")
            except Exception as e2:
                print(f"[ERROR] No se pudo crear superficie de gráfica: {e2}")
                self.superficie_grafica_hombro = None
        
        plt.close(fig_hombro)
        
        fig_antebrazo = plt.figure(figsize=(6.5, 3.5), dpi=100)
        ax_antebrazo = fig_antebrazo.add_subplot(111)
        ax_antebrazo.plot(self.eje_tiempo, self.datos_antebrazo, color='#E6BE64', linewidth=2)
        ax_antebrazo.set_facecolor('#14382C')
        ax_antebrazo.set_title('Señal ECG - Antebrazo', color='#E6BE64', fontsize=16, fontweight='bold')
        ax_antebrazo.set_xlabel('Tiempo (s)', color='#E6BE64', fontsize=12)
        ax_antebrazo.set_ylabel('Amplitud ECG', color='#E6BE64', fontsize=12)
        ax_antebrazo.tick_params(colors='#E6BE64', labelsize=10)
        ax_antebrazo.grid(True, alpha=0.3, color='#E6BE64')
        ax_antebrazo.set_ylim(-5, 105)
        fig_antebrazo.patch.set_facecolor('#14382C')
        fig_antebrazo.tight_layout(pad=2.0)
        
        canvas_antebrazo = FigureCanvasAgg(fig_antebrazo)
        canvas_antebrazo.draw()
        renderer = canvas_antebrazo.get_renderer()
        
        try:
            raw_data = renderer.buffer_rgba()
            if isinstance(raw_data, memoryview):
                raw_data = bytes(raw_data)
            size = canvas_antebrazo.get_width_height()
            self.superficie_grafica_antebrazo = pygame.image.fromstring(raw_data, size, "RGBA")
        except (AttributeError, TypeError) as e:
            print(f"[DEBUG] Error con buffer_rgba, intentando método alternativo: {e}")
            try:
                raw_data = renderer.tostring_argb()
                size = canvas_antebrazo.get_width_height()
                self.superficie_grafica_antebrazo = pygame.image.fromstring(raw_data, size, "ARGB")
            except Exception as e2:
                print(f"[ERROR] No se pudo crear superficie de gráfica: {e2}")
                self.superficie_grafica_antebrazo = None
        plt.close(fig_antebrazo)
    
    def redimensionar_grafica(self, nuevo_ancho, nuevo_alto):
        """Redimensiona elementos cuando estamos en modo de gráficas (boton_id==2)."""
        self.ancho, self.alto = nuevo_ancho, nuevo_alto
        # Recalcular área de gráficas y columna de botones de control
        self.area_graficas_ancho = int(self.ancho * 0.62)
        self.inicio_botones_x = self.area_graficas_ancho + 20
        # Reposicionar botones respetando reglas originales
        if hasattr(self, 'boton_captura'):
            self.boton_captura.rect.topleft = (self.inicio_botones_x, self.margen + 60)
        if hasattr(self, 'boton_cambiar'):
            self.boton_cambiar.rect.topleft = (self.inicio_botones_x, self.margen + 60 + self.alto_boton + self.espaciado)
        if hasattr(self, 'boton_guardar'):
            self.boton_guardar.rect.topleft = (self.inicio_botones_x, self.margen + 60 + 2 * (self.alto_boton + self.espaciado))
        if hasattr(self, 'boton_comparar'):
            self.boton_comparar.rect.topleft = (self.inicio_botones_x, self.margen + 60 + 3 * (self.alto_boton + self.espaciado))
        if hasattr(self, 'boton_regresar'):
            y_reg = max(60, self.alto - self.alto_boton - self.margen - alto_barra_inferior(self.alto) - 8)
            self.boton_regresar.rect.topleft = (self.inicio_botones_x, y_reg)

    def generar_grafica_progreso(self):
        """Genera la gráfica de comparación de progreso de todas las sesiones"""
        if not _try_import_matplotlib():
            return None
        if not self.id_paciente or not self.gestor_pacientes:
            return None
        
        df_progreso = self.gestor_pacientes.obtener_datos_progreso(self.id_paciente)
        if df_progreso is None or len(df_progreso) == 0:
            return None
        
        plt.style.use('dark_background')
        fig = plt.figure(figsize=(8, 6), dpi=100)
        ax = fig.add_subplot(111)
        
        # Usar las columnas transformadas: Esfuerzo_Hombro_Promedio, Esfuerzo_Antebrazo_Promedio
        # Crear número de sesión basado en el índice (o usar Numero_Sesion si existe)
        if 'Numero_Sesion' in df_progreso.columns:
            sesiones = df_progreso['Numero_Sesion']
        else:
            sesiones = np.arange(1, len(df_progreso) + 1)
        
        esfuerzo_hombro = df_progreso['Esfuerzo_Hombro_Promedio']
        esfuerzo_antebrazo = df_progreso['Esfuerzo_Antebrazo_Promedio']
        
        ax.plot(sesiones, esfuerzo_hombro, 'o-', color='#E6BE64', linewidth=2, markersize=6, label='Hombro')
        ax.plot(sesiones, esfuerzo_antebrazo, 's-', color='#64E6C5', linewidth=2, markersize=6, label='Antebrazo')
        
        ax.set_facecolor('#14382C')
        # Eliminar título de la gráfica ya que se muestra en la interfaz de Pygame
        ax.set_xlabel('Número de Sesión', color='#E6BE64', fontsize=12)
        ax.set_ylabel('Actividad ECG Promedio', color='#E6BE64', fontsize=12)
        ax.tick_params(colors='#E6BE64')
        ax.legend(facecolor='#14382C', edgecolor='#E6BE64', labelcolor='#E6BE64')
        ax.grid(True, alpha=0.3, color='#E6BE64')
        
        if len(sesiones) > 1:
            z_hombro = np.polyfit(sesiones, esfuerzo_hombro, 1)
            p_hombro = np.poly1d(z_hombro)
            ax.plot(sesiones, p_hombro(sesiones), "--", color='#E6BE64', alpha=0.7, linewidth=1)
            
            z_antebrazo = np.polyfit(sesiones, esfuerzo_antebrazo, 1)
            p_antebrazo = np.poly1d(z_antebrazo)
            ax.plot(sesiones, p_antebrazo(sesiones), "--", color='#64E6C5', alpha=0.7, linewidth=1)
        
        fig.patch.set_facecolor('#14382C')
        fig.tight_layout()
        
        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        renderer = canvas.get_renderer()
        
        try:
            raw_data = renderer.buffer_rgba()
            if isinstance(raw_data, memoryview):
                raw_data = bytes(raw_data)
            size = canvas.get_width_height()
            superficie_progreso = pygame.image.fromstring(raw_data, size, "RGBA")
        except (AttributeError, TypeError) as e:
            print(f"[DEBUG] Error con buffer_rgba, intentando método alternativo: {e}")
            try:
                raw_data = renderer.tostring_argb()
                size = canvas.get_width_height()
                superficie_progreso = pygame.image.fromstring(raw_data, size, "ARGB")
            except Exception as e2:
                print(f"[ERROR] No se pudo crear superficie de gráfica: {e2}")
                superficie_progreso = None
        
        plt.close(fig)
        return superficie_progreso
    
    def _manejar_ver_progreso(self):
        """Maneja la acción del botón 'Ver Progreso'."""
        if not self.id_paciente:
            mostrar_aviso_sistema("Aviso", "No hay paciente seleccionado")
            return
        
        try:
            # Guardar el estado de la pantalla actual
            pantalla_actual = pygame.display.get_surface()
            
            ventana_graficas = GraficasMusculares(self.id_paciente)
            ventana_graficas.ejecutar()
            
            # Después de cerrar la ventana de gráficas, restaurar la ventana principal
            # Recrear la superficie de display con las dimensiones originales
            if pantalla_actual:
                self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
                pygame.display.set_caption("Sistema de Control CNC - Rehabilitación")
        except CerrarPrograma:
            # Propagar la excepción de cierre para cerrar el programa
            raise
        except Exception as e:
            print(f"Error al abrir ventana de gráficas: {e}")
            import traceback
            traceback.print_exc()
            mostrar_aviso_sistema("Error", f"No se pudo abrir gráficas: {e}")
    
    def _manejar_comparar_sesiones(self):
        """Maneja la acción del botón 'Comparar Sesiones'."""
        if not self.id_paciente:
            mostrar_aviso_sistema("Aviso", "No hay paciente seleccionado")
            return
        
        try:
            df_progreso = self.gestor_pacientes.obtener_datos_progreso(self.id_paciente)
            
            if df_progreso is None or len(df_progreso) == 0:
                mostrar_aviso_sistema("Sin Datos Reales", 
                    "No hay sesiones de ejercicios reales guardadas para este paciente.\n\n" +
                    "Para generar datos de progreso:\n" +
                    "1. Vaya a 'Gráficas' en el menú principal\n" +
                    "2. Realice ejercicios con captura ECG\n" +
                    "3. Los datos se guardarán automáticamente")
                return
            
            if len(df_progreso) == 1:
                mostrar_aviso_sistema("Datos Insuficientes", 
                    f"Solo hay 1 sesión real registrada para {self.id_paciente}.\n\n" +
                    "Se necesitan al menos 2 sesiones para comparar progreso.\n" +
                    "Realice más ejercicios con captura ECG para generar más datos.")
                return
            
            # Calcular estadísticas
            mensaje = self._generar_mensaje_estadisticas(df_progreso)
            mostrar_aviso_sistema("Comparación de Sesiones", mensaje)
            
        except CerrarPrograma:
            # Propagar la excepción de cierre para cerrar el programa
            raise
        except Exception as e:
            print(f"Error al comparar sesiones: {e}")
            import traceback
            traceback.print_exc()
            mostrar_aviso_sistema("Error", f"No se pudo comparar sesiones: {e}")
    
    def _generar_mensaje_estadisticas(self, df_progreso):
        """Genera el mensaje de estadísticas de sesiones."""
        mensaje = f"Paciente: {self.id_paciente}\n"
        mensaje += f"Total de sesiones: {len(df_progreso)}\n\n"
        
        # Estadísticas de hombro - usar nombres transformados
        promedio_hombro = df_progreso['Esfuerzo_Hombro_Promedio'].mean()
        primera_hombro = df_progreso['Esfuerzo_Hombro_Promedio'].iloc[0]
        ultima_hombro = df_progreso['Esfuerzo_Hombro_Promedio'].iloc[-1]
        mejora_hombro = self._calcular_mejora(primera_hombro, ultima_hombro)
        
        # Estadísticas de antebrazo - usar nombres transformados
        promedio_antebrazo = df_progreso['Esfuerzo_Antebrazo_Promedio'].mean()
        primera_antebrazo = df_progreso['Esfuerzo_Antebrazo_Promedio'].iloc[0]
        ultima_antebrazo = df_progreso['Esfuerzo_Antebrazo_Promedio'].iloc[-1]
        mejora_antebrazo = self._calcular_mejora(primera_antebrazo, ultima_antebrazo)
        
        mensaje += f"HOMBRO:\n"
        mensaje += f"  Promedio: {promedio_hombro:.1f}%\n"
        mensaje += f"  Primera sesión: {primera_hombro:.1f}%\n"
        mensaje += f"  Última sesión: {ultima_hombro:.1f}%\n"
        mensaje += f"  Mejora: {mejora_hombro:.1f}%\n\n"
        
        mensaje += f"ANTEBRAZO:\n"
        mensaje += f"  Promedio: {promedio_antebrazo:.1f}%\n"
        mensaje += f"  Primera sesión: {primera_antebrazo:.1f}%\n"
        mensaje += f"  Última sesión: {ultima_antebrazo:.1f}%\n"
        mensaje += f"  Mejora: {mejora_antebrazo:.1f}%"
        
        return mensaje
    
    def _calcular_mejora(self, primera, ultima):
        """Calcula el porcentaje de mejora entre dos valores."""
        if primera > 0:
            return ((ultima - primera) / primera * 100)
        return 0
    
    def _manejar_exportar_reporte(self):
        """Maneja la acción del botón 'Exportar Reporte'."""
        if not self.id_paciente:
            mostrar_aviso_sistema("Aviso", "No hay paciente seleccionado")
            return
        
        try:
            df_progreso = self.gestor_pacientes.obtener_datos_progreso(self.id_paciente)
            
            if df_progreso is None or len(df_progreso) == 0:
                mostrar_aviso_sistema("Aviso", "No hay sesiones para exportar")
                return
            
            # Exportar a CSV
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            nombre_archivo = f"reporte_{self.id_paciente}_{timestamp}.csv"
            ruta_reporte = os.path.join(BASE_DIR, nombre_archivo)
            
            df_progreso.to_csv(ruta_reporte, index=False)
            mostrar_aviso_sistema("Reporte Exportado", f"Reporte guardado en:\n{ruta_reporte}")
            
        except CerrarPrograma:
            # Propagar la excepción de cierre para cerrar el programa
            raise
        except Exception as e:
            print(f"Error al exportar reporte: {e}")
            mostrar_aviso_sistema("Error", f"No se pudo exportar reporte: {e}")
    
    def _manejar_configurar_metas(self):
        """Maneja la acción del botón 'Configurar Metas'."""
        if not self.id_paciente:
            mostrar_aviso_sistema("Aviso", "No hay paciente seleccionado")
            return
        
        try:
            mensaje = f"Funcionalidad de Configurar Metas\n\n"
            mensaje += f"Paciente: {self.id_paciente}\n\n"
            mensaje += "Esta función permitirá establecer:\n"
            mensaje += "- Metas de actividad cardíaca\n"
            mensaje += "- Número de sesiones objetivo\n"
            mensaje += "- Alertas de progreso\n\n"
            mensaje += "(Función en desarrollo)"
            mostrar_aviso_sistema("Configurar Metas", mensaje)
        except CerrarPrograma:
            raise
        except Exception as e:
            print(f"Error en configurar metas: {e}")
            mostrar_aviso_sistema("Error", f"Error: {e}")

    def guardar_datos(self):
        """Guarda los datos actuales en un archivo CSV y registra la sesión"""
        try:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            nombre_archivo = os.path.join(BASE_DIR, f"datos_musculares_{timestamp}.csv")
            
            with open(nombre_archivo, 'w') as f:
                f.write("tiempo,hombro,antebrazo\n")
                for i in range(len(self.eje_tiempo)):
                    f.write(f"{self.eje_tiempo[i]},{self.datos_hombro[i]},{self.datos_antebrazo[i]}\n")
            
            if self.id_paciente and self.gestor_pacientes and len(self.datos_sesion_hombro) > 0:
                promedio_hombro = np.mean(self.datos_sesion_hombro)
                promedio_antebrazo = np.mean(self.datos_sesion_antebrazo)
                duracion = len(self.datos_sesion_hombro) * self.intervalo_captura / 60000
                
                datos_sesion = {
                    'esfuerzo_hombro': promedio_hombro,
                    'esfuerzo_antebrazo': promedio_antebrazo,
                    'duracion': duracion,
                    'observaciones': f'Archivo CSV: {nombre_archivo}'
                }
                
                exito, numero_sesion = self.gestor_pacientes.registrar_sesion(self.id_paciente, datos_sesion)
                if exito:
                    return True, f"{nombre_archivo} (Sesión #{numero_sesion} registrada)"
                else:
                    return True, f"{nombre_archivo} (Error al registrar sesión: {numero_sesion})"
            
            return True, nombre_archivo
        except Exception as e:
            print(f"Error al guardar datos: {e}")
            return False, str(e)

    def ejecutar(self):
        if self.boton_id == 2:
            info = pygame.display.Info()
            self.ancho, self.alto = info.current_w, info.current_h
            self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
            pygame.display.set_caption("Gráficas de Esfuerzo Muscular")
            self.fullscreen = False
            # Ajustar layout inicial para cubrir ventana maximizada
            self.redimensionar_grafica(self.ancho, self.alto)
            
            # Título con fuente más grande y color amarillo brillante
            fuente_titulo = ajustar_fuente_a_ancho("Gráficas de Esfuerzo Muscular", int(self.ancho * 0.95), 48, 20)
            color_titulo = (255, 255, 0)  # Amarillo brillante para mejor contraste
            fuente_mensaje = pygame.font.Font(None, 24)
            mensaje_texto = None
            mensaje_tiempo = 0
            
            mostrar_progreso = False
            superficie_progreso = None
            
            # self.generar_graficas()
            
            clock = pygame.time.Clock()
            
            ejecutando = True
            while ejecutando:
                tiempo_actual = pygame.time.get_ticks()
                
                self.pantalla.fill(self.color_fondo)
                
                if not mostrar_progreso:
                    titulo_texto = fuente_titulo.render("Gráficas de Esfuerzo Muscular", True, color_titulo)
                    # Mover el título a la izquierda (margen 20 px)
                    titulo_rect = titulo_texto.get_rect(topleft=(20, 8))
                    self.pantalla.blit(titulo_texto, titulo_rect)
                    
                    self.actualizar_datos()
                    
                    if self.modo_visualizacion == "hombro" or self.modo_visualizacion == "ambos":
                        if self.superficie_grafica_hombro:
                            if self.modo_visualizacion == "hombro":
                                rect_hombro = self.superficie_grafica_hombro.get_rect(
                                    center=(self.area_graficas_ancho // 2, self.alto // 2)
                                )
                            else:
                                rect_hombro = self.superficie_grafica_hombro.get_rect(
                                    center=(self.area_graficas_ancho // 2, self.alto * 0.305)
                                )
                            self.pantalla.blit(self.superficie_grafica_hombro, rect_hombro)
                    
                    if self.modo_visualizacion == "antebrazo" or self.modo_visualizacion == "ambos":
                        if self.superficie_grafica_antebrazo:
                            if self.modo_visualizacion == "antebrazo":
                                rect_antebrazo = self.superficie_grafica_antebrazo.get_rect(
                                    center=(self.area_graficas_ancho // 2, self.alto // 2)
                                )
                            else:
                                rect_antebrazo = self.superficie_grafica_antebrazo.get_rect(
                                    center=(self.area_graficas_ancho // 2, self.alto * 0.75)
                                )
                            self.pantalla.blit(self.superficie_grafica_antebrazo, rect_antebrazo)
                else:
                    # Título principal más grande y centrado
                    fuente_titulo_comp = ajustar_fuente_a_ancho("Comparación de Progreso", int(self.ancho * 0.95), 52, 24)
                    titulo_texto = fuente_titulo_comp.render("Comparación de Progreso", True, (255, 255, 0))
                    titulo_rect = titulo_texto.get_rect(center=(self.ancho // 2, 40))
                    self.pantalla.blit(titulo_texto, titulo_rect)
                    
                    # Subtítulo explicativo más visible
                    fuente_subtitulo = pygame.font.Font(None, 24)
                    subtitulo_texto = fuente_subtitulo.render("Progreso de Rehabilitación", True, (200, 200, 100))
                    subtitulo_rect = subtitulo_texto.get_rect(center=(self.ancho // 2, 75))
                    self.pantalla.blit(subtitulo_texto, subtitulo_rect)
                    
                    explicacion_texto = fuente_subtitulo.render("(Menor esfuerzo = Mejor rehabilitación)", True, (200, 200, 100))
                    explicacion_rect = explicacion_texto.get_rect(center=(self.ancho // 2, 100))
                    self.pantalla.blit(explicacion_texto, explicacion_rect)
                    
                    if superficie_progreso:
                        # Centrar la gráfica considerando el espacio del título
                        rect_progreso = superficie_progreso.get_rect(
                            center=(self.area_graficas_ancho // 2, (self.alto + 120) // 2)
                        )
                        self.pantalla.blit(superficie_progreso, rect_progreso)
                    else:
                        texto_sin_datos = fuente_mensaje.render("No hay datos de sesiones previas", True, (255, 255, 0))
                        rect_sin_datos = texto_sin_datos.get_rect(center=(self.area_graficas_ancho // 2, self.alto // 2))
                        self.pantalla.blit(texto_sin_datos, rect_sin_datos)

                pygame.draw.line(self.pantalla, self.color_linea, 
                                (self.area_graficas_ancho, 60), 
                                (self.area_graficas_ancho, self.alto - 60), 2)
                
                pos_mouse = pygame.mouse.get_pos()
                self.boton_captura.verificar_hover(pos_mouse)
                self.boton_cambiar.verificar_hover(pos_mouse)
                self.boton_guardar.verificar_hover(pos_mouse)
                self.boton_comparar.verificar_hover(pos_mouse)
                self.boton_regresar.verificar_hover(pos_mouse)
                
                if not mostrar_progreso:
                    # Modo de captura en tiempo real - mostrar todos los botones en columna derecha
                    self.boton_captura.dibujar(self.pantalla)
                    self.boton_cambiar.dibujar(self.pantalla)
                    self.boton_guardar.dibujar(self.pantalla)
                    self.boton_comparar.dibujar(self.pantalla)
                    self.boton_regresar.dibujar(self.pantalla)
                else:
                    # Modo de comparación de progreso - botones centrados más grandes
                    # Dibujar solo el botón "Volver a Tiempo Real" centrado
                    ancho_boton_centrado = 280
                    alto_boton_centrado = 60
                    x_centrado = self.area_graficas_ancho + (self.ancho - self.area_graficas_ancho - ancho_boton_centrado) // 2
                    y_boton_comparar = 150
                    
                    # Crear rectángulo temporal para el botón centrado más grande
                    rect_comparar_temp = pygame.Rect(x_centrado, y_boton_comparar, ancho_boton_centrado, alto_boton_centrado)
                    
                    # Guardar el rect original y aplicar el temporal
                    rect_original_comparar = self.boton_comparar.rect
                    self.boton_comparar.rect = rect_comparar_temp
                    self.boton_comparar.dibujar(self.pantalla)
                    self.boton_comparar.rect = rect_original_comparar
                    
                    # Botón "Regresar" también centrado en la parte inferior
                    y_boton_regresar = self.alto - alto_boton_centrado - 100
                    rect_regresar_temp = pygame.Rect(x_centrado, y_boton_regresar, ancho_boton_centrado, alto_boton_centrado)
                    
                    rect_original_regresar = self.boton_regresar.rect
                    self.boton_regresar.rect = rect_regresar_temp
                    self.boton_regresar.dibujar(self.pantalla)
                    self.boton_regresar.rect = rect_original_regresar
                
                if self.id_paciente and not mostrar_progreso:
                    # Solo mostrar info del paciente en modo tiempo real
                    texto_paciente_str = f"Paciente: {self.id_paciente}"
                    fuente_paciente = ajustar_fuente_a_ancho(texto_paciente_str, int(self.ancho * 0.35), 20, 12)
                    texto_paciente = fuente_paciente.render(texto_paciente_str, True, (255, 255, 0))
                    self.pantalla.blit(texto_paciente, (self.inicio_botones_x, 20))
                
                if mensaje_texto and tiempo_actual < mensaje_tiempo:
                    max_px = int(self.ancho * 0.9)
                    fuente_msg = ajustar_fuente_a_ancho(mensaje_texto, max_px, 24, 12)
                    msg_fit = recortar_con_ellipsis(mensaje_texto, fuente_msg, max_px)
                    texto = fuente_msg.render(msg_fit, True, VERDE if ("guardado" in mensaje_texto or "registrada" in mensaje_texto) else ROJO)
                    # Reservar espacio para barra inferior elevada en Progreso (id=3)
                    offset_barra_local = max(60, int(self.alto * 0.10)) if self.boton_id == 3 else 0
                    y_msg = max(
                        self.boton_regresar.rect.top - 10,
                        self.alto - alto_barra_inferior(self.alto) - offset_barra_local - 20
                    )
                    texto_rect = texto.get_rect(center=(self.ancho // 2, y_msg))
                    self.pantalla.blit(texto, texto_rect)
                
                for evento in pygame.event.get():
                    if evento.type == pygame.QUIT:
                        # Ya no se usa GPIO
                        raise CerrarPrograma("Usuario cerró ventana gráficas")
                    if evento.type == pygame.VIDEORESIZE:
                        nuevo_w, nuevo_h = ajustar_a_pantalla(evento.w, evento.h, 1000, 700)
                        self.pantalla = pygame.display.set_mode((nuevo_w, nuevo_h), pygame.RESIZABLE)
                        # Recalcular layout de controles de gráfica para evitar desajustes
                        if hasattr(self, 'redimensionar_grafica'):
                            self.redimensionar_grafica(nuevo_w, nuevo_h)
                    if evento.type == pygame.KEYDOWN:
                        if evento.key == pygame.K_F11:
                            self.fullscreen = not self.fullscreen
                            if self.fullscreen:
                                self.pantalla = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                                info = pygame.display.Info()
                                self.ancho, self.alto = info.current_w, info.current_h
                            else:
                                w, h = ajustar_a_pantalla(1400, 800, 1000, 700)
                                self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                                if hasattr(self, 'redimensionar_grafica'):
                                    self.redimensionar_grafica(w, h)
                            continue
                        if evento.key == pygame.K_ESCAPE and self.fullscreen:
                            self.fullscreen = False
                            w, h = ajustar_a_pantalla(1200, 700, 900, 600)
                            self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                            if hasattr(self, 'redimensionar_grafica'):
                                self.redimensionar_grafica(w, h)
                            continue
                    
                    if evento.type == pygame.MOUSEBUTTONDOWN:
                        # Manejar clics en modo comparación con rectángulos temporales más grandes
                        if mostrar_progreso:
                            # Calcular rectángulos temporales para botones centrados
                            ancho_boton_centrado = 280
                            alto_boton_centrado = 60
                            x_centrado = self.area_graficas_ancho + (self.ancho - self.area_graficas_ancho - ancho_boton_centrado) // 2
                            y_boton_comparar = 150
                            y_boton_regresar = self.alto - alto_boton_centrado - 100
                            
                            rect_comparar_temp = pygame.Rect(x_centrado, y_boton_comparar, ancho_boton_centrado, alto_boton_centrado)
                            rect_regresar_temp = pygame.Rect(x_centrado, y_boton_regresar, ancho_boton_centrado, alto_boton_centrado)
                            
                            if rect_comparar_temp.collidepoint(pos_mouse):
                                mostrar_progreso = False
                                self.boton_comparar.texto = "Comparar Progreso"
                            elif rect_regresar_temp.collidepoint(pos_mouse):
                                return
                        else:
                            # Modo tiempo real - lógica normal
                            if self.boton_regresar.verificar_clic(pos_mouse):
                                return
                            
                            if self.boton_comparar.verificar_clic(pos_mouse):
                                mostrar_progreso = True
                                superficie_progreso = self.generar_grafica_progreso()
                                self.boton_comparar.texto = "Volver a Tiempo Real"
                            
                            if self.boton_captura.verificar_clic(pos_mouse):
                                if not self.capturando:
                                    self.capturando = True
                                    self.inicio_sesion = time.time()
                                    self.datos_sesion_hombro = []
                                    self.datos_sesion_antebrazo = []
                                    self.boton_captura.texto = "Detener Captura"
                                    self.boton_captura.color = ROJO
                                else:
                                    self.capturando = False
                                    self.boton_captura.texto = "Iniciar Captura"
                                    self.boton_captura.color = VERDE
                            
                            if self.boton_cambiar.verificar_clic(pos_mouse):
                                if self.modo_visualizacion == "ambos":
                                    self.modo_visualizacion = "hombro"
                                    self.boton_cambiar.texto = "Mostrar Antebrazo"
                                elif self.modo_visualizacion == "hombro":
                                    self.modo_visualizacion = "antebrazo"
                                    self.boton_cambiar.texto = "Mostrar Ambos"
                                else:
                                    self.modo_visualizacion = "ambos"
                                    self.boton_cambiar.texto = "Mostrar Hombro"
                            
                            if self.boton_guardar.verificar_clic(pos_mouse):
                                exito, resultado = self.guardar_datos()
                                if exito:
                                    mensaje_texto = f"Datos guardados: {resultado}"
                                else:
                                    mensaje_texto = f"Error al guardar: {resultado}"
                                mensaje_tiempo = tiempo_actual + 5000
                
                # Barra inferior permanente
                dibujar_barra_inferior(
                    self.pantalla, self.ancho, self.alto,
                    bool(self.controlador_cnc and self.controlador_cnc.esta_conectado()),
                    None,
                    getattr(self, 'controlador_cnc', None)
                )
                pygame.display.flip()
                clock.tick(60)
        else:
            # Funcionalidad original para otros botones
            # Para Progreso del Paciente usar un mínimo mayor; otros mantienen mínimos anteriores
            min_w, min_h = (900, 600) if self.boton_id == 3 else (360, 420)
            self.ancho, self.alto = ajustar_a_pantalla(self.ancho_inicial, self.alto_inicial, min_w, min_h)
            info = pygame.display.Info()
            self.ancho, self.alto = info.current_w, info.current_h
            self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
            self.fullscreen = False
            # Ajustar layout inicial para cubrir ventana maximizada
            self.redimensionar(self.ancho, self.alto)
            
            titulo_str = self.nombres_menus.get(self.boton_id, f"Menú {self.boton_id}")
            # Usar fuente más grande para "Rutinas" y "Progreso del Paciente"
            if self.boton_id in (1, 3):
                fuente_titulo = ajustar_fuente_a_ancho(titulo_str, int(self.ancho * 0.95), 52, 24)
                # Color negro para Rutinas, verde para Progreso del Paciente
                color_titulo = NEGRO if self.boton_id == 1 else VERDE_BOTON
            else:
                fuente_titulo = ajustar_fuente_a_ancho(titulo_str, int(self.ancho * 0.95), 40, 14)
                color_titulo = VERDE_BOTON
            titulo_texto = fuente_titulo.render(titulo_str, True, color_titulo)
            
            fuente_mensaje = pygame.font.Font(None, 24)
            mensaje_texto = None
            
            clock = pygame.time.Clock()
            ejecutando = True
            
            while ejecutando:
                self.pantalla.fill(self.color_fondo)
                # Título más arriba para "Rutinas" y "Progreso del Paciente"
                if self.boton_id in (1, 3):
                    titulo_rect = titulo_texto.get_rect(center=(self.ancho // 2, 50))
                else:
                    titulo_rect = titulo_texto.get_rect(center=(self.ancho // 2, 25))
                self.pantalla.blit(titulo_texto, titulo_rect)
                
                pos_mouse = pygame.mouse.get_pos()
                ahora_ms = pygame.time.get_ticks()
                
                # Verificar cambios en la velocidad si está conectado
                if self.conexion_activa and self.controlador_cnc:
                    cambio, nueva_velocidad = self.controlador_cnc.verificar_cambios_velocidad()
                    if cambio:
                        self.velocidad_actual = nueva_velocidad
                
                for evento in pygame.event.get():
                    if evento.type == pygame.QUIT:
                        raise CerrarPrograma("Usuario cerró la ventana")
                    
                    # Manejar redimensionamiento de ventana
                    if evento.type == pygame.VIDEORESIZE:
                        nuevo_w, nuevo_h = ajustar_a_pantalla(evento.w, evento.h, min_w, min_h)
                        self.redimensionar(nuevo_w, nuevo_h)
                    if evento.type == pygame.KEYDOWN:
                        if evento.key == pygame.K_F11:
                            self.fullscreen = not self.fullscreen
                            if self.fullscreen:
                                self.pantalla = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                                info = pygame.display.Info()
                                self.redimensionar(info.current_w, info.current_h)
                            else:
                                # Si es Progreso del Paciente (id=3), restaurar a tamaño pantalla
                                info = pygame.display.Info()
                                if self.boton_id == 3:
                                    w, h = max(min_w, info.current_w), max(min_h, info.current_h)
                                else:
                                    w, h = ajustar_a_pantalla(self.ancho_inicial, self.alto_inicial, min_w, min_h)
                                self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                                self.redimensionar(w, h)
                            continue
                        if evento.key == pygame.K_ESCAPE and self.fullscreen:
                            self.fullscreen = False
                            # Si es Progreso del Paciente (id=3), restaurar a tamaño pantalla
                            info = pygame.display.Info()
                            if self.boton_id == 3:
                                w, h = max(min_w, info.current_w), max(min_h, info.current_h)
                            else:
                                w, h = ajustar_a_pantalla(self.ancho_inicial, self.alto_inicial, min_w, min_h)
                            self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                            self.redimensionar(w, h)
                            continue
                    
                    if evento.type == pygame.MOUSEBUTTONDOWN:
                        if self.boton_regresar.verificar_clic(pos_mouse):
                            return
                        
                        # Verificar clic en botón "Volver" de la izquierda (solo para boton_id==1)
                        if self.boton_id == 1 and hasattr(self, 'boton_volver_izq'):
                            if self.boton_volver_izq.verificar_clic(pos_mouse):
                                return
                        
                        # Ejecutar rutina solo con clic (no por movimiento)
                        if getattr(evento, 'button', 1) == 1:
                            # Selector zona/dificultad activos solo en boton_id==1
                            if self.boton_id == 1:
                                # Botones Paro/Reanudar
                                try:
                                    if self.boton_paro.verificar_clic(pos_mouse):
                                        if self.conexion_activa and self.controlador_cnc:
                                            self.controlador_cnc.paro_emergencia()
                                        continue
                                    if self.boton_reanudar_mov.verificar_clic(pos_mouse):
                                        if self.conexion_activa and self.controlador_cnc:
                                            self.controlador_cnc.reanudar_movimiento()
                                        continue
                                except Exception:
                                    pass
                                if self.radio_hombro.verificar_clic(pos_mouse):
                                    self.radio_hombro.seleccionado = True
                                    self.radio_antebrazo.seleccionado = False
                                    self.zona_actual = 'Hombro'
                                    self._actualizar_textos_rutinas()
                                elif self.radio_antebrazo.verificar_clic(pos_mouse):
                                    self.radio_hombro.seleccionado = False
                                    self.radio_antebrazo.seleccionado = True
                                    self.zona_actual = 'Antebrazo'
                                    self._actualizar_textos_rutinas()
                                # Selector de mano
                                if self.radio_derecha.verificar_clic(pos_mouse):
                                    self.radio_derecha.seleccionado = True
                                    self.radio_izquierda.seleccionado = False
                                    self.mano_actual = 'Derecha'
                                elif self.radio_izquierda.verificar_clic(pos_mouse):
                                    self.radio_derecha.seleccionado = False
                                    self.radio_izquierda.seleccionado = True
                                    self.mano_actual = 'Izquierda'
                                if self.slider_dificultad.verificar_clic(pos_mouse):
                                    self.dificultad = self.slider_dificultad.valor
                                # Slider de velocidad
                                if self.slider_velocidad_rutina.verificar_clic(pos_mouse):
                                    self.velocidad_actual = int(self.slider_velocidad_rutina.valor)
                                    if self.conexion_activa and self.controlador_cnc:
                                        try:
                                            self.controlador_cnc.velocidad_actual = self.velocidad_actual
                                            # Evitar aplicar cambio si hay rutina en ejecución
                                            if not getattr(self.controlador_cnc, 'ejecutando_rutina', False):
                                                self.controlador_cnc.aplicar_velocidad()
                                            with open(self.controlador_cnc.archivo_velocidad, 'w') as f:
                                                json.dump({'velocidad': self.velocidad_actual}, f)
                                        except Exception as e:
                                            print(f"Error al ajustar velocidad: {e}")
                                # Botones de utilidades CNC: Ver firmware, Guardar $$, Restablecer $$
                                try:
                                    if self.boton_ver_fw.verificar_clic(pos_mouse) and self.controlador_cnc:
                                        info = self.controlador_cnc.consultar_info_firmware()
                                        self.controlador_cnc.firmware_info = info or self.controlador_cnc.firmware_info
                                        try:
                                            mostrar_aviso_sistema("Firmware", self.controlador_cnc.firmware_info or "(sin datos)")
                                        except Exception:
                                            pass
                                    if self.boton_guardar_cfg.verificar_clic(pos_mouse) and self.controlador_cnc:
                                        ok, msg = self.controlador_cnc.guardar_configuracion_grbl()
                                        try:
                                            if ok:
                                                mostrar_aviso_sistema("Respaldo GRBL", f"Guardado en:\n{msg}")
                                            else:
                                                mostrar_aviso_sistema("Respaldo GRBL", f"No se pudo guardar: {msg}")
                                        except Exception:
                                            pass
                                    if self.boton_rest_cfg.verificar_clic(pos_mouse) and self.controlador_cnc:
                                        ok, msg = self.controlador_cnc.restablecer_configuracion_grbl()
                                        try:
                                            mostrar_aviso_sistema("Restauración GRBL", msg)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                            
                            # Manejo específico para Progreso del Paciente (boton_id==3)
                            if self.boton_id == 3:
                                for i, boton in enumerate(self.botones):
                                    if boton.verificar_clic(pos_mouse):
                                        subrutina = i + 1
                                        
                                        # Mapeo de botones a funciones
                                        acciones = {
                                            1: self._manejar_ver_progreso,
                                            2: self._manejar_comparar_sesiones,
                                            3: self._manejar_exportar_reporte,
                                            4: self._manejar_configurar_metas
                                        }
                                        
                                        # Ejecutar la acción correspondiente
                                        if subrutina in acciones:
                                            acciones[subrutina]()
                                        
                                        break  # Salir del loop de botones
                            
                            # Manejo para otros menús (Rutinas, etc.)
                            elif self.boton_id == 1:
                                subrutina = None
                                for i, boton in enumerate(self.botones):
                                    if boton.verificar_clic(pos_mouse):
                                        subrutina = i + 1
                                        rutina_key = (self.boton_id, subrutina)
                                        base_tiempo = TIEMPOS_RUTINAS.get(rutina_key, 1.0)
                                        break  # Solo tomar el primer botón clickeado
                                if subrutina is not None:
                                    if self.conexion_activa and self.controlador_cnc:
                                        # Bloqueo: exigir Punto de Origen antes de ejecutar cualquier rutina
                                        if not getattr(self.controlador_cnc, 'origen_establecido', False):
                                            try:
                                                mostrar_aviso_sistema("Aviso", "Aún no se ha establecido Punto de Origen")
                                            except Exception:
                                                pass
                                            return
                                        # Generar u obtener líneas según menú
                                        if self.boton_id == 1:
                                            lineas = self._generar_rutina_por_zona(self.zona_actual, subrutina, self.dificultad)
                                        else:
                                            lineas = self.obtener_rutina_usuario(self.boton_id, subrutina, getattr(self, 'zona_actual', None))
                                        # Si no hay líneas definidas, avisar y no ejecutar
                                        if not lineas:
                                            self._aviso_limite_mensaje = "Rutina vacía. Defínela primero."
                                            self._aviso_limite_expira_ms = pygame.time.get_ticks() + 3000
                                            return
                                        # Validar rango de seguridad
                                        ok_rng, msg_rng = self._validar_lineas_en_rango(lineas)
                                        if not ok_rng:
                                            self._aviso_limite_mensaje = msg_rng or "Rutina fuera de rango"
                                            self._aviso_limite_expira_ms = pygame.time.get_ticks() + 3000
                                            return
                                        
                                        # Preparar nombre de rutina para la captura
                                        nombre_rutina = f"{self.mano_actual} - {self.zona_actual} - {self._nombres_rutinas_por_zona(self.zona_actual)[subrutina-1]}"
                                        
                                        # Determinar si hay que invertir según la mano seleccionada
                                        invertir_rutina = (self.mano_actual == 'Izquierda')
                                        
                                        # Iniciar captura ECG automáticamente
                                        self._iniciar_captura_ecg(nombre_rutina)
                                        
                                        # Ejecutar en hilo para no bloquear la UI
                                        def _run_rutina_mem():
                                            exito_local = self.controlador_cnc.ejecutar_lineas_gcode(lineas, base_tiempo=0.4, invert=invertir_rutina)
                                            
                                            # Detener y guardar captura ECG automáticamente al finalizar
                                            self._detener_y_guardar_captura_ecg()
                                            
                                            if exito_local:
                                                try:
                                                    mostrar_aviso_sistema("Ejecución Exitosa", f"Rutina {nombre_rutina} ejecutada")
                                                except Exception:
                                                    pass
                                            else:
                                                detalle = ""
                                                try:
                                                    if self.controlador_cnc and getattr(self.controlador_cnc, 'ultimo_limite', ''):
                                                        detalle = self.controlador_cnc.ultimo_limite
                                                except Exception:
                                                    detalle = ""
                                                self._aviso_limite_mensaje = detalle or "Movimiento fuera de límites. Comando cancelado."
                                                self._aviso_limite_expira_ms = pygame.time.get_ticks() + 3000
                                        Thread(target=_run_rutina_mem, daemon=True).start()
                                    else:
                                        mensaje_texto = "CNC no conectada"
                    
                    if evento.type == pygame.MOUSEBUTTONUP and self.boton_id == 1:
                        # Detener arrastre al soltar el botón del mouse
                        try:
                            self.slider_dificultad.verificar_soltar()
                        except Exception:
                            pass
                        try:
                            self.slider_velocidad_rutina.verificar_soltar()
                        except Exception:
                            pass
                    if evento.type == pygame.MOUSEMOTION and self.boton_id == 1:
                        if self.slider_dificultad.verificar_arrastre(pos_mouse):
                            self.dificultad = self.slider_dificultad.valor
                        if self.slider_velocidad_rutina.verificar_arrastre(pos_mouse):
                            self.velocidad_actual = int(self.slider_velocidad_rutina.valor)
                            if self.conexion_activa and self.controlador_cnc:
                                try:
                                    self.controlador_cnc.velocidad_actual = self.velocidad_actual
                                    # Guardar archivo para que verificar_cambios_velocidad lo detecte
                                    with open(self.controlador_cnc.archivo_velocidad, 'w') as f:
                                        json.dump({'velocidad': self.velocidad_actual}, f)
                                    # Si hay rutina en ejecución, verificar_cambios_velocidad() aplicará el cambio
                                    if not getattr(self.controlador_cnc, 'ejecutando_rutina', False):
                                        self.controlador_cnc.aplicar_velocidad()
                                except Exception as e:
                                    print(f"Error al ajustar velocidad: {e}")
                        # No ejecutar rutinas en MOUSEMOTION; sólo actualizar sliders/hover
                
                # Leer sensores ECG si la captura está activa (para ventana Rutinas)
                if self.boton_id == 1 and self.captura_ecg_activa:
                    self._leer_sensor_ecg()
                
                # Actualizar hover y dibujar botones
                for boton in self.botones:
                    boton.verificar_hover(pos_mouse)
                    boton.dibujar(self.pantalla)
                # Hover/dibujo de Paro/Reanudar
                if self.boton_id == 1:
                    try:
                        self.boton_paro.verificar_hover(pos_mouse)
                        self.boton_reanudar_mov.verificar_hover(pos_mouse)
                        self.boton_ver_fw.verificar_hover(pos_mouse)
                        self.boton_guardar_cfg.verificar_hover(pos_mouse)
                        self.boton_rest_cfg.verificar_hover(pos_mouse)
                        self.boton_paro.dibujar(self.pantalla)
                        self.boton_reanudar_mov.dibujar(self.pantalla)
                        self.boton_ver_fw.dibujar(self.pantalla)
                        self.boton_guardar_cfg.dibujar(self.pantalla)
                        self.boton_rest_cfg.dibujar(self.pantalla)
                        # Dibujar botón "Volver" en la izquierda
                        if hasattr(self, 'boton_volver_izq'):
                            self.boton_volver_izq.verificar_hover(pos_mouse)
                            self.boton_volver_izq.dibujar(self.pantalla)
                    except Exception:
                        pass
                # Detectar rutina bajo el cursor para vista previa (default 1)
                rutina_hover = 1
                for idx, boton in enumerate(self.botones):
                    if boton.rect.collidepoint(pos_mouse):
                        rutina_hover = idx + 1
                        break
                
                self.boton_regresar.verificar_hover(pos_mouse)
                self.boton_regresar.dibujar(self.pantalla)
                # Dibujar selector zona/dificultad si aplica
                if self.boton_id == 1:
                    # Dibujar etiqueta "Zona de ejercicio:" antes de los radio buttons - MÁS ARRIBA
                    fuente_etiqueta_zona = pygame.font.Font(None, 28)
                    etiqueta_zona = fuente_etiqueta_zona.render("Zona de ejercicio:", True, (0, 100, 0))
                    # Posicionar más arriba (cambio de -28 a -35)
                    y_etiqueta_zona = self.radio_hombro.y - 35
                    self.pantalla.blit(etiqueta_zona, (self.radio_hombro.x, y_etiqueta_zona))
                    
                    self.radio_hombro.dibujar(self.pantalla)
                    self.radio_antebrazo.dibujar(self.pantalla)
                    
                    # Dibujar etiqueta "Mano:" antes de los radio buttons de mano - MÁS SEPARACIÓN
                    etiqueta_mano = fuente_etiqueta_zona.render("Mano:", True, (0, 100, 0))
                    y_etiqueta_mano = self.radio_derecha.y - 40  # Aumentado de -35 a -40
                    self.pantalla.blit(etiqueta_mano, (self.radio_derecha.x, y_etiqueta_mano))
                    
                    self.radio_derecha.dibujar(self.pantalla)
                    self.radio_izquierda.dibujar(self.pantalla)
                    
                    self.slider_dificultad.dibujar(self.pantalla)
                    # Mostrar el nivel de dificultad (solo número, sin %)
                    try:
                        fuente_val_dif = pygame.font.Font(None, 22)
                        dif_surface = fuente_val_dif.render(f"{int(self.dificultad)}", True, NEGRO)
                        dif_rect = dif_surface.get_rect()
                        dif_rect.midleft = (self.slider_dificultad.rect.right + 10, self.slider_dificultad.rect.centery)
                        # Evitar invadir la columna de botones derecha
                        col_w = min(320, int(self.ancho * 0.28))
                        limite_der = self.ancho - col_w - 10
                        if dif_rect.right > limite_der:
                            dif_rect.right = limite_der
                        self.pantalla.blit(dif_surface, dif_rect)
                    except Exception:
                        pass
                    # Etiqueta y slider de velocidad
                    fuente_lbl = pygame.font.Font(None, 28)
                    lblv = fuente_lbl.render("Velocidad", True, (0, 100, 0))
                    label_pos = (self.slider_velocidad_rutina.rect.x, self.slider_velocidad_rutina.rect.y - 24)
                    self.pantalla.blit(lblv, label_pos)
                    self.slider_velocidad_rutina.dibujar(self.pantalla)
                    # Hacer que el valor de la barra sea autoritativo: forzar OV/M220 a este valor cuando no se arrastra
                    try:
                        objetivo_ui = int(self.slider_velocidad_rutina.valor)
                        # Mantener el número mostrado igual al slider
                        self.velocidad_actual = objetivo_ui
                        if (
                            self.conexion_activa and self.controlador_cnc
                            and not getattr(self.slider_velocidad_rutina, 'arrastrando', False)
                            and not getattr(self.controlador_cnc, 'ejecutando_rutina', False)
                        ):
                            # Solo aplicar si difiere para evitar trabajo innecesario
                            actual = int(getattr(self.controlador_cnc, 'override_actual', -1))
                            ahora = time.time()
                            if actual != objetivo_ui and (ahora - getattr(self.controlador_cnc, '_ultimo_aplicar_ov', 0.0)) >= getattr(self.controlador_cnc, '_intervalo_aplicar_ov', 0.08):
                                self.controlador_cnc.velocidad_actual = objetivo_ui
                                self.controlador_cnc.aplicar_velocidad()
                                try:
                                    self.controlador_cnc._ultimo_aplicar_ov = ahora
                                except Exception:
                                    pass
                        fuente_val = pygame.font.Font(None, 22)
                        val_surface = fuente_val.render(f"{int(self.velocidad_actual)}%", True, NEGRO)
                        val_rect = val_surface.get_rect()
                        val_rect.midleft = (self.slider_velocidad_rutina.rect.right + 10, self.slider_velocidad_rutina.rect.centery)
                        # Evitar invadir la columna de botones derecha
                        col_w = min(320, int(self.ancho * 0.28))
                        limite_der = self.ancho - col_w - 10
                        if val_rect.right > limite_der:
                            val_rect.right = limite_der
                        self.pantalla.blit(val_surface, val_rect)
                    except Exception:
                        pass
                    # Indicador de velocidad real reportada por GRBL (override y feed), en la misma línea del porcentaje
                    try:
                        if self.controlador_cnc:
                            ov, f_act = self.controlador_cnc.obtener_estado_velocidad()
                            fuente_stat = pygame.font.Font(None, 18)
                            txt = f"Ov:{ov}%  F:{int(f_act)}"
                            stat_surface = fuente_stat.render(txt, True, (30, 100, 30))
                            stat_rect = stat_surface.get_rect()
                            # Colocar a la derecha del porcentaje actual
                            stat_rect.midleft = (val_rect.right + 12, val_rect.centery)
                            # Evitar invadir la columna de botones derecha
                            col_w = min(320, int(self.ancho * 0.28))
                            limite_der = self.ancho - col_w - 10
                            if stat_rect.right > limite_der:
                                stat_rect.right = limite_der
                            self.pantalla.blit(stat_surface, stat_rect)
                    except Exception:
                        pass
                    # Etiqueta dificultad con fuente más grande y color verde oscuro
                    fuente_lbl_dif = pygame.font.Font(None, 28)
                    lbl = fuente_lbl_dif.render("Dificultad", True, (0, 100, 0))
                    self.pantalla.blit(lbl, (self.slider_dificultad.rect.x, self.slider_dificultad.rect.y - 24))
                    # Vista previa del patrón
                    self.dibujar_vista_previa(self.zona_actual, rutina_hover, self.dificultad)
                
                # Mostrar mensaje si existe (subido respecto a la barra inferior)
                if mensaje_texto:
                    fuente_mensaje = ajustar_fuente_a_ancho(mensaje_texto, int(self.ancho * 0.9), 24, 12)
                    texto = fuente_mensaje.render(mensaje_texto, True, ROJO)
                    # Elevar el mensaje dejando mayor margen sobre la barra
                    margen_inferior_msg = 100
                    y_msg = self.alto - alto_barra_inferior(self.alto) - margen_inferior_msg
                    texto_rect = texto.get_rect(center=(self.ancho // 2, y_msg))
                    self.pantalla.blit(texto, texto_rect)
                # Aviso discreto de límites (solo Rutinas)
                if self.boton_id == 1 and self._aviso_limite_mensaje and ahora_ms < self._aviso_limite_expira_ms:
                    try:
                        fuente_tip = pygame.font.Font(None, 22)
                        txt = fuente_tip.render(self._aviso_limite_mensaje, True, ROJO)
                        # Colocar sobre la barra inferior, margen izquierdo
                        margen = 10
                        y_tip = self.alto - alto_barra_inferior(self.alto) - 30
                        rect_tip = txt.get_rect(topleft=(margen, y_tip))
                        self.pantalla.blit(txt, rect_tip)
                    except Exception:
                        pass
                elif self.boton_id == 1 and ahora_ms >= self._aviso_limite_expira_ms:
                    self._aviso_limite_mensaje = ""
                # Si hay detalle de límite en el controlador y debug activo, mostrarlo breve
                if (
                    self.boton_id == 1 and self.controlador_cnc and getattr(self.controlador_cnc, 'ultimo_limite', '')
                    and getattr(self.controlador_cnc, 'debug_limites', False)
                ):
                    try:
                        fuente_det = pygame.font.Font(None, 20)
                        det = self.controlador_cnc.ultimo_limite
                        det_fit = recortar_con_ellipsis(det, fuente_det, int(self.ancho * 0.9))
                        surf = fuente_det.render(det_fit, True, (200, 80, 80))
                        y_det = self.alto - alto_barra_inferior(self.alto) - 52
                        self.pantalla.blit(surf, (10, y_det))
                    except Exception:
                        pass
                
                # Mostrar estado de conexión y velocidad
                # En "Progreso del Paciente" (id=3): ocultar el texto cuando está desconectado
                if self.boton_id == 3:
                    if self.conexion_activa:
                        estado_texto = "Conectado"
                        estado_color = VERDE
                        fuente_estado = ajustar_fuente_a_ancho(estado_texto, int(self.ancho * 0.5), 24, 12)
                        texto_estado = fuente_estado.render(estado_texto, True, estado_color)
                        # Elevar sobre la barra levantada
                        offset_barra_local = max(60, int(self.alto * 0.10))
                        rect_estado = texto_estado.get_rect(bottomleft=(10, self.alto - alto_barra_inferior(self.alto) - offset_barra_local - 10))
                        self.pantalla.blit(texto_estado, rect_estado)
                    # Si no está conectado, no mostramos nada
                else:
                    estado_texto = "Estado: Conectado" if self.conexion_activa else "Estado: Desconectado"
                    estado_color = VERDE if self.conexion_activa else ROJO
                    fuente_estado = ajustar_fuente_a_ancho(estado_texto, int(self.ancho * 0.5), 24, 12)
                    texto_estado = fuente_estado.render(estado_texto, True, estado_color)
                    rect_estado = texto_estado.get_rect(bottomleft=(10, self.alto - alto_barra_inferior(self.alto) - 10))
                    self.pantalla.blit(texto_estado, rect_estado)
                
                # Mostrar indicador de captura ECG activa (solo para ventana Rutinas)
                if self.boton_id == 1 and self.captura_ecg_activa:
                    try:
                        fuente_captura = pygame.font.Font(None, 26)
                        texto_captura = fuente_captura.render("● Capturando datos ECG...", True, ROJO)
                        rect_captura = texto_captura.get_rect(topright=(self.ancho - 10, 10))
                        self.pantalla.blit(texto_captura, rect_captura)
                        
                        # Mostrar nombre de la rutina
                        if self.nombre_rutina_actual:
                            fuente_rutina = pygame.font.Font(None, 22)
                            texto_rutina = fuente_rutina.render(f"Rutina: {self.nombre_rutina_actual}", True, (100, 100, 100))
                            rect_rutina = texto_rutina.get_rect(topright=(self.ancho - 10, 36))
                            self.pantalla.blit(texto_rutina, rect_rutina)
                    except Exception:
                        pass
                
                # Ocultar indicador numérico de velocidad en la parte derecha de la ventana
                if self.conexion_activa and self.boton_id != 1:
                    vel_str = f"Velocidad: {self.velocidad_actual}%"
                    fuente_vel = ajustar_fuente_a_ancho(vel_str, int(self.ancho * 0.4), 24, 12)
                    texto_velocidad = fuente_vel.render(vel_str, True, VERDE)
                    rect_velocidad = texto_velocidad.get_rect(topright=(self.ancho - 10, 10))
                    self.pantalla.blit(texto_velocidad, rect_velocidad)
                    
                    # Mostrar estado de limit switches basado en X/Y/Z
                    any_switch = False
                    try:
                        any_switch = bool(self.controlador_cnc.limit_switch_x or self.controlador_cnc.limit_switch_y or self.controlador_cnc.limit_switch_z)
                    except Exception:
                        any_switch = False
                    color_switch = VERDE if any_switch else GRIS
                    texto_switch = fuente_mensaje.render(
                        f"Switches: {'Activos' if any_switch else 'Inactivos'}", 
                        True, color_switch
                    )
                    rect_switch = texto_switch.get_rect(topright=(self.ancho - 10, 40))
                    self.pantalla.blit(texto_switch, rect_switch)
                
                # Barra inferior permanente (elevada en Progreso del Paciente)
                offset_barra_local = max(60, int(self.alto * 0.10)) if self.boton_id == 3 else 0
                dibujar_barra_inferior(
                    self.pantalla, self.ancho, self.alto,
                    bool(self.controlador_cnc and self.controlador_cnc.esta_conectado()),
                    None,
                    getattr(self, 'controlador_cnc', None),
                    offset_px=offset_barra_local
                )
                pygame.display.flip()
                clock.tick(60)
            
            return not ejecutando  # Retorna False si se cerró la ventana

    def __del__(self):
        """Limpia los recursos al finalizar"""
        if hasattr(self, 'sensor_arduino') and self.sensor_arduino:
            self.sensor_arduino.desconectar()

class GraficasMusculares:
    def __init__(self, id_paciente):
        self.id_paciente = id_paciente
        self.gestor_pacientes = GestorPacientes()
        
        # Guardar la pantalla actual antes de crear una nueva
        self.pantalla_anterior = pygame.display.get_surface()
        
        # Configuración de ventana: iniciar maximizadas (modo ventana y redimensionable)
        info = pygame.display.Info()
        self.ancho, self.alto = info.current_w, info.current_h
        self.fullscreen = False
        self.pantalla = pygame.display.set_mode((self.ancho, self.alto), pygame.RESIZABLE)
        pygame.display.set_caption(f"Gráficas Musculares - Paciente: {id_paciente}")
        
        # Fuentes
        self.fuente = pygame.font.Font(None, 24)
        self.fuente_titulo = pygame.font.Font(None, 32)
        self.fuente_pequeña = pygame.font.Font(None, 20)
        
        # Variables de control
        self.tipo_grafica = "progreso"  # "progreso", "comparacion", "sesion"
        self.datos_paciente = None
        self.superficie_grafica = None
        
        # Crear botones
        self.crear_botones()
        
        # Cargar datos del paciente
        self.cargar_datos_paciente()
        
        self.superficie_grafica_hombro = None
        self.superficie_grafica_antebrazo = None
        
        # self.generar_graficas()
        
        # Botones
        self.boton_regresar = Boton(self.ancho - 220, self.alto - 70, 200, 50, "Regresar", ROJO)
        
        # Mensajes de estado
        self.mensaje = f"Gráficas del paciente: {id_paciente}"
        self.color_mensaje = VERDE
        self.mostrar_mensaje_tiempo = pygame.time.get_ticks() + 3000

    def crear_botones(self):
        """Crea todos los botones de la interfaz"""
        # Dimensiones de botones mejoradas
        ancho_boton = 200
        alto_boton = 50
        espaciado = 20  # espacio entre botones
        y_botones = 100  # más abajo para dejar espacio al título
        
        # Calcular ancho total de todos los botones
        num_botones = 4
        ancho_total = (ancho_boton * num_botones) + (espaciado * (num_botones - 1))
        
        # Centrar los botones horizontalmente
        x_inicio = (self.ancho - ancho_total) // 2
        
        # Colores mejorados y más visibles para fondos
        color_progreso = (46, 204, 113)      # Verde brillante
        color_comparacion = (52, 152, 219)   # Azul brillante
        color_sesion = (155, 89, 182)        # Morado
        color_cerrar = (231, 76, 60)         # Rojo brillante
        
        # Color de texto blanco para todos los botones
        color_texto = (255, 255, 255)
        
        # Crear botones centrados con texto blanco
        self.boton_progreso = Boton(
            x_inicio, y_botones, ancho_boton, alto_boton,
            "Progreso General", color_progreso, self.fuente, color_texto
        )
        
        self.boton_comparacion = Boton(
            x_inicio + (ancho_boton + espaciado), y_botones, ancho_boton, alto_boton,
            "Comparación", color_comparacion, self.fuente, color_texto
        )
        
        self.boton_sesion = Boton(
            x_inicio + 2 * (ancho_boton + espaciado), y_botones, ancho_boton, alto_boton,
            "Última Sesión", color_sesion, self.fuente, color_texto
        )
        
        self.boton_volver = Boton(
            x_inicio + 3 * (ancho_boton + espaciado), y_botones, ancho_boton, alto_boton,
            "Volver", color_cerrar, self.fuente, color_texto
        )

    def cargar_datos_paciente(self):
        """Carga los datos del paciente desde el archivo CSV de sesiones reales"""
        # Intentar importar pandas si no se ha hecho aún
        if not _try_import_pandas():
            print("[AVISO] pandas no está disponible; no se podrán mostrar gráficas de progreso.")
            self.datos_paciente = None
            return
        
        self.datos_paciente = self.gestor_pacientes.obtener_datos_progreso(self.id_paciente)
        print(f"[DEBUG] Datos reales cargados: {self.datos_paciente is not None}")
        if self.datos_paciente is not None:
            print(f"[DEBUG] Número de sesiones reales: {len(self.datos_paciente)}")
            print(f"[DEBUG] Columnas disponibles: {list(self.datos_paciente.columns)}")
        else:
            print("[INFO] No hay datos de sesiones reales para este paciente")
            print("[INFO] Para generar datos, use las funciones de captura ECG en tiempo real")

    def generar_graficas(self):
        """Genera las gráficas según el tipo seleccionado"""
        if not _try_import_matplotlib():
            self.superficie_grafica = None
            return
        if self.datos_paciente is None or len(self.datos_paciente) == 0:
            print("[INFO] No hay sesiones reales guardadas para este paciente")
            print("[INFO] Para generar gráficas, primero realice sesiones de ejercicios con captura ECG")
            self.superficie_grafica = None
            return
        
        try:
            # Cerrar cualquier figura previa para evitar fugas de memoria
            plt.close('all')
            
            # Configurar matplotlib para renderizado en memoria
            plt.ioff()
            
            print(f"[DEBUG] Generando gráfica tipo: {self.tipo_grafica}")
            
            # Calcular tamaño apropiado para la gráfica basado en el espacio disponible
            # Espacio disponible: ancho completo, alto desde y=170 hasta alto-100 (dejando margen)
            espacio_alto = self.alto - 170 - 100  # 170 de botones arriba, 100 de margen abajo
            espacio_ancho = self.ancho - 100  # Margen de 50px a cada lado
            
            # Convertir pixeles a pulgadas (asumiendo 100 DPI)
            ancho_fig = min(espacio_ancho / 100, 10)  # Máximo 10 pulgadas
            alto_fig = min(espacio_alto / 100, 6)     # Máximo 6 pulgadas
            
            print(f"[DEBUG] Tamaño figura: {ancho_fig:.1f}x{alto_fig:.1f} pulgadas")
            
            # Resetear configuración de matplotlib para asegurar colores de texto visibles
            plt.rcParams['axes.edgecolor'] = 'black'
            plt.rcParams['axes.labelcolor'] = 'black'
            plt.rcParams['xtick.color'] = 'black'
            plt.rcParams['ytick.color'] = 'black'
            plt.rcParams['text.color'] = 'black'
            plt.rcParams['axes.titlecolor'] = 'black'
            
            # Crear figura con fondo blanco explícito y tamaño ajustado
            fig = plt.figure(figsize=(ancho_fig, alto_fig), facecolor='white', dpi=100)
            ax = fig.add_subplot(111, facecolor='white')
            
            # Configurar colores del eje explícitamente
            ax.xaxis.label.set_color('black')
            ax.yaxis.label.set_color('black')
            ax.title.set_color('black')
            ax.tick_params(colors='black')
            
            if self.tipo_grafica == "progreso":
                self.generar_grafica_progreso(ax)
            elif self.tipo_grafica == "comparacion":
                self.generar_grafica_comparacion(ax)
            elif self.tipo_grafica == "sesion":
                self.generar_grafica_sesion(ax)
            
            # Asegurar layout ajustado con más espacio para etiquetas
            fig.tight_layout(pad=3.0)
            
            # Convertir a superficie de Pygame
            canvas = FigureCanvasAgg(fig)
            canvas.draw()
            
            print(f"[DEBUG] Canvas dibujado, tamaño: {canvas.get_width_height()}")
            
            # Obtener los datos de la imagen
            buf = canvas.buffer_rgba()
            size = canvas.get_width_height()
            
            # Convertir a bytes si es necesario
            if isinstance(buf, memoryview):
                buf = bytes(buf)
            
            # Crear superficie de Pygame desde los datos RGBA
            self.superficie_grafica = pygame.image.frombuffer(buf, size, "RGBA")
            
            print(f"[DEBUG] Superficie creada exitosamente: {self.superficie_grafica.get_size()}")
            
            # Cerrar la figura
            plt.close(fig)
            
        except Exception as e:
            print(f"[ERROR] Error al generar gráfica: {e}")
            import traceback
            traceback.print_exc()
            self.superficie_grafica = None

    def generar_grafica_progreso(self, ax):
        """Genera gráfica de progreso general"""
        print(f"[DEBUG] Generando gráfica de progreso...")
        print(f"[DEBUG] Tipo de datos_paciente: {type(self.datos_paciente)}")
        print(f"[DEBUG] Columnas disponibles: {list(self.datos_paciente.columns)}")
        print(f"[DEBUG] Primeras filas:")
        print(self.datos_paciente.head())
        
        sesiones = self.datos_paciente['Numero_Sesion']
        hombro = self.datos_paciente['Esfuerzo_Hombro_Promedio']
        antebrazo = self.datos_paciente['Esfuerzo_Antebrazo_Promedio']
        
        print(f"[DEBUG] Sesiones: {len(sesiones)} valores")
        print(f"[DEBUG] Hombro: min={hombro.min():.2f}, max={hombro.max():.2f}, mean={hombro.mean():.2f}")
        print(f"[DEBUG] Antebrazo: min={antebrazo.min():.2f}, max={antebrazo.max():.2f}, mean={antebrazo.mean():.2f}")
        
        ax.plot(sesiones, hombro, 'b-o', label='Hombro', linewidth=3, markersize=10)
        ax.plot(sesiones, antebrazo, 'r-s', label='Antebrazo', linewidth=3, markersize=10)
        
        ax.set_xlabel('Número de Sesión', fontsize=16, color='black', fontweight='bold')
        ax.set_ylabel('Esfuerzo Promedio (%)', fontsize=16, color='black', fontweight='bold')
        ax.set_title(f'Progreso Muscular - Paciente: {self.id_paciente}', fontsize=20, fontweight='bold', color='black', pad=20)
        ax.legend(fontsize=14, frameon=True, fancybox=True, shadow=True, 
                 facecolor='white', edgecolor='black', framealpha=1.0)
        ax.grid(True, alpha=0.4, color='gray', linestyle='-', linewidth=0.5)
        ax.set_ylim(-5, 110)
        
        # Configurar colores de ticks y bordes explícitamente
        ax.tick_params(axis='both', which='major', labelsize=12, colors='black')
        ax.spines['bottom'].set_color('black')
        ax.spines['top'].set_color('black')
        ax.spines['right'].set_color('black')
        ax.spines['left'].set_color('black')

    def generar_grafica_comparacion(self, ax):
        """Genera gráfica de comparación entre músculos"""
        promedio_hombro = self.datos_paciente['Esfuerzo_Hombro_Promedio'].mean()
        promedio_antebrazo = self.datos_paciente['Esfuerzo_Antebrazo_Promedio'].mean()
        
        musculos = ['Hombro', 'Antebrazo']
        promedios = [promedio_hombro, promedio_antebrazo]
        colores = ['skyblue', 'lightcoral']
        
        bars = ax.bar(musculos, promedios, color=colores, alpha=0.9, edgecolor='black', linewidth=3)
        
        # Agregar valores en las barras
        for bar, valor in zip(bars, promedios):
            altura = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., altura + 2,
                   f'{valor:.1f}%', ha='center', va='bottom', fontsize=16, fontweight='bold', color='black')
        
        ax.set_ylabel('Esfuerzo Promedio (%)', fontsize=16, color='black', fontweight='bold')
        ax.set_xlabel('Grupos Musculares', fontsize=16, color='black', fontweight='bold')
        ax.set_title(f'Comparación Muscular - Paciente: {self.id_paciente}', fontsize=20, fontweight='bold', color='black', pad=20)
        ax.set_ylim(-5, 110)
        ax.grid(True, alpha=0.4, axis='y', color='gray', linestyle='-', linewidth=0.5)
        
        # Configurar colores de ticks y bordes explícitamente
        ax.tick_params(axis='both', which='major', labelsize=14, colors='black')
        ax.spines['bottom'].set_color('black')
        ax.spines['top'].set_color('black')
        ax.spines['right'].set_color('black')
        ax.spines['left'].set_color('black')

    def generar_grafica_sesion(self, ax):
        """Genera gráfica de la última sesión"""
        if len(self.datos_paciente) == 0:
            return
        
        ultima_sesion = self.datos_paciente.iloc[-1]
        
        musculos = ['Hombro', 'Antebrazo']
        esfuerzos = [ultima_sesion['Esfuerzo_Hombro_Promedio'], 
                    ultima_sesion['Esfuerzo_Antebrazo_Promedio']]
        colores = ['gold', 'lightgreen']
        
        bars = ax.bar(musculos, esfuerzos, color=colores, alpha=0.9, edgecolor='black', linewidth=3)
        
        # Agregar valores en las barras
        for bar, valor in zip(bars, esfuerzos):
            altura = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., altura + 2,
                   f'{valor:.1f}%', ha='center', va='bottom', fontsize=16, fontweight='bold', color='black')
        
        fecha_sesion = ultima_sesion['Fecha']
        ax.set_ylabel('Esfuerzo (%)', fontsize=16, color='black', fontweight='bold')
        ax.set_xlabel('Grupos Musculares', fontsize=16, color='black', fontweight='bold')
        ax.set_title(f'Última Sesión - {fecha_sesion}', fontsize=20, fontweight='bold', color='black', pad=20)
        ax.set_ylim(-5, 110)
        ax.grid(True, alpha=0.4, axis='y', color='gray', linestyle='-', linewidth=0.5)
        
        # Configurar colores de ticks y bordes explícitamente
        ax.tick_params(axis='both', which='major', labelsize=14, colors='black')
        ax.spines['bottom'].set_color('black')
        ax.spines['top'].set_color('black')
        ax.spines['right'].set_color('black')
        ax.spines['left'].set_color('black')

    def dibujar_interfaz(self):
        """Dibuja toda la interfaz de gráficas"""
        # Título centrado en la parte superior
        titulo_surface = self.fuente_titulo.render("Gráficas de Esfuerzo Muscular", True, NEGRO)
        titulo_rect = titulo_surface.get_rect(centerx=self.ancho // 2, top=20)
        self.pantalla.blit(titulo_surface, titulo_rect)
        
        # Dibujar botones (ya están centrados)
        self.boton_progreso.dibujar(self.pantalla)
        self.boton_comparacion.dibujar(self.pantalla)
        self.boton_sesion.dibujar(self.pantalla)
        self.boton_volver.dibujar(self.pantalla)
        
        # Resaltar botón activo con un borde más visible
        borde_activo = 5
        if self.tipo_grafica == "progreso":
            pygame.draw.rect(self.pantalla, (0, 0, 0), self.boton_progreso.rect, borde_activo)
        elif self.tipo_grafica == "comparacion":
            pygame.draw.rect(self.pantalla, (0, 0, 0), self.boton_comparacion.rect, borde_activo)
        elif self.tipo_grafica == "sesion":
            pygame.draw.rect(self.pantalla, (0, 0, 0), self.boton_sesion.rect, borde_activo)
        
        # Dibujar gráfica centrada debajo de los botones
        y_grafica = 170  # Debajo de los botones (100 + 50 + 20)
        
        if self.superficie_grafica:
            # Calcular posición centrada para la gráfica
            graf_x = (self.ancho - self.superficie_grafica.get_width()) // 2
            self.pantalla.blit(self.superficie_grafica, (graf_x, y_grafica))
        else:
            # Mostrar mensaje informativo cuando no hay datos reales
            y_centro = (self.alto + y_grafica) // 2
            
            mensaje1 = self.fuente.render("No hay sesiones de ejercicios guardadas", True, ROJO)
            rect1 = mensaje1.get_rect(center=(self.ancho // 2, y_centro - 40))
            self.pantalla.blit(mensaje1, rect1)
            
            mensaje2 = self.fuente_pequeña.render("Para generar gráficas de progreso:", True, NEGRO)
            rect2 = mensaje2.get_rect(center=(self.ancho // 2, y_centro + 10))
            self.pantalla.blit(mensaje2, rect2)
            
            mensaje3 = self.fuente_pequeña.render("1. Vaya a 'Gráficas' en el menú principal", True, NEGRO)
            rect3 = mensaje3.get_rect(center=(self.ancho // 2, y_centro + 35))
            self.pantalla.blit(mensaje3, rect3)
            
            mensaje4 = self.fuente_pequeña.render("2. Realice ejercicios con captura ECG en tiempo real", True, NEGRO)
            rect4 = mensaje4.get_rect(center=(self.ancho // 2, y_centro + 60))
            self.pantalla.blit(mensaje4, rect4)
            
            mensaje5 = self.fuente_pequeña.render("3. Los datos se guardarán automáticamente para análisis", True, NEGRO)
            rect5 = mensaje5.get_rect(center=(self.ancho // 2, y_centro + 85))
            self.pantalla.blit(mensaje5, rect5)
        
        # Información del paciente en la esquina superior derecha
        info_text = f"Paciente: {self.id_paciente}"
        if self.datos_paciente is not None and len(self.datos_paciente) > 0:
            info_text += f" | Sesiones: {len(self.datos_paciente)}"

        info_surface = self.fuente_pequeña.render(info_text, True, NEGRO)
        info_rect = info_surface.get_rect(topright=(self.ancho - 20, 20))
        self.pantalla.blit(info_surface, info_rect)
    
    def dibujar_vista_previa(self, zona: str, numero: int, dificultad: int):
        try:
            lines = self.generar_rutina_dinamica(zona, numero, dificultad)
        except Exception:
            return
        # Convertir a puntos para renderizar (solo G0/G1 X Y)
        pts = []
        x, y = None, None
        for ln in lines:
            parts = ln.strip().split()
            if not parts:
                continue
            if parts[0] not in ('G0', 'G1'):
                continue
            xi = yi = None
            for p in parts[1:]:
                if p.startswith('X'):
                    try:
                        xi = float(p[1:])
                    except: pass
                elif p.startswith('Y'):
                    try:
                        yi = float(p[1:])
                    except: pass
            x = xi if xi is not None else x
            y = yi if yi is not None else y
            if x is not None and y is not None:
                pts.append((x, y))
        if len(pts) < 2:
            return
        # Panel de vista previa en área izquierda para mantener consistencia
        col_w = min(320, int(self.ancho * 0.28))
        margen_izq = max(16, int(self.ancho * 0.04))
        panel_w = min(520, int((self.ancho - col_w - margen_izq - 30) * 0.9))
        panel_h = min(420, int(self.alto * 0.45))
        panel_x = margen_izq
        panel_y = max(80, int(self.alto * 0.25))
        rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        pygame.draw.rect(self.pantalla, (245, 245, 245), rect)
        pygame.draw.rect(self.pantalla, (100, 100, 100), rect, 2)
        # Normalizar puntos al panel (workspace 0..40)
        def map_pt(px, py):
            u = (px / 40.0)
            v = 1.0 - (py / 40.0)
            sx = rect.x + int(u * (rect.width - 10)) + 5
            sy = rect.y + int(v * (rect.height - 10)) + 5
            return sx, sy
        # Dibujar ejes y caja
        pygame.draw.line(self.pantalla, (180,180,180), (rect.x+5, rect.bottom-5), (rect.right-5, rect.bottom-5), 1)
        pygame.draw.line(self.pantalla, (180,180,180), (rect.x+5, rect.y+5), (rect.x+5, rect.bottom-5), 1)
        # Dibujar trayectoria
        prev = map_pt(*pts[0])
        for pt in pts[1:]:
            cur = map_pt(*pt)
            pygame.draw.line(self.pantalla, (30, 120, 200), prev, cur, 2)
            prev = cur

    def mostrar_mensaje(self):
        """Muestra mensajes de estado"""
        rect_mensaje = pygame.Rect(20, 670, 960, 25)
        pygame.draw.rect(self.pantalla, self.color_mensaje, rect_mensaje)
        pygame.draw.rect(self.pantalla, NEGRO, rect_mensaje, 2)
        
        texto_surface = self.fuente_pequeña.render(self.mensaje, True, BLANCO)
        texto_rect = texto_surface.get_rect(center=rect_mensaje.center)
        self.pantalla.blit(texto_surface, texto_rect)

    def ejecutar(self):
        """Bucle principal de las gráficas musculares"""
        clock = pygame.time.Clock()
        ejecutando = True
        
        while ejecutando:
            tiempo_actual = pygame.time.get_ticks()
            
            # Procesar eventos
            for evento in pygame.event.get():
                if evento.type == pygame.QUIT:
                    raise CerrarPrograma("Usuario cerró ventana rutinas")
                elif evento.type == pygame.VIDEORESIZE and not self.fullscreen:
                    # Ajustar superficie en modo ventana
                    self.pantalla = pygame.display.set_mode((evento.w, evento.h), pygame.RESIZABLE)
                    self.ancho, self.alto = evento.w, evento.h
                    # Reposicionar botones al cambiar tamaño de ventana
                    self.crear_botones()
                    # Regenerar gráfica con el nuevo tamaño
                    self.generar_graficas()
                
                elif evento.type == pygame.MOUSEMOTION:
                    # Verificar hover en botones
                    self.boton_progreso.verificar_hover(evento.pos)
                    self.boton_comparacion.verificar_hover(evento.pos)
                    self.boton_sesion.verificar_hover(evento.pos)
                    self.boton_volver.verificar_hover(evento.pos)
                
                elif evento.type == pygame.MOUSEBUTTONDOWN:
                    # Verificar clics en botones
                    if self.boton_progreso.verificar_clic(evento.pos):
                        self.tipo_grafica = "progreso"
                        self.generar_graficas()
                        self.mensaje = "Mostrando gráfica de progreso general"
                        self.color_mensaje = VERDE
                        self.mostrar_mensaje_tiempo = tiempo_actual + 2000
                    
                    elif self.boton_comparacion.verificar_clic(evento.pos):
                        self.tipo_grafica = "comparacion"
                        self.generar_graficas()
                        self.mensaje = "Mostrando gráfica de comparación"
                        self.color_mensaje = VERDE
                        self.mostrar_mensaje_tiempo = tiempo_actual + 2000
                    
                    elif self.boton_sesion.verificar_clic(evento.pos):
                        self.tipo_grafica = "sesion"
                        self.generar_graficas()
                        self.mensaje = "Mostrando gráfica de la última sesión"
                        self.color_mensaje = VERDE
                        self.mostrar_mensaje_tiempo = tiempo_actual + 2000
                    
                    elif self.boton_volver.verificar_clic(evento.pos):
                        ejecutando = False
                elif evento.type == pygame.KEYDOWN:
                    if evento.key == pygame.K_F11:
                        self.fullscreen = not self.fullscreen
                        if self.fullscreen:
                            self.pantalla = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                            info = pygame.display.Info()
                            self.ancho, self.alto = info.current_w, info.current_h
                            # Reposicionar botones al cambiar a fullscreen
                            self.crear_botones()
                            # Regenerar gráfica con el nuevo tamaño
                            self.generar_graficas()
                        else:
                            # Salir a un tamaño base y permitir redimensionar
                            w, h = 1200, 700
                            self.pantalla = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                            self.ancho, self.alto = w, h
                            # Reposicionar botones al salir de fullscreen
                            self.crear_botones()
                            # Regenerar gráfica con el nuevo tamaño
                            self.generar_graficas()
            
            # Limpiar pantalla
            self.pantalla.fill(VERDE_CLARO)
            
            # Dibujar interfaz
            self.dibujar_interfaz()
            
            # Mostrar mensaje si es necesario
            if tiempo_actual < self.mostrar_mensaje_tiempo:
                self.mostrar_mensaje()
            
            # Barra inferior permanente (sin conexión directa aquí)
            dibujar_barra_inferior(self.pantalla, self.ancho, self.alto, False, "CNC no conectada")

            # Actualizar pantalla
            pygame.display.flip()
            
            # Controlar FPS
            clock.tick(60)
        
        # Limpiar recursos al cerrar la ventana de gráficas
        try:
            # Cerrar todas las figuras de matplotlib si existen
            if _try_import_matplotlib():
                plt.close('all')
        except Exception as e:
            print(f"[DEBUG] Error al cerrar figuras matplotlib: {e}")

def main():
    """Función principal del programa"""
    try:
        # Inicializar pygame
        pygame.init()
        
        # Ya no se usa GPIO - Arduino ECG se inicializa automáticamente en la ventana de gráficas
        
        # Mostrar mensaje de bienvenida
        print("=" * 60)
        print("    SISTEMA DE CONTROL CNC CON GESTIÓN DE PACIENTES")
        print("=" * 60)
        print("Versión: 3.1 - Con integración Arduino para sensores ECG")
        print("Características:")
        print("- Gestión completa de pacientes")
        print("- Control de CNC con diseño exacto de interfas1.py")
        print("- Rutinas de rehabilitación configurables")
        print("- Gráficas de progreso cardíaco con sensores ECG reales")
        print("- Lectura de datos ECG mediante Arduino Nano")
        print("- Interfaz adaptable y redimensionable")
        print("=" * 60)
        
        # Crear y ejecutar la ventana principal
        ventana_principal = VentanaPrincipal()
        resultado = ventana_principal.ejecutar()
        # Si la ventana se cerró con X o se salió normalmente, cerrar programa
        pygame.quit()
        sys.exit(0)
        
    except CerrarPrograma:
        print("\\nPrograma cerrado por el usuario")
        pygame.quit()
        sys.exit(0)
    except KeyboardInterrupt:
        print("\nPrograma interrumpido por el usuario")
    except Exception as e:
        print(f"Error inesperado: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Limpiar recursos
        try:
            pygame.quit()
        except:
            pass
        print("Programa finalizado correctamente")

if __name__ == "__main__":
    main()

    