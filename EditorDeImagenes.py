"""
LÚMINA STUDIO — Editor de imágenes
Proyecto educativo para Programación II.

PARA EJECUTAR EN THONNY:
1. En Thonny, abre Herramientas > Gestionar paquetes.
2. Busca Pillow e instálalo.
3. Abre este archivo y presiona F5 (o el botón Ejecutar).

ENVÍO POR CORREO (Gmail):
La contraseña de aplicación va enmascarada dentro de este mismo archivo
(constante CLAVE_APP_MASCARA). El programa no la pide al usuario.
"""
            
import winsound            
import os
import sys
import re
import io
import ssl
import base64
import smtplib
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from email.message import EmailMessage

try:
    from PIL import Image, ImageTk, ImageOps, ImageEnhance, ImageFilter, UnidentifiedImageError
except ModuleNotFoundError:
    # Mensaje claro si Pillow no está instalado en el intérprete que usa Thonny.
    _aviso = tk.Tk()
    _aviso.withdraw()
    messagebox.showerror(
        "Falta instalar Pillow",
        "Lúmina Studio necesita la biblioteca Pillow.\n\n"
        "En Thonny, entra en Herramientas > Gestionar paquetes, busca Pillow e instálala.\n"
        "Después vuelve a ejecutar este archivo con F5."
    )
    _aviso.destroy()
    raise SystemExit

# -------------------------- COLORES DEL DISEÑO --------------------------
FONDO = "#10121B"
PANEL = "#191C28"
ACENTO = "#8B5CF6"
TEXTO = "#F3F4F6"
SECUNDARIO = "#A6A9B8"
LIENZO = "#0C0E15"

# ----------------------- CONFIGURACIÓN DEL CORREO -----------------------
# Contraseña de aplicación de Gmail enmascarada (invertida y en Base64).
# No es cifrado: solo evita que se lea a simple vista en el código.
CLAVE_APP_MASCARA = "eGl4aGJienhkaWJoc3BnaQ=="

# -------------------------- RECURSOS Y RUTAS ----------------------------
def ruta_recurso(nombre_archivo):
    """Obtiene la ruta correcta del archivo tanto en .py como dentro de un .exe"""
    # 1. Si está empaquetado dentro de un .exe de PyInstaller
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, nombre_archivo)
    
    # 2. Si el archivo está al lado del .exe
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), nombre_archivo)
    
    # 3. Si se ejecuta como script normal en Thonny (.py)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), nombre_archivo)

# -------------------------- OPERACIONES DE IMAGEN -----------------------
def preparar(imagen):
    """Devuelve una copia en un modo compatible con las herramientas."""
    if imagen.mode not in ("RGB", "RGBA"):
        return imagen.convert("RGBA" if "A" in imagen.getbands() else "RGB")
    return imagen.copy()


def girar(imagen, grados):
    # expand=True evita que se corte la imagen al girarla.
    return imagen.rotate(grados, expand=True)


def voltear_horizontal(imagen):
    return ImageOps.mirror(imagen)


def voltear_vertical(imagen):
    return ImageOps.flip(imagen)


def grises(imagen):
    gris = ImageOps.grayscale(imagen)
    return gris.convert("RGB")


def blanco_negro(imagen, umbral=128):
    gris = ImageOps.grayscale(imagen)
    return gris.point(lambda pixel: 255 if pixel >= umbral else 0).convert("RGB")


def desenfoque(imagen):
    return imagen.filter(ImageFilter.GaussianBlur(radius=2))


def nitidez(imagen):
    return imagen.filter(ImageFilter.SHARPEN)


def bordes(imagen):
    return imagen.filter(ImageFilter.FIND_EDGES)


def negativo(imagen):
    if imagen.mode == "RGBA":
        rgb = imagen.convert("RGB")
        resultado = ImageOps.invert(rgb)
        resultado.putalpha(imagen.getchannel("A"))
        return resultado
    return ImageOps.invert(imagen.convert("RGB"))


def sepia(imagen):
    original = imagen.convert("RGB")
    gris = ImageOps.grayscale(original)
    sepia_img = ImageOps.colorize(gris, "#342313", "#F5D7A1")
    return sepia_img


def ajustes(imagen, brillo=1.0, contraste=1.0, saturacion=1.0):
    tiene_alpha = imagen.mode == "RGBA"
    alpha = imagen.getchannel("A") if tiene_alpha else None
    base = imagen.convert("RGB")
    base = ImageEnhance.Brightness(base).enhance(brillo)
    base = ImageEnhance.Contrast(base).enhance(contraste)
    base = ImageEnhance.Color(base).enhance(saturacion)
    if alpha is not None:
        base.putalpha(alpha)
    return base


def recortar(imagen, x1, y1, x2, y2):
    ancho, alto = imagen.size
    x1 = max(0, min(int(x1), ancho))
    x2 = max(0, min(int(x2), ancho))
    y1 = max(0, min(int(y1), alto))
    y2 = max(0, min(int(y2), alto))
    if x2 <= x1 or y2 <= y1:
        raise ValueError("Las coordenadas finales deben ser mayores que las iniciales.")
    return imagen.crop((x1, y1, x2, y2))


# ------------------------------- HISTORIAL ------------------------------
class Historial:
    """Guarda copias para deshacer y rehacer cambios."""
    def __init__(self):
        self.anteriores = []
        self.posteriores = []

    def guardar(self, imagen):
        self.anteriores.append(imagen.copy())
        self.posteriores.clear()

    def deshacer(self, actual):
        if not self.anteriores:
            return None
        self.posteriores.append(actual.copy())
        return self.anteriores.pop()

    def rehacer(self, actual):
        if not self.posteriores:
            return None
        self.anteriores.append(actual.copy())
        return self.posteriores.pop()


# ---------------------------- CORREO ELECTRÓNICO ------------------------
def correo_valido(direccion):
    patron = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return re.match(patron, direccion) is not None


