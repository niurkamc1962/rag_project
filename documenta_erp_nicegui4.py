import os
import json
import asyncio
import webbrowser
from nicegui import ui, run
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings

# --- 1. CONFIGURACIÓN INICIAL ---
# Definimos el modelo de Ollama que usaremos y el tiempo de espera (timeout)
MODELO_LLM = "llama3.2-1b-instruct-q4km:latest"
Settings.llm = Ollama(model=MODELO_LLM, request_timeout=600.0)

# Rutas para guardar los manuales (.md) y la sesión (.json)
OUTPUT_DIR = os.path.abspath("./data/manuales_md")
SESSION_FILE = os.path.abspath("./data/sesion_ia.json")

# Creamos la carpeta de salida si no existe para evitar errores de escritura
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)


# --- 2. GESTIÓN DEL ESTADO (MEMORIA DEL PROGRAMA) ---
class AppState:
    def __init__(self):
        self.seleccionados = set()  # Archivos marcados actualmente en la lista
        self.checkboxes = []  # Referencias a los objetos checkbox de la interfaz
        self.memoria_contexto = {}  # El "cerebro": {nombre_archivo: contenido_texto}

    def guardar_a_disco(self):
        """Convierte la memoria de la IA en un archivo JSON para persistencia."""
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(self.memoria_contexto, f, ensure_ascii=False, indent=4)

    def cargar_de_disco(self):
        """Lee el archivo JSON y lo sube a la memoria RAM del programa."""
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                self.memoria_contexto = json.load(f)
            return True
        return False


# Instanciamos el estado global
state = AppState()


