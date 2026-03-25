import os
import json
from nicegui import ui, run
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings

# --- CONFIGURACIÓN DE IA ---
MODELO_LLM = "llama3.2-1b-instruct-q4km:latest"
Settings.llm = Ollama(model=MODELO_LLM, request_timeout=600.0)
OUTPUT_DIR = "./data/manuales_md"

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)


class ERPDocumenter:
    def __init__(self):
        self.ruta_proyecto = ""
        self.doctypes = []

    def buscar_doctypes(self, ruta):
        self.doctypes = []
        for root, dirs, files in os.walk(ruta):
            if "doctype" in dirs:
                path_dt = os.path.join(root, "doctype")
                for d in os.listdir(path_dt):
                    json_file = os.path.join(path_dt, d, f"{d}.json")
                    if os.path.exists(json_file):
                        self.doctypes.append(
                            {
                                "label": f"{os.path.basename(root)} > {d}",
                                "value": json_file,
                                "name": d,
                            }
                        )
        return self.doctypes


doc_manager = ERPDocumenter()


# --- INTERFAZ CON NICEGUI ---
@ui.page("/")
def main_page():
    ui.colors(primary="#5898d4")

    with ui.header().classes("items-center justify-between"):
        ui.label("ERPNext AI Documenter").classes("text-2xl font-bold")
        ui.icon("description", size="lg")

    with ui.column().classes("w-full items-center"):
        # 1. Selección de Ruta (Input manual o pegado)
        with ui.card().classes("w-3/4 m-4 p-4"):
            ui.label("1. Configura la ruta de tu App ERPNext").classes("text-h6")
            ruta_input = ui.input(
                "Ruta local del proyecto",
                placeholder="/home/niurka/erpnext/apps/mi_app",
            ).classes("w-full")

            def cargar_doctypes():
                if os.path.exists(ruta_input.value):
                    lista = doc_manager.buscar_doctypes(ruta_input.value)
                    selector.options = lista
                    selector.update()
                    ui.notify(f"Se encontraron {len(lista)} DocTypes", type="positive")
                else:
                    ui.notify("Ruta no válida", type="negative")

            ui.button("Escanear Proyecto", on_click=cargar_doctypes).classes("mt-2")

        # 2. Selección de DocType y Generación
        with ui.card().classes("w-3/4 m-4 p-4"):
            ui.label("2. Selecciona y Genera").classes("text-h6")
            selector = ui.select(options=[], label="Selecciona un DocType").classes(
                "w-full"
            )

            async def generar_manual():
                if not selector.value:
                    ui.notify("Selecciona un DocType primero", type="warning")
                    return

                with ui.dialog() as dialog, ui.card():
                    ui.label("Generando manual con IA... por favor espera.")
                    ui.spinner(size="lg")
                dialog.open()

                # Cargar JSON
                with open(selector.value, "r", encoding="utf-8") as f:
                    data_json = json.load(f)

                prompt = f"Actúa como experto en ERPNext. Traduce este JSON a manual de usuario MD: {json.dumps(data_json)}"

                # Ejecutar IA en un hilo separado para no bloquear la web
                respuesta = await run.io_bound(Settings.llm.complete, prompt)

                # Guardar
                nombre_archivo = (
                    f"{os.path.basename(os.path.dirname(selector.value))}_manual.md"
                )
                with open(os.path.join(OUTPUT_DIR, nombre_archivo), "w") as f_md:
                    f_md.write(respuesta.text)

                dialog.close()
                ui.notify(f"Manual guardado: {nombre_archivo}", type="positive")
                resultado_area.set_content(respuesta.text)

            ui.button("Generar Manual (.md)", on_click=generar_manual).classes(
                "w-full bg-orange-500"
            )

        # 3. Vista Previa
        with ui.card().classes("w-3/4 m-4 p-4"):
            ui.label("Vista Previa").classes("text-h6")
            resultado_area = ui.markdown().classes("border p-4 w-full")


ui.run(title="ERPNext Documenter", port=8080)