def obtener_clave():
    """Desenmascara la contraseña de aplicación guardada en el código."""
    try:
        return base64.b64decode(CLAVE_APP_MASCARA).decode("utf-8")[::-1].strip()
    except (ValueError, UnicodeDecodeError):
        return ""


def imagen_para_adjunto(imagen, limite_mb=18):
    """Prepara un JPEG de tamaño prudente para adjuntar al correo."""
    base = imagen.convert("RGB")
    calidad = 90
    while True:
        memoria = io.BytesIO()
        base.save(memoria, format="JPEG", quality=calidad, optimize=True)
        datos = memoria.getvalue()
        if len(datos) <= limite_mb * 1024 * 1024:
            return datos, (calidad < 90)
        if calidad > 45:
            calidad -= 10
        else:
            ancho, alto = base.size
            if max(ancho, alto) <= 800:
                raise ValueError("La imagen sigue siendo demasiado grande para adjuntarla.")
            base.thumbnail((int(ancho * 0.8), int(alto * 0.8)), Image.Resampling.LANCZOS)
            calidad = 80


def enviar_correo(remitente, clave, destinatario, imagen, asunto, texto_mensaje):
    """Envía la imagen usando la cuenta de Gmail y una contraseña de aplicación."""
    servidor = os.getenv("LUMINA_SMTP", "smtp.gmail.com")
    puerto = int(os.getenv("LUMINA_PORT", "465"))
    remitente = remitente.strip()
    clave = clave.strip()

    if not remitente or not correo_valido(remitente):
        raise ValueError("Ingresá una dirección Gmail válida como remitente.")
    if not clave:
        raise ValueError("No se ingresó la contraseña de aplicación de Gmail.")

    datos, comprimida = imagen_para_adjunto(imagen)
    mensaje = EmailMessage()
    mensaje["Subject"] = asunto.strip() or "Imagen enviada desde Chio Studio"
    mensaje["From"] = remitente
    mensaje["To"] = destinatario
    mensaje.set_content(texto_mensaje.strip() or "Hola. Te envío una imagen editada con Chio Studio.")
    mensaje.add_attachment(
        datos, maintype="image", subtype="jpeg", filename="lumina_imagen.jpg"
    )

    contexto = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(servidor, puerto, context=contexto, timeout=25) as smtp:
            smtp.login(remitente, clave)
            smtp.send_message(mensaje)
    except smtplib.SMTPAuthenticationError:
        raise ValueError(
            "Gmail rechazó la contraseña. Usá una contraseña de aplicación de 16 "
            "caracteres (con la verificación en dos pasos activada), no la normal."
        )
    return comprimida