# --- 3. INTERFAZ DE USUARIO (NICEGUI) ---
@ui.page("/")
def main_page():
    # Estética: Color Indigo para un look profesional
    ui.colors(primary="#3949ab", secondary="#eeeeee")

    with ui.column().classes("w-full max-w-5xl mx-auto p-8 gap-4"):
        ui.label("🧠 ERPNext: Documentador & Consultor Persistente").classes(
            "text-3xl font-extrabold text-indigo-900"
        )

        # --- SECCIÓN A: SELECCIÓN DE ARCHIVOS ---
        with ui.expansion("1. Gestión de Archivos Fuente", icon="folder_zip").classes(
            "w-full border rounded-lg shadow-sm"
        ) as exp:
            with ui.column().classes("p-4 w-full gap-4"):
                with ui.row().classes("w-full items-center gap-4"):
                    input_ruta = ui.input(
                        label="Ruta local del proyecto",
                        placeholder="/home/niurka/erpnext...",
                    ).classes("flex-grow")
                    ui.button(
                        "Escanear",
                        icon="refresh",
                        on_click=lambda: cargar_lista_archivos(),
                    )

                # Contenedor donde aparecerán los checkboxes de los archivos
                container_archivos = ui.column().classes(
                    "w-full gap-1 p-2 border rounded bg-slate-50 max-h-48 overflow-auto"
                )

                def cargar_lista_archivos():
                    """Escanea la carpeta del usuario y dibuja los checkboxes en pantalla."""
                    ruta = input_ruta.value.strip()
                    if not os.path.exists(ruta):
                        ui.notify("La ruta no existe", type="negative")
                        return
                    container_archivos.clear()
                    state.seleccionados.clear()
                    state.checkboxes.clear()
                    try:
                        # Filtramos solo archivos de interés (Python, JSON, Markdown)
                        items = sorted(
                            os.scandir(ruta),
                            key=lambda e: (not e.is_dir(), e.name.lower()),
                        )
                        with container_archivos:
                            for entry in items:
                                if not entry.is_dir() and entry.name.endswith(
                                    (".json", ".py", ".md")
                                ):
                                    # Al cambiar el checkbox, se añade o quita de la lista de 'seleccionados'
                                    cb = ui.checkbox(
                                        text=entry.name,
                                        on_change=lambda e, p=entry.path: (
                                            state.seleccionados.add(p)
                                            if e.value
                                            else state.seleccionados.discard(p)
                                        ),
                                    )
                                    state.checkboxes.append(cb)
                    except Exception as e:
                        ui.notify(f"Error al leer: {e}")

                ui.button(
                    "PROCESAR Y GUARDAR SESIÓN",
                    icon="save",
                    on_click=lambda: procesar_lote(),
                ).classes("w-full bg-indigo-600 text-white py-3 shadow-md")

        # --- SECCIÓN B: ESTADO DE LA MEMORIA ---
        with ui.row().classes(
            "w-full items-center justify-between bg-slate-100 p-2 rounded text-xs"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("database", color="indigo")
                lbl_status = ui.label("Memoria vacía.")
            # Botón para recuperar la sesión guardada previamente en el JSON
            ui.button(
                "Cargar Sesión Anterior", on_click=lambda: recuperar_sesion()
            ).props("flat size=sm")
        # --- SECCIÓN C: CHAT DE CONSULTORÍA ---
        chat_card = ui.card().classes(
            "w-full p-0 shadow-xl border-0 overflow-hidden rounded-xl mt-4"
        )
        with chat_card:
            # Encabezado del chat
            with ui.row().classes(
                "w-full bg-indigo-800 p-4 text-white items-center justify-between"
            ):
                ui.label("💬 Consultas sobre el Proyecto").classes("font-bold text-lg")
                ui.button(
                    icon="delete_sweep", on_click=lambda: chat_logs.clear()
                ).props("flat color=white")

            # Área donde se imprimen los globos de texto
            chat_logs = ui.column().classes("w-full h-96 overflow-auto p-6 bg-white")

            # Campo de entrada de texto
            with ui.row().classes("w-full p-4 bg-gray-50 border-t items-center gap-2"):
                pregunta_input = (
                    ui.input(placeholder="Pregunta algo sobre el código procesado...")
                    .classes("flex-grow")
                    .on("keydown.enter", lambda: enviar_pregunta())
                )
                ui.button(icon="send", on_click=lambda: enviar_pregunta()).classes(
                    "bg-indigo-600 rounded-full text-white"
                )

        # --- 4. LÓGICA DE PROCESAMIENTO ---

        async def procesar_lote():
            """Lee los archivos, genera manuales y los guarda en el JSON de sesión."""
            if not state.seleccionados:
                ui.notify("Selecciona archivos primero", type="warning")
                return

            with ui.dialog() as diag, ui.card().classes("p-6 items-center"):
                ui.label("IA trabajando...").classes("font-bold")
                p_bar = ui.linear_progress(value=0).classes("w-64 mt-2")
            diag.open()

            for i, ruta in enumerate(list(state.seleccionados)):
                nombre = os.path.basename(ruta)
                try:
                    with open(ruta, "r", encoding="utf-8") as f:
                        contenido = f.read()

                    # 1. Guardamos en la memoria RAM del objeto state
                    state.memoria_contexto[nombre] = contenido

                    # 2. Generamos el manual físico (.md) por si quieres leerlo fuera
                    prompt = f"Analiza este archivo de ERPNext y crea un manual técnico: {contenido}"
                    resp = await run.io_bound(Settings.llm.complete, prompt)
                    with open(os.path.join(OUTPUT_DIR, nombre + ".md"), "w") as f_md:
                        f_md.write(resp.text)
                except Exception as e:
                    ui.notify(f"Error en {nombre}: {e}")
                p_bar.value = (i + 1) / len(state.seleccionados)

            # 3. Persistencia: Guardamos todo el diccionario en el archivo JSON
            state.guardar_a_disco()
            diag.close()
            lbl_status.set_text(
                f"Memoria activa: {len(state.memoria_contexto)} archivos cargados."
            )
            ui.notify("Archivos procesados y sesión guardada.", type="positive")

        def recuperar_sesion():
            """Función para cargar el JSON sin tener que volver a procesar archivos."""
            if state.cargar_de_disco():
                lbl_status.set_text(
                    f"Sesión recuperada: {len(state.memoria_contexto)} archivos en memoria."
                )
                ui.notify("¡Sesión cargada exitosamente!", type="positive")
            else:
                ui.notify("No se encontró sesión guardada.", type="warning")

        async def enviar_pregunta():
            """Envía el contexto guardado + la pregunta del usuario a la IA."""
            msg = pregunta_input.value.strip()
            if not msg or not state.memoria_contexto:
                ui.notify("Escribe algo o carga archivos primero.")
                return

            # Dibujamos mensaje del usuario
            with chat_logs:
                ui.chat_message(msg, sent=True, name="Tú").classes("text-sm")
                wait = ui.spinner(size="md")

            pregunta_input.value = ""  # Limpiamos el input

            # Preparamos el contexto: Unimos todos los archivos cargados en un solo string
            # Esto es lo que permite que la IA "sepa" de qué hablas.
            contexto = "\n".join(
                [f"ARCHIVO {n}:\n{c}" for n, c in state.memoria_contexto.items()]
            )
            full_prompt = f"Contexto técnico:\n{contexto}\n\nPregunta: {msg}\nRespuesta corta y técnica:"

            try:
                # Ejecutamos la llamada a Ollama en un hilo separado para no congelar la UI
                respuesta = await run.io_bound(Settings.llm.complete, full_prompt)
                chat_logs.remove(wait)
                with chat_logs:
                    ui.chat_message(respuesta.text, name="IA DocBot").classes(
                        "bg-indigo-50 text-sm"
                    )
            except Exception as e:
                ui.notify(f"Error: {e}")

            chat_logs.run_method("scrollTo", 0, 99999)


# Arrancamos la aplicación
ui.run(title="ERPNext AI Consultant", port=8080)
