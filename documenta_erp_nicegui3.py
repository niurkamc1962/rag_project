import os
import asyncio
from nicegui import ui, run
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings

# --- CONFIGURACIÓN ---
MODELO_LLM = "llama3.2-1b-instruct-q4km:latest"
Settings.llm = Ollama(model=MODELO_LLM, request_timeout=600.0)
OUTPUT_DIR = os.path.abspath("./data/manuales_md")

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)


class AppState:
    def __init__(self):
        self.seleccionados = set()
        self.checkboxes = []
        # Esta es la base de conocimientos que persistirá
        self.memoria_contexto = {}


state = AppState()


@ui.page("/")
def main_page():
    ui.colors(primary="#3949ab", secondary="#eeeeee")

    with ui.column().classes("w-full max-w-5xl mx-auto p-8 gap-4"):
        ui.label("🧠 Consultor ERPNext Inteligente").classes(
            "text-3xl font-extrabold text-indigo-900"
        )

        # --- PANEL DE SELECCIÓN ---
        with ui.expansion(
            "1. Selección de Archivos Fuente", icon="folder_zip", value=True
        ).classes("w-full border rounded-lg shadow-sm"):
            with ui.column().classes("p-4 w-full gap-4"):
                with ui.row().classes("w-full items-center gap-4"):
                    input_ruta = ui.input(
                        label="Ruta local", placeholder="/home/niurka/..."
                    ).classes("flex-grow")
                    ui.button(
                        "Cargar Carpeta",
                        icon="refresh",
                        on_click=lambda: cargar_contenido(),
                    )

                container_archivos = ui.column().classes(
                    "w-full gap-1 p-2 border rounded bg-slate-50 max-h-48 overflow-auto"
                )

                def cargar_contenido():
                    ruta = input_ruta.value.strip()
                    if not os.path.exists(ruta):
                        ui.notify("Ruta no válida", type="negative")
                        return
                    container_archivos.clear()
                    state.seleccionados.clear()
                    state.checkboxes.clear()
                    try:
                        items = sorted(
                            os.scandir(ruta),
                            key=lambda e: (not e.is_dir(), e.name.lower()),
                        )
                        with container_archivos:
                            for entry in items:
                                if not entry.is_dir() and entry.name.endswith(
                                    (".json", ".py", ".md")
                                ):
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
                        ui.notify(f"Error: {e}")

                ui.button(
                    "GENERAR Y CARGAR EN MEMORIA",
                    icon="bolt",
                    on_click=lambda: procesar_lote(),
                ).classes("w-full bg-indigo-600 text-white py-3 shadow-md")

        # --- CONSOLA DE ESTADO ---
        with ui.row().classes("w-full items-center gap-2 text-xs text-gray-500"):
            ui.icon("memory")
            lbl_status_memoria = ui.label(
                "Memoria vacía. Procesa archivos para preguntar."
            )

        # --- SECCIÓN DE CHAT (PERMANENTE) ---
        chat_card = ui.card().classes(
            "w-full p-0 shadow-xl border-0 overflow-hidden rounded-xl"
        )
        with chat_card:
            with ui.row().classes(
                "w-full bg-indigo-800 p-4 text-white items-center justify-between"
            ):
                ui.label("💬 Chat de Consultoría Técnica").classes("font-bold text-lg")
                ui.button(
                    icon="delete_sweep", on_click=lambda: chat_logs.clear()
                ).props("flat color=white text-xs").classes("hover:bg-indigo-700")

            chat_logs = ui.column().classes("w-full h-80 overflow-auto p-6 bg-white")

            with ui.row().classes("w-full p-4 bg-gray-50 border-t items-center gap-2"):
                pregunta_input = (
                    ui.input(placeholder="Pregunta sobre los archivos procesados...")
                    .classes("flex-grow")
                    .on("keydown.enter", lambda: enviar_pregunta())
                )
                ui.button(icon="send", on_click=lambda: enviar_pregunta()).classes(
                    "bg-indigo-600 rounded-full w-12 h-12"
                )

        async def enviar_pregunta():
            msg = pregunta_input.value.strip()
            if not msg:
                return
            if not state.memoria_contexto:
                ui.notify(
                    "La memoria está vacía. Procesa archivos primero.", type="warning"
                )
                return

            with chat_logs:
                ui.chat_message(msg, sent=True, name="Tú", stamp="ahora").classes(
                    "text-sm"
                )
                spinner = ui.spinner(size="md", color="indigo")

            pregunta_input.value = ""

            # Construimos el contexto a partir de lo que ya está en memoria
            contexto_texto = "\n".join(
                [f"ARCHIVO {n}:\n{c}" for n, c in state.memoria_contexto.items()]
            )

            full_prompt = (
                f"Eres un consultor experto en ERPNext. Utiliza la siguiente información técnica para responder:\n"
                f"{contexto_texto}\n\n"
                f"USUARIO PREGUNTA: {msg}\n"
                f"RESPUESTA TÉCNICA:"
            )

            try:
                response = await run.io_bound(Settings.llm.complete, full_prompt)
                chat_logs.remove(spinner)
                with chat_logs:
                    ui.chat_message(response.text, name="DocBot", stamp="IA").classes(
                        "text-sm bg-indigo-50 shadow-sm border border-indigo-100"
                    )
            except Exception as e:
                chat_logs.remove(spinner)
                ui.notify(f"Error en LLM: {e}")

            chat_logs.run_method("scrollTo", 0, 99999)

        async def procesar_lote():
            if not state.seleccionados:
                ui.notify("Selecciona archivos", type="warning")
                return

            total = len(state.seleccionados)
            with ui.dialog() as diag, ui.card().classes("p-8 items-center w-80"):
                ui.label("Alimentando Memoria...").classes("font-bold")
                progreso = ui.linear_progress(value=0).classes("w-full mt-2")
            diag.open()

            for i, ruta_file in enumerate(list(state.seleccionados)):
                nombre = os.path.basename(ruta_file)
                try:
                    with open(ruta_file, "r", encoding="utf-8") as f:
                        contenido = f.read()

                    # GUARDAR EN MEMORIA (Diccionario: llave=nombre, valor=contenido)
                    state.memoria_contexto[nombre] = contenido

                    # Generar manual físico opcionalmente
                    prompt = f"Genera un manual técnico breve para: {contenido}"
                    respuesta = await run.io_bound(Settings.llm.complete, prompt)
                    with open(
                        os.path.join(OUTPUT_DIR, nombre.replace(".", "_") + ".md"), "w"
                    ) as f_md:
                        f_md.write(respuesta.text)
                except Exception as e:
                    ui.notify(f"Error en {nombre}: {e}")

                progreso.value = (i + 1) / total

            diag.close()
            lbl_status_memoria.set_text(
                f"Memoria activa: {len(state.memoria_contexto)} archivos cargados."
            )
            ui.notify("Contexto cargado. ¡Haz tus preguntas!", type="positive")


ui.run(title="ERPNext Inteligente", port=8080)
