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


class Processor:
    def __init__(self):
        self.ruta_actual = ""
        self.archivo_seleccionado = ""

    def obtener_items(self, ruta):
        try:
            items = []
            for entry in os.scandir(ruta):
                # Filtramos para ver carpetas o archivos de interés
                if entry.is_dir():
                    items.append(
                        {"name": entry.name, "path": entry.path, "type": "dir"}
                    )
                elif entry.name.endswith((".json", ".py", ".md")):
                    items.append(
                        {"name": entry.name, "path": entry.path, "type": "file"}
                    )
            return sorted(items, key=lambda x: (x["type"] != "dir", x["name"].lower()))
        except Exception as e:
            ui.notify(f"Error al leer la ruta: {e}", type="negative")
            return []


proc = Processor()


@ui.page("/")
def main_page():
    ui.colors(primary="#5c6bc0")

    with ui.column().classes("w-full max-w-4xl mx-auto p-8 gap-6"):
        # TÍTULO
        with ui.row().classes("items-center gap-4"):
            ui.icon("settings_suggest", size="40px", color="primary")
            ui.label("Documentador ERPNext (Modo Ruta Directa)").classes(
                "text-3xl font-bold"
            )

        # PASO 1: ESCOGER EL CAMINO
        with ui.card().classes("w-full p-6 shadow-lg"):
            ui.label("1. Establece la ruta base del proyecto").classes(
                "text-lg font-bold mb-2"
            )
            with ui.row().classes("w-full items-center gap-4"):
                input_ruta = ui.input(
                    label="Pegar ruta aquí", placeholder="/home/niurka/Proyectos-TM/..."
                ).classes("flex-grow")
                ui.button(
                    "Cargar Carpeta",
                    icon="refresh",
                    on_click=lambda: actualizar_visor(),
                )

        # PASO 2: VISOR DE CARPETAS Y ARCHIVOS (Aparece al cargar)
        container_visor = ui.column().classes("w-full gap-2")

        def actualizar_visor():
            ruta = input_ruta.value.strip()
            if not os.path.exists(ruta):
                ui.notify("La ruta no existe", type="warning")
                return

            proc.ruta_actual = ruta
            container_visor.clear()
            items = proc.obtener_items(ruta)

            with container_visor:
                ui.label(f"Mostrando contenido en: {ruta}").classes(
                    "text-sm text-gray-500 italic"
                )
                # Usamos un grid para que se vea ordenado
                with ui.grid(columns=3).classes("w-full gap-4"):
                    for item in items:
                        icon = "folder" if item["type"] == "dir" else "description"
                        color = "orange" if item["type"] == "dir" else "blue-grey"

                        with (
                            ui.card()
                            .classes(
                                "cursor-pointer hover:bg-indigo-50 p-3 items-center text-center"
                            )
                            .on("click", lambda i=item: seleccionar(i))
                        ):
                            ui.icon(icon, size="32px", color=color)
                            ui.label(item["name"]).classes(
                                "text-xs font-medium truncate w-full"
                            )

        # PASO 3: ACCIONES SOBRE SELECCIÓN
        with ui.card().classes("w-full p-6 bg-slate-50 border-dashed border-2"):
            ui.label("2. Archivo Seleccionado").classes("text-lg font-bold")
            lbl_seleccion = ui.label("Ninguno").classes(
                "text-indigo-700 font-mono text-sm mb-4"
            )

            async def ejecutar_ia():
                if not proc.archivo_seleccionado:
                    ui.notify(
                        "Primero selecciona un archivo de la lista de arriba",
                        type="warning",
                    )
                    return

                with ui.dialog() as dialog, ui.card().classes("p-8 items-center"):
                    ui.spinner(size="xl")
                    ui.label("Procesando con Llama 3.2...")
                dialog.open()

                try:
                    with open(proc.archivo_seleccionado, "r", encoding="utf-8") as f:
                        code = f.read()

                    prompt = f"Analiza este archivo de ERPNext y crea un manual técnico: {code}"
                    respuesta = await run.io_bound(Settings.llm.complete, prompt)

                    # Guardar
                    nombre = (
                        os.path.basename(proc.archivo_seleccionado).replace(".", "_")
                        + ".md"
                    )
                    with open(os.path.join(OUTPUT_DIR, nombre), "w") as f_md:
                        f_md.write(respuesta.text)

                    area_resultado.set_content(respuesta.text)
                    ui.notify(f"Guardado como {nombre}", type="positive")
                finally:
                    dialog.close()

            ui.button(
                "GENERAR MANUAL MD", icon="auto_awesome", on_click=ejecutar_ia
            ).classes("w-full py-4")

        # RESULTADO
        area_resultado = ui.markdown().classes(
            "w-full p-6 border rounded bg-white shadow-inner min-h-[300px]"
        )

    def seleccionar(item):
        if item["type"] == "dir":
            # Si es carpeta, actualizamos el input y recargamos para "entrar"
            input_ruta.value = item["path"]
            actualizar_visor()
        else:
            proc.archivo_seleccionado = item["path"]
            lbl_seleccion.set_text(item["path"])
            ui.notify(f"Seleccionado: {item['name']}")


ui.run(title="ERPNext Documenter", port=8080)