# ------------------------------ APLICACIÓN ------------------------------
class LuminaStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chio Studio — Editor de imágenes")
        self.geometry("1180x760")
        self.minsize(900, 620)
        self.configure(bg=FONDO)

        self.imagen = None
        self.ruta = None
        self.historial = Historial()
        self.foto_canvas = None
        self.seleccion_inicio = None
        self.rectangulo = None
        self.lineas_cuadricula = []
        self.recorte_activo = False
        self.seleccion_recorte = None
        self.modo_arrastre_recorte = None
        self.inicio_arrastre_recorte = None
        self.recorte_original_arrastre = None
        self.barra_recorte = None
        self.factor_vista = 1.0
        self.origen_vista = (0, 0)

        self._configurar_estilo()
        self._crear_menu()
        self._crear_interfaz()
        self._refrescar()

    def _configurar_estilo(self):
        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure("TFrame", background=FONDO)
        estilo.configure("TLabel", background=FONDO, foreground=TEXTO, font=("Segoe UI", 10))
        estilo.configure("TButton", background="#292D3D", foreground=TEXTO,
                         padding=(10, 7), font=("Segoe UI", 10))
        estilo.map("TButton", background=[("active", ACENTO)])
        estilo.configure("Accent.TButton", background=ACENTO, foreground="white")
        estilo.configure("TScale", background=PANEL)
        estilo.configure("TEntry", fieldbackground="#25293A", foreground=TEXTO)

    def _crear_menu(self):
        barra = tk.Menu(self, bg=PANEL, fg=TEXTO, activebackground=ACENTO)

        archivo = tk.Menu(barra, tearoff=False)
        archivo.add_command(label="Abrir imagen…", command=self.abrir, accelerator="Ctrl+O")
        archivo.add_command(label="Guardar como…", command=self.guardar, accelerator="Ctrl+S")
        archivo.add_separator()
        archivo.add_command(label="Enviar por correo…", command=self.dialogo_correo)
        archivo.add_separator()
        archivo.add_command(label="Salir", command=self.destroy)
        barra.add_cascade(label="Archivo", menu=archivo)

        editar = tk.Menu(barra, tearoff=False)
        editar.add_command(label="Deshacer", command=self.deshacer, accelerator="Ctrl+Z")
        editar.add_command(label="Rehacer", command=self.rehacer, accelerator="Ctrl+Y")
        editar.add_separator()
        editar.add_command(label="Recortar con el mouse", command=self.activar_recorte_mouse)
        barra.add_cascade(label="Editar", menu=editar)

        imagen = tk.Menu(barra, tearoff=False)
        imagen.add_command(label="Girar 90° a la izquierda",
                           command=lambda: self.previsualizar("Girar 90° a la izquierda", lambda im: girar(im, 90)))
        imagen.add_command(label="Girar 90° a la derecha",
                           command=lambda: self.previsualizar("Girar 90° a la derecha", lambda im: girar(im, -90)))
        imagen.add_command(label="Girar 180°",
                           command=lambda: self.previsualizar("Girar 180°", lambda im: girar(im, 180)))
        imagen.add_separator()
        imagen.add_command(label="Voltear horizontalmente",
                           command=lambda: self.previsualizar("Voltear horizontal", voltear_horizontal))
        imagen.add_command(label="Voltear verticalmente",
                           command=lambda: self.previsualizar("Voltear vertical", voltear_vertical))
        imagen.add_command(label="Escala de grises",
                           command=lambda: self.previsualizar("Escala de grises", grises))
        imagen.add_command(label="Blanco y negro · ajustar con slider…", command=self.dialogo_umbral)
        barra.add_cascade(label="Imagen", menu=imagen)

        filtros = tk.Menu(barra, tearoff=False)
        for nombre, funcion in [
            ("Desenfoque", desenfoque), ("Nitidez", nitidez),
            ("Bordes", bordes), ("Negativo", negativo), ("Sepia", sepia)
        ]:
            filtros.add_command(label=nombre,
                                command=lambda n=nombre, f=funcion: self.previsualizar(n, f))
        barra.add_cascade(label="Filtros", menu=filtros)

        ayuda = tk.Menu(barra, tearoff=False)
        ayuda.add_command(label="Acerca de Chio Studio",
                          command=lambda: messagebox.showinfo(
                              "Chio Studio",
                              "Editor de imágenes desarrollado en Python, Tkinter y Pillow.\nProyecto educativo de Programación II."
                          ))
        ayuda.add_command(label="Consejos de uso",
                          command=lambda: messagebox.showinfo(
                              "Consejos",
                              "Abrí una imagen y elegí una herramienta. La vista previa permite confirmar o cancelar el cambio.\nGuardá una copia con Archivo > Guardar como."
                          ))
        barra.add_cascade(label="Ayuda", menu=ayuda)
        self.config(menu=barra)

        self.bind("<Control-o>", lambda _e: self.abrir())
        self.bind("<Control-s>", lambda _e: self.guardar())
        self.bind("<Control-z>", lambda _e: self.deshacer())
        self.bind("<Control-y>", lambda _e: self.rehacer())

    def _crear_interfaz(self):
        cabecera = tk.Frame(self, bg=FONDO, padx=22, pady=15)
        cabecera.pack(fill="x")
        tk.Label(cabecera, text="◈  CHIO STUDIO", bg=FONDO, fg=TEXTO,
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(cabecera, text="EDITOR CREATIVO", bg=FONDO, fg="#A78BFA",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=15, pady=(5, 0))
        self.estado = tk.StringVar(value="Abrí una imagen para comenzar")
        tk.Label(cabecera, textvariable=self.estado, bg=FONDO, fg=SECUNDARIO,
                 font=("Segoe UI", 9)).pack(side="right")

        cuerpo = tk.Frame(self, bg=FONDO, padx=18, pady=5)
        cuerpo.pack(fill="both", expand=True)

        lateral = tk.Frame(cuerpo, bg=PANEL, width=250, padx=15, pady=15)
        lateral.pack(side="left", fill="y", padx=(0, 14))
        lateral.pack_propagate(False)
        tk.Label(lateral, text="HERRAMIENTAS", bg=PANEL, fg=TEXTO,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 12))

        for texto, comando in [
            ("＋  Abrir imagen", self.abrir),
            ("↶  Deshacer", self.deshacer),
            ("↷  Rehacer", self.rehacer),
            ("✂  Recortar", self.activar_recorte_mouse),
            ("◐  Blanco y negro · ajustar", self.dialogo_umbral),
        ]:
            ttk.Button(lateral, text=texto, command=comando).pack(fill="x", pady=4)

        ttk.Separator(lateral).pack(fill="x", pady=13)
        tk.Label(lateral, text="AJUSTES DE COLOR", bg=PANEL, fg=TEXTO,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")

        self.controles = {}
        for clave, nombre in [
            ("brillo", "Brillo"), ("contraste", "Contraste"), ("saturacion", "Saturación")
        ]:
            tk.Label(lateral, text=nombre, bg=PANEL, fg=SECUNDARIO,
                     font=("Segoe UI", 9)).pack(anchor="w", pady=(9, 1))
            variable = tk.DoubleVar(value=1.0)
            self.controles[clave] = variable
            ttk.Scale(lateral, from_=0, to=2, variable=variable,
                      command=lambda _v: self._actualizar_valores()).pack(fill="x")

        self.valores = tk.Label(lateral, text="1.00 · 1.00 · 1.00", bg=PANEL,
                                fg="#C4B5FD", font=("Consolas", 9))
        self.valores.pack(anchor="w", pady=(4, 8))
        ttk.Button(lateral, text="Vista previa de ajustes", command=self.previsualizar_ajustes,
                   style="Accent.TButton").pack(fill="x", pady=(4, 8))
        ttk.Button(lateral, text="Restablecer controles",
                   command=self.restablecer_controles).pack(fill="x")

        zona = tk.Frame(cuerpo, bg=LIENZO, padx=12, pady=12)
        zona.pack(side="left", fill="both", expand=True)
        tk.Label(zona, text="LIENZO", bg=LIENZO, fg=SECUNDARIO,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 8))
        self.canvas = tk.Canvas(zona, bg="#141722", highlightthickness=1,
                                highlightbackground="#303448", cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._refrescar())
        self.canvas.bind("<ButtonPress-1>", self._inicio_seleccion)
        self.canvas.bind("<B1-Motion>", self._mover_seleccion)
        self.canvas.bind("<ButtonRelease-1>", self._fin_seleccion)

        # Estos controles solo aparecen mientras se está recortando.
        self.barra_recorte = tk.Frame(zona, bg=LIENZO, pady=8)
        tk.Label(self.barra_recorte, text="Arrastrá para elegir el área y pulsá Listo para recortar.",
                 bg=LIENZO, fg=SECUNDARIO).pack(side="left", padx=(0, 12))
        ttk.Button(self.barra_recorte, text="Cancelar", command=self.cancelar_recorte).pack(side="right", padx=(8, 0))
        ttk.Button(self.barra_recorte, text="Listo", command=self.confirmar_recorte,
                   style="Accent.TButton").pack(side="right")

        pie = tk.Frame(self, bg=FONDO, padx=22, pady=12)
        pie.pack(fill="x")
        ttk.Button(pie, text="Guardar como…", command=self.guardar).pack(side="left")
        ttk.Button(pie, text="Enviar por correo", command=self.dialogo_correo).pack(side="left", padx=8)
        ttk.Button(pie, text="Comparar / aplicar filtros", command=self.dialogo_filtros).pack(side="left")
        self.dimensiones = tk.Label(pie, text="", bg=FONDO, fg=SECUNDARIO,
                                    font=("Segoe UI", 9))
        self.dimensiones.pack(side="right")

    def _actualizar_valores(self):
        valores = [self.controles[k].get() for k in ("brillo", "contraste", "saturacion")]
        self.valores.config(text=" · ".join(f"{v:.2f}" for v in valores))

    def restablecer_controles(self):
        for variable in self.controles.values():
            variable.set(1.0)
        self._actualizar_valores()

    def _necesita_imagen(self):
        if self.imagen is None:
            messagebox.showwarning("No hay imagen", "Primero abrí una imagen desde Archivo > Abrir.")
            return False
        return True

    def abrir(self):
        ruta = filedialog.askopenfilename(
            title="Abrir imagen",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff"),
                       ("Todos los archivos", "*.*")]
        )
        if not ruta:
            return
        try:
            with Image.open(ruta) as archivo:
                archivo.verify()
            with Image.open(ruta) as archivo:
                cargada = ImageOps.exif_transpose(archivo)
                cargada = preparar(cargada)
            self.imagen = cargada
            self.ruta = ruta
            self.historial = Historial()
            self._refrescar()
            self.estado.set("Abierta: " + os.path.basename(ruta))
        except (OSError, ValueError, UnidentifiedImageError) as error:
            messagebox.showerror("No se pudo abrir", f"El archivo no parece una imagen válida.\n\n{error}")

    def guardar(self):
        if not self._necesita_imagen():
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar imagen como", defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("BMP", "*.bmp"), ("TIFF", "*.tiff")]
        )
        if not ruta:
            return
        try:
            copia = self.imagen.copy()
            extension = os.path.splitext(ruta)[1].lower()
            if extension in (".jpg", ".jpeg") and copia.mode in ("RGBA", "LA"):
                fondo = Image.new("RGB", copia.size, "white")
                fondo.paste(copia, mask=copia.getchannel("A"))
                copia = fondo
            elif extension in (".jpg", ".jpeg", ".bmp") and copia.mode not in ("RGB", "L"):
                copia = copia.convert("RGB")
            copia.save(ruta)
            self.estado.set("Guardada: " + os.path.basename(ruta))
            messagebox.showinfo("Imagen guardada", "La imagen se guardó correctamente.")
        except (OSError, ValueError) as error:
            messagebox.showerror("Error al guardar", f"No se pudo guardar la imagen.\n\n{error}")

    def previsualizar(self, titulo, operacion):
        if not self._necesita_imagen():
            return
        try:
            candidata = operacion(self.imagen.copy())
            self._dialogo_previo(titulo, candidata)
        except Exception as error:
            messagebox.showerror("Error de edición", f"No se pudo preparar la vista previa.\n\n{error}")

    def _dialogo_previo(self, titulo, candidata):
        ventana = tk.Toplevel(self)
        ventana.title("Vista previa — " + titulo)
        ventana.configure(bg=FONDO)
        ventana.geometry("900x570")
        ventana.transient(self)
        tk.Label(ventana, text=titulo.upper(), bg=FONDO, fg=TEXTO,
                 font=("Segoe UI", 13, "bold")).pack(pady=12)

        comparacion = tk.Frame(ventana, bg=FONDO, padx=12)
        comparacion.pack(fill="both", expand=True)
        antes = tk.Label(comparacion, text="ANTES", bg=PANEL, fg=SECUNDARIO,
                         compound="top", padx=6, pady=6)
        despues = tk.Label(comparacion, text="DESPUÉS", bg=PANEL, fg="#C4B5FD",
                           compound="top", padx=6, pady=6)
        antes.pack(side="left", fill="both", expand=True, padx=5)
        despues.pack(side="left", fill="both", expand=True, padx=5)
        ventana.update_idletasks()
        self._poner_previa(antes, self.imagen, 410, 390)
        self._poner_previa(despues, candidata, 410, 390)

        botones = tk.Frame(ventana, bg=FONDO, pady=12)
        botones.pack()
        ttk.Button(botones, text="Cancelar", command=ventana.destroy).pack(side="left", padx=7)

        def confirmar():
            self.historial.guardar(self.imagen)
            self.imagen = candidata.copy()
            self._refrescar()
            self.estado.set("Aplicado: " + titulo)
            self._sonido()
            ventana.destroy()

        ttk.Button(botones, text="Confirmar cambio", command=confirmar,
                   style="Accent.TButton").pack(side="left", padx=7)

    def _poner_previa(self, etiqueta, imagen, ancho, alto):
        vista = imagen.copy()
        vista.thumbnail((ancho, alto), Image.Resampling.LANCZOS)
        foto = ImageTk.PhotoImage(vista)
        etiqueta.configure(image=foto)
        etiqueta.image = foto

    def _refrescar(self):
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        if self.imagen is None:
            self.canvas.create_text(
                max(100, self.canvas.winfo_width() // 2),
                max(80, self.canvas.winfo_height() // 2),
                text="CHIO STUDIO\n\nAbrí una imagen para empezar a editar",
                fill="#777D94", font=("Segoe UI", 16), justify="center"
            )
            if hasattr(self, "dimensiones"):
                self.dimensiones.config(text="")
            return

        ancho_canvas = max(1, self.canvas.winfo_width() - 30)
        alto_canvas = max(1, self.canvas.winfo_height() - 30)
        vista = self.imagen.copy()
        vista.thumbnail((ancho_canvas, alto_canvas), Image.Resampling.LANCZOS)
        self.factor_vista = vista.width / self.imagen.width
        self.foto_canvas = ImageTk.PhotoImage(vista)
        centro_x = self.canvas.winfo_width() // 2
        centro_y = self.canvas.winfo_height() // 2
        self.origen_vista = (centro_x - vista.width // 2, centro_y - vista.height // 2)
        self.canvas.create_image(centro_x, centro_y, image=self.foto_canvas, anchor="center")
        if self.recorte_activo and self.seleccion_recorte:
            x1, y1, x2, y2 = self.seleccion_recorte
            self._dibujar_cuadricula_recorte(
                self.origen_vista[0] + x1 * self.factor_vista,
                self.origen_vista[1] + y1 * self.factor_vista,
                self.origen_vista[0] + x2 * self.factor_vista,
                self.origen_vista[1] + y2 * self.factor_vista
            )
        if hasattr(self, "dimensiones"):
            self.dimensiones.config(text=f"{self.imagen.width} × {self.imagen.height} px")

    def _sonido(self):
        """Reproduce wow.wav (o wow.mp3) de forma asíncrona sin trabar la interfaz."""
        try:
            ruta_wav = ruta_recurso("WowAnime.wav")
            ruta_mp3 = ruta_recurso("WowAnime.mp3")

            if os.path.exists(ruta_wav):
                winsound.PlaySound(ruta_wav, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif os.path.exists(ruta_mp3):
                alias = "sonido_lumina"
                ctypes.windll.winmm.mciSendStringW(f'close {alias}', None, 0, None)
                ctypes.windll.winmm.mciSendStringW(f'open "{ruta_mp3}" type mpegvideo alias {alias}', None, 0, None)
                ctypes.windll.winmm.mciSendStringW(f'play {alias} from 0', None, 0, None)
            else:
                self.bell()
        except Exception:
            try:
                self.bell()
            except tk.TclError:
                pass

    def deshacer(self):
        if not self._necesita_imagen():
            return
        anterior = self.historial.deshacer(self.imagen)
        if anterior is None:
            messagebox.showinfo("Historial", "No hay más cambios para deshacer.")
            return
        self.imagen = anterior
        self._refrescar()
        self.estado.set("Cambio deshecho")
        self._sonido()

    def rehacer(self):
        if not self._necesita_imagen():
            return
        siguiente = self.historial.rehacer(self.imagen)
        if siguiente is None:
            messagebox.showinfo("Historial", "No hay cambios para rehacer.")
            return
        self.imagen = siguiente
        self._refrescar()
        self.estado.set("Cambio rehecho")
        self._sonido()

    def dialogo_umbral(self):
        """Permite ajustar el umbral de blanco y negro con un slider."""
        if not self._necesita_imagen():
            return

        ventana = tk.Toplevel(self)
        ventana.title("Blanco y negro")
        ventana.configure(bg=FONDO)
        ventana.transient(self)
        ventana.resizable(False, False)
        ventana.grab_set()

        tk.Label(
            ventana, text="AJUSTAR BLANCO Y NEGRO", bg=FONDO, fg=TEXTO,
            font=("Segoe UI", 12, "bold")
        ).pack(padx=24, pady=(18, 8))
        tk.Label(
            ventana,
            text="Mové el control para cambiar qué tonos se ven blancos o negros.",
            bg=FONDO, fg=SECUNDARIO, wraplength=340, justify="center"
        ).pack(padx=24, pady=(0, 12))

        valor = tk.IntVar(value=128)
        fila_valor = tk.Frame(ventana, bg=FONDO)
        fila_valor.pack(fill="x", padx=24)
        tk.Label(fila_valor, text="Umbral", bg=FONDO, fg=TEXTO).pack(side="left")
        etiqueta_valor = tk.Label(
            fila_valor, text="128", bg=FONDO, fg="#C4B5FD",
            font=("Segoe UI", 10, "bold")
        )
        etiqueta_valor.pack(side="right")

        def actualizar_valor(nuevo):
            etiqueta_valor.config(text=str(int(float(nuevo))))

        ttk.Scale(
            ventana, from_=0, to=255, orient="horizontal", variable=valor,
            command=actualizar_valor, length=320
        ).pack(padx=24, pady=(8, 4))
        tk.Label(
            ventana, text="Más negro  ←                 →  Más blanco",
            bg=FONDO, fg=SECUNDARIO, font=("Segoe UI", 8)
        ).pack(padx=24, pady=(0, 16))

        botones = tk.Frame(ventana, bg=FONDO)
        botones.pack(pady=(0, 18))
        ttk.Button(botones, text="Cancelar", command=ventana.destroy).pack(side="left", padx=6)

        def aplicar():
            umbral = int(valor.get())
            ventana.destroy()
            self.previsualizar(
                f"Blanco y negro · umbral {umbral}",
                lambda im: blanco_negro(im, umbral)
            )

        ttk.Button(
            botones, text="Ver vista previa", command=aplicar,
            style="Accent.TButton"
        ).pack(side="left", padx=6)

    def activar_recorte_mouse(self):
        if not self._necesita_imagen():
            return
        self.recorte_activo = True
        self.seleccion_inicio = None
        self.seleccion_recorte = None
        self.barra_recorte.pack(fill="x", pady=(4, 0))
        self.estado.set("Recorte activo: arrastrá sobre la imagen y luego pulsá Listo")
        for elemento in self.lineas_cuadricula:
            self.canvas.delete(elemento)
        self.lineas_cuadricula.clear()
        if self.rectangulo:
            self.canvas.delete(self.rectangulo)
            self.rectangulo = None

    def cancelar_recorte(self):
        self.recorte_activo = False
        self.seleccion_inicio = None
        self.seleccion_recorte = None
        self.modo_arrastre_recorte = None
        self.inicio_arrastre_recorte = None
        self.recorte_original_arrastre = None
        self.canvas.configure(cursor="crosshair")
        if self.barra_recorte and self.barra_recorte.winfo_manager():
            self.barra_recorte.pack_forget()
        self._refrescar()
        self.estado.set("Recorte cancelado")

    def confirmar_recorte(self):
        if not self.recorte_activo or not self.seleccion_recorte:
            messagebox.showinfo("Recorte", "Primero arrastrá sobre la imagen para elegir el área.")
            return
        x1, y1, x2, y2 = self.seleccion_recorte
        try:
            candidata = recortar(self.imagen, x1, y1, x2, y2)
        except ValueError as error:
            messagebox.showerror("Recorte inválido", str(error))
            return
        self.historial.guardar(self.imagen)
        self.imagen = candidata
        self.recorte_activo = False
        self.seleccion_inicio = None
        self.seleccion_recorte = None
        self.modo_arrastre_recorte = None
        self.inicio_arrastre_recorte = None
        self.recorte_original_arrastre = None
        self.canvas.configure(cursor="crosshair")
        if self.barra_recorte and self.barra_recorte.winfo_manager():
            self.barra_recorte.pack_forget()
        self._refrescar()
        self.estado.set("Recorte aplicado")
        self._sonido()

    def _limitar_a_imagen(self, x, y):
        """Mantiene un punto dentro de los bordes de la imagen mostrada."""
        ox, oy = self.origen_vista
        ancho = self.imagen.width * self.factor_vista
        alto = self.imagen.height * self.factor_vista
        x = max(ox, min(x, ox + ancho))
        y = max(oy, min(y, oy + alto))
        return x, y

    def _dibujar_cuadricula_recorte(self, x0, y0, x1, y1):
        """Dibuja el marco de recorte y la cuadrícula de tercios."""
        for elemento in self.lineas_cuadricula:
            self.canvas.delete(elemento)
        self.lineas_cuadricula.clear()

        izquierda, derecha = sorted((x0, x1))
        arriba, abajo = sorted((y0, y1))
        ancho = derecha - izquierda
        alto = abajo - arriba
        if ancho < 1 or alto < 1:
            return

        # Marco exterior, blanco para que se vea sobre imágenes claras u oscuras.
        self.rectangulo = self.canvas.create_rectangle(
            izquierda, arriba, derecha, abajo,
            outline="#FFFFFF", width=2
        )
        # Cuadrícula 3 x 3, como las guías de recorte habituales en apps móviles.
        for parte in (1 / 3, 2 / 3):
            x = izquierda + ancho * parte
            y = arriba + alto * parte
            self.lineas_cuadricula.append(self.canvas.create_line(
                x, arriba, x, abajo, fill="#FFFFFF", width=1, dash=(4, 3)
            ))
            self.lineas_cuadricula.append(self.canvas.create_line(
                izquierda, y, derecha, y, fill="#FFFFFF", width=1, dash=(4, 3)
            ))
        # Pequeños marcadores en las esquinas para destacar el área elegida.
        largo = min(14, ancho / 4, alto / 4)
        for xa, ya, dx, dy in (
            (izquierda, arriba, 1, 1), (derecha, arriba, -1, 1),
            (izquierda, abajo, 1, -1), (derecha, abajo, -1, -1)
        ):
            self.lineas_cuadricula.append(self.canvas.create_line(
                xa, ya, xa + dx * largo, ya, fill="#A78BFA", width=3
            ))
            self.lineas_cuadricula.append(self.canvas.create_line(
                xa, ya, xa, ya + dy * largo, fill="#A78BFA", width=3
            ))
        # Tiradores visibles en esquinas y centros de cada borde para redimensionar.
        centro_x = (izquierda + derecha) / 2
        centro_y = (arriba + abajo) / 2
        for hx, hy in ((izquierda, arriba), (centro_x, arriba), (derecha, arriba),
                       (izquierda, centro_y), (derecha, centro_y),
                       (izquierda, abajo), (centro_x, abajo), (derecha, abajo)):
            r = 4
            self.lineas_cuadricula.append(self.canvas.create_rectangle(
                hx-r, hy-r, hx+r, hy+r, fill="#A78BFA", outline="#FFFFFF", width=1
            ))

    def _coordenadas_canvas_a_imagen(self, x, y):
        """Convierte coordenadas del lienzo a coordenadas de la imagen original."""
        ox, oy = self.origen_vista
        factor = max(self.factor_vista, 0.0001)
        x = (x - ox) / factor
        y = (y - oy) / factor
        return (max(0, min(self.imagen.width, x)),
                max(0, min(self.imagen.height, y)))

    def _coordenadas_recorte_canvas(self):
        """Devuelve el recorte actual en coordenadas del lienzo."""
        x1, y1, x2, y2 = self.seleccion_recorte
        ox, oy = self.origen_vista
        f = self.factor_vista
        return (ox + x1 * f, oy + y1 * f, ox + x2 * f, oy + y2 * f)

    def _inicio_seleccion(self, evento):
        if self.imagen is None or not self.recorte_activo:
            return
        ox, oy = self.origen_vista
        ancho_vista = self.imagen.width * self.factor_vista
        alto_vista = self.imagen.height * self.factor_vista
        if not (ox <= evento.x <= ox + ancho_vista and oy <= evento.y <= oy + alto_vista):
            return

        # Si ya existe un recorte, permitir agarrar los bordes/esquinas para ajustarlo.
        if self.seleccion_recorte:
            izquierda, arriba, derecha, abajo = self._coordenadas_recorte_canvas()
            margen = 12
            cerca_izq = abs(evento.x - izquierda) <= margen
            cerca_der = abs(evento.x - derecha) <= margen
            cerca_arriba = abs(evento.y - arriba) <= margen
            cerca_abajo = abs(evento.y - abajo) <= margen
            dentro_x = izquierda <= evento.x <= derecha
            dentro_y = arriba <= evento.y <= abajo

            modo = None
            if cerca_izq and cerca_arriba: modo = "nw"
            elif cerca_der and cerca_arriba: modo = "ne"
            elif cerca_izq and cerca_abajo: modo = "sw"
            elif cerca_der and cerca_abajo: modo = "se"
            elif cerca_izq and dentro_y: modo = "w"
            elif cerca_der and dentro_y: modo = "e"
            elif cerca_arriba and dentro_x: modo = "n"
            elif cerca_abajo and dentro_x: modo = "s"
            elif dentro_x and dentro_y: modo = "mover"

            if modo:
                self.modo_arrastre_recorte = modo
                self.inicio_arrastre_recorte = self._coordenadas_canvas_a_imagen(evento.x, evento.y)
                self.recorte_original_arrastre = self.seleccion_recorte
                self.canvas.configure(cursor="fleur" if modo == "mover" else "sizing")
                return

        # Al pulsar fuera del marco actual se inicia una nueva selección.
        self.modo_arrastre_recorte = "nuevo"
        self.seleccion_inicio = self._limitar_a_imagen(evento.x, evento.y)
        self.seleccion_recorte = None
        self.inicio_arrastre_recorte = None
        self.recorte_original_arrastre = None
        for elemento in self.lineas_cuadricula:
            self.canvas.delete(elemento)
        self.lineas_cuadricula.clear()
        if self.rectangulo:
            self.canvas.delete(self.rectangulo)
            self.rectangulo = None
        self._dibujar_cuadricula_recorte(*self.seleccion_inicio, *self.seleccion_inicio)

    def _mover_seleccion(self, evento):
        if not self.recorte_activo or self.imagen is None:
            return
        if self.modo_arrastre_recorte in ("nw", "ne", "sw", "se", "n", "s", "e", "w", "mover") and self.recorte_original_arrastre:
            x, y = self._coordenadas_canvas_a_imagen(evento.x, evento.y)
            sx, sy = self.inicio_arrastre_recorte
            x1, y1, x2, y2 = self.recorte_original_arrastre
            dx, dy = x - sx, y - sy
            modo = self.modo_arrastre_recorte
            if modo == "mover":
                ancho, alto = x2 - x1, y2 - y1
                x1 = max(0, min(self.imagen.width - ancho, x1 + dx))
                y1 = max(0, min(self.imagen.height - alto, y1 + dy))
                x2, y2 = x1 + ancho, y1 + alto
            else:
                if "w" in modo: x1 = max(0, min(x2 - 1, x1 + dx))
                if "e" in modo: x2 = min(self.imagen.width, max(x1 + 1, x2 + dx))
                if "n" in modo: y1 = max(0, min(y2 - 1, y1 + dy))
                if "s" in modo: y2 = min(self.imagen.height, max(y1 + 1, y2 + dy))
            self.seleccion_recorte = (int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2)))
            self._refrescar()
            self.estado.set("Ajustá los bordes o mové el marco; pulsá Listo para recortar")
            return

        if self.modo_arrastre_recorte == "nuevo" and self.seleccion_inicio:
            x0, y0 = self.seleccion_inicio
            x1, y1 = self._limitar_a_imagen(evento.x, evento.y)
            self._refrescar()
            self._dibujar_cuadricula_recorte(x0, y0, x1, y1)

    def _fin_seleccion(self, evento):
        if not self.recorte_activo or self.imagen is None:
            return
        if self.modo_arrastre_recorte in ("nw", "ne", "sw", "se", "n", "s", "e", "w", "mover"):
            self.modo_arrastre_recorte = None
            self.inicio_arrastre_recorte = None
            self.recorte_original_arrastre = None
            self.canvas.configure(cursor="crosshair")
            self.estado.set("Recorte ajustado. Podés seguir moviendo los bordes o pulsar Listo")
            self._refrescar()
            return
        if self.modo_arrastre_recorte != "nuevo" or not self.seleccion_inicio:
            return
        x0, y0 = self.seleccion_inicio
        x_fin, y_fin = self._limitar_a_imagen(evento.x, evento.y)
        self.seleccion_inicio = None
        self.modo_arrastre_recorte = None
        ox, oy = self.origen_vista
        factor = max(self.factor_vista, 0.0001)
        x1 = round((min(x0, x_fin) - ox) / factor)
        y1 = round((min(y0, y_fin) - oy) / factor)
        x2 = round((max(x0, x_fin) - ox) / factor)
        y2 = round((max(y0, y_fin) - oy) / factor)
        try:
            recortar(self.imagen, x1, y1, x2, y2)
            self.seleccion_recorte = (x1, y1, x2, y2)
            self.estado.set("Recorte seleccionado. Arrastrá los bordes o pulsá Listo")
            self._refrescar()
        except ValueError:
            self.seleccion_recorte = None
            self.estado.set("Selección demasiado pequeña; intentá de nuevo")
            self._refrescar()

    def previsualizar_ajustes(self):
        if not self._necesita_imagen():
            return
        valores = [self.controles[k].get() for k in ("brillo", "contraste", "saturacion")]
        self.previsualizar("Ajustes de color", lambda im: ajustes(im, *valores))

    def dialogo_filtros(self):
        if not self._necesita_imagen():
            return
        ventana = tk.Toplevel(self)
        ventana.title("Filtros de Chio Studio")
        ventana.configure(bg=FONDO)
        tk.Label(ventana, text="Elegí un filtro para comparar antes de aplicarlo",
                 bg=FONDO, fg=TEXTO, font=("Segoe UI", 11, "bold")).pack(padx=20, pady=14)
        for nombre, funcion in [
            ("Desenfoque", desenfoque), ("Nitidez", nitidez), ("Bordes", bordes),
            ("Negativo", negativo), ("Sepia", sepia), ("Escala de grises", grises)
        ]:
            ttk.Button(
                ventana, text=nombre,
                command=lambda n=nombre, f=funcion: (
                    ventana.destroy(), self.previsualizar(n, f)
                )
            ).pack(fill="x", padx=20, pady=4)
        ttk.Button(ventana, text="Cerrar", command=ventana.destroy).pack(pady=12)

    def dialogo_correo(self):
        if not self._necesita_imagen():
            return

        ventana = tk.Toplevel(self)
        ventana.title("APLICACION DE MENSAJERIA")
        ventana.geometry("430x650")
        ventana.resizable(False, False)
        ventana.configure(bg="white", bd=10)
        ventana.transient(self)
        ventana.grab_set()

        tk.Label(
            ventana, text="ENVIAR CORREO VIA GMAIL", fg="black", bg="white",
            font=("Arial", 15, "bold"), padx=5, pady=5,
        ).pack(pady=(2, 8))

        remitente = os.getenv("LUMINA_EMAIL", "especialidad246@gmail.com").strip()
        tk.Label(
            ventana, text=f"Mi correo: {remitente}", fg="white", bg="blue",
            font=("Arial", 10, "bold"), padx=5, pady=5,
        ).pack(pady=5)

        opciones_emails = [
            "Seleccionar opción...",
            "fjcoronati@gmail.com",
            "mfedullo@gmail.com",
            "lafortaleza246@institucion.edu.ar",
        ]
        email_seleccionado = tk.StringVar(ventana, value=opciones_emails[0])
        destinatario_manual = tk.StringVar(ventana)

        fila_lista = tk.Frame(ventana, bg="white")
        fila_lista.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(fila_lista, text="Lista correos:", bg="white", font=("Arial", 10, "bold")).pack(side="left")
        tk.OptionMenu(fila_lista, email_seleccionado, *opciones_emails).pack(side="right")

        fila_manual = tk.Frame(ventana, bg="white")
        fila_manual.pack(fill="x", padx=8, pady=3)
        tk.Label(fila_manual, text="Destinatario:", bg="white", font=("Arial", 10, "bold")).pack(side="left")
        tk.Entry(fila_manual, textvariable=destinatario_manual, width=29).pack(side="right")

        tk.Label(ventana, text="Mensaje (la foto se adjuntará al correo):", bg="white", font=("Arial", 10, "bold")).pack(anchor="w", padx=8, pady=(8, 3))

        # Vista previa de la imagen que se adjuntará.
        marco_foto = tk.Frame(ventana, bg="#eeeeee", bd=1, relief="sunken", height=190)
        marco_foto.pack(fill="x", padx=8, pady=3)
        marco_foto.pack_propagate(False)
        try:
            vista = self.imagen.copy()
            vista.thumbnail((390, 180), Image.Resampling.LANCZOS)
            self._vista_correo = ImageTk.PhotoImage(vista)
            tk.Label(marco_foto, image=self._vista_correo, bg="#eeeeee").pack(expand=True)
        except Exception as error:
            tk.Label(marco_foto, text=f"No se pudo mostrar la vista previa: {error}", bg="#eeeeee", fg="red").pack(expand=True)

        mensaje = tk.Text(ventana, height=5, width=45, font=("Arial", 10), wrap="word")
        mensaje.pack(fill="both", expand=True, padx=8, pady=4)
        mensaje.insert("1.0", "Hola. Te envío una imagen editada con Lúmina Studio.")

        def enviar_email():
            opcion = email_seleccionado.get()
            manual = destinatario_manual.get().strip()
            destinatario_final = manual if manual else (opcion if opcion != "Seleccionar opción..." else "")
            if not destinatario_final:
                messagebox.showwarning("MENSAJERIA", "Seleccione un correo de la lista o ingrese uno manualmente.", parent=ventana)
                return
            if not correo_valido(destinatario_final):
                messagebox.showerror("ERROR", "Ingrese una dirección de correo válida.", parent=ventana)
                return
            if not correo_valido(remitente):
                messagebox.showerror("ERROR", "El correo remitente configurado no es válido.", parent=ventana)
                return

            # La clave sale enmascarada del propio código; no se pide al usuario.
            clave = obtener_clave()
            if not clave:
                return
            copia = self.imagen.copy()
            cuerpo_texto = mensaje.get("1.0", "end-1c")
            boton.config(state="disabled")
            self.estado.set("Enviando correo…")

            def tarea():
                try:
                    comprimida = enviar_correo(
                        remitente, clave, destinatario_final, copia,
                        "Imagen enviada desde Lúmina Studio", cuerpo_texto,
                    )
                    resultado = ("ok", comprimida, destinatario_final)
                except Exception as error:
                    resultado = ("error", str(error), destinatario_final)
                self.after(0, lambda: terminar(resultado))

            def terminar(resultado):
                boton.config(state="normal")
                if resultado[0] == "ok":
                    ventana.destroy()
                    self.estado.set("Correo enviado correctamente")
                    texto = f"Mensaje enviado correctamente a:\n{resultado[2]}"
                    if resultado[1]:
                        texto += "\nLa imagen se optimizó para adjuntarla."
                    messagebox.showinfo("MENSAJERIA", texto, parent=self)
                else:
                    self.estado.set("No se pudo enviar el correo")
                    messagebox.showerror("ERROR", f"No se pudo enviar el correo:\n{resultado[1]}", parent=ventana)

            threading.Thread(target=tarea, daemon=True).start()

        boton = tk.Button(
            ventana, text="ENVIAR", command=enviar_email, height=2, width=12,
            bg="black", fg="white", font=("Arial", 10, "bold"),
        )
        boton.pack(pady=8)


if __name__ == "__main__":
    app = LuminaStudio()
    app.mainloop()
