import os
import json
import asyncio
import webbrowser
from nicegui import ui, run
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings

# --- CONFIGURACIÓN ---
MODELO_LLM = "llama3.2-1b-instruct-q4km:latest"
Settings.llm = Ollama(model=MODELO_LLM, request_timeout=600.0)
OUTPUT_DIR = os.path.abspath("./data/manuales_md")

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)


class MultiProcessor:
    def __init__(self):
        self.seleccionados = set()
        self.checkboxes = []
        self.archivos_finalizados = []


proc = MultiProcessor()


@ui.page("/")
def main_page():
    ui.colors(primary="#5c6bc0", secondary="#f5f5f5")

    with ui.column().classes("w-full max-w-5xl mx-auto p-8 gap-6"):
        ui.label("🚀 Documentador ERPNext Pro").classes("text-3xl font-bold")

        # PASO 1: RUTA
        with ui.card().classes("w-full p-6 shadow-md"):
            ui.label("1. Ruta del Proyecto").classes("text-lg font-bold mb-2")
            with ui.row().classes("w-full items-center gap-4"):
                input_ruta = ui.input(
                    label="Ruta local", placeholder="/home/niurka/..."
                ).classes("flex-grow")
                ui.button("Cargar", icon="refresh", on_click=lambda: cargar_contenido())

        # PASO 2: SELECCIÓN
        with ui.row().classes("w-full items-center justify-between mt-4"):
            ui.label("2. Selecciona Archivos").classes("text-lg font-bold")
            with ui.row():
                ui.button("Todo", on_click=lambda: marcar_todo(True)).props(
                    "outline size=sm"
                )
                ui.button("Nada", on_click=lambda: marcar_todo(False)).props(
                    "outline size=sm"
                )

        container_archivos = ui.column().classes(
            "w-full gap-2 p-4 border rounded bg-gray-50 max-h-80 overflow-auto"
        )

        def marcar_todo(valor: bool):
            for cb in proc.checkboxes:
                cb.value = valor

        def cargar_contenido():
            ruta = input_ruta.value.strip()
            if not os.path.exists(ruta):
                ui.notify("Ruta no válida", type="negative")
                return
            container_archivos.clear()
            proc.seleccionados.clear()
            proc.checkboxes.clear()
            try:
                items = sorted(
                    os.scandir(ruta), key=lambda e: (not e.is_dir(), e.name.lower())
                )
                with container_archivos:
                    for entry in items:
                        if entry.is_dir():
                            with ui.row().classes(
                                "items-center gap-2 p-1 hover:bg-blue-50 w-full cursor-pointer"
                            ):
                                ui.icon("folder", color="orange")
                                ui.label(entry.name).on(
                                    "click", lambda e=entry: navegar_a(e.path)
                                )
                        elif entry.name.endswith((".json", ".py", ".md")):
                            with ui.row().classes(
                                "items-center gap-2 p-1 border-b w-full"
                            ):
                                cb = ui.checkbox(
                                    text=entry.name,
                                    on_change=lambda e, p=entry.path: (
                                        proc.seleccionados.add(p)
                                        if e.value
                                        else proc.seleccionados.discard(p)
                                    ),
                                )
                                proc.checkboxes.append(cb)
            except Exception as e:
                ui.notify(f"Error: {e}")

        def navegar_a(nueva_ruta):
            input_ruta.value = nueva_ruta
            cargar_contenido()

        # PASO 3: PROCESAR
        ui.button(
            "GENERAR DOCUMENTACIÓN", icon="bolt", on_click=lambda: procesar_lote()
        ).classes("w-full bg-indigo-600 text-white mt-2 py-4")

        # PASO 4: RESULTADOS - CORRECCIÓN AQUÍ
        container_resultados = ui.column().classes("w-full gap-2 mt-4")
        container_resultados.set_visibility(
            False
        )  # Forma correcta de ocultar inicialmente

        log_container = ui.column().classes(
            "w-full p-4 bg-slate-900 text-teal-400 font-mono text-xs rounded h-40 overflow-auto"
        )

        async def procesar_lote():
            if not proc.seleccionados:
                ui.notify("Selecciona al menos un archivo", type="warning")
                return

            proc.archivos_finalizados = []
            container_resultados.set_visibility(False)
            total = len(proc.seleccionados)

            with ui.dialog() as diag, ui.card().classes("p-8 items-center w-80"):
                ui.label("Procesando...").classes("text-xl font-bold")
                progreso = ui.linear_progress(value=0).classes("w-full mt-4")
                lbl_file = ui.label("Preparando...").classes(
                    "text-xs italic mt-2 text-center"
                )
            diag.open()

            for i, ruta_file in enumerate(list(proc.seleccionados)):
                nombre = os.path.basename(ruta_file)
                lbl_file.set_text(f"Analizando: {nombre}")

                try:
                    with open(ruta_file, "r", encoding="utf-8") as f:
                        contenido = f.read()

                    prompt = f"Como experto en ERPNext, genera un manual de usuario en Markdown para este archivo: {contenido}"
                    respuesta = await run.io_bound(Settings.llm.complete, prompt)

                    nombre_out = nombre.replace(".", "_") + ".md"
                    ruta_final = os.path.join(OUTPUT_DIR, nombre_out)
                    with open(ruta_final, "w", encoding="utf-8") as f_md:
                        f_md.write(respuesta.text)

                    proc.archivos_finalizados.append(nombre_out)
                    with log_container:
                        ui.label(f"✅ Generado: {nombre_out}")
                except Exception as e:
                    with log_container:
                        ui.label(f"❌ Error en {nombre}: {e}").classes("text-red-400")

                progreso.value = (i + 1) / total
                log_container.run_method("scrollTo", 0, 99999)

            await asyncio.sleep(1)
            diag.close()
            mostrar_exito()

        def mostrar_exito():
            container_resultados.clear()
            container_resultados.set_visibility(True)
            with container_resultados:
                with ui.card().classes(
                    "w-full bg-green-50 p-6 border-green-200 border-2"
                ):
                    ui.label("🎉 ¡Tarea Completada!").classes(
                        "text-2xl font-bold text-green-800"
                    )
                    ui.label(
                        f"Se han guardado {len(proc.archivos_finalizados)} archivos en:"
                    ).classes("text-sm")
                    ui.label(OUTPUT_DIR).classes(
                        "text-xs font-mono bg-white p-2 border mb-4"
                    )

                    with ui.row():
                        ui.button(
                            "Abrir Carpeta",
                            icon="folder",
                            on_click=lambda: webbrowser.open(f"file://{OUTPUT_DIR}"),
                        ).classes("bg-green-700")
                        ui.button(
                            "Cerrar Aviso",
                            icon="close",
                            on_click=lambda: container_resultados.set_visibility(False),
                        ).props("outline")


ui.run(title="ERPNext Doc Pro", port=8080)
