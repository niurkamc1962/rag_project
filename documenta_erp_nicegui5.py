import os
import json
import asyncio
import re
from pathlib import Path
from nicegui import ui, run
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings

# --- CONFIGURACIÓN ---
MODELO_LLM = "llama3.2-1b-instruct-q4km:latest"
Settings.llm = Ollama(model=MODELO_LLM, request_timeout=600.0)

SESSION_FILE = os.path.abspath("./data/sesion_ia.json")
MD_OUTPUT_DIR = os.path.abspath("./data/docs_md")

if not os.path.exists("./data"):
    os.makedirs("./data")
if not os.path.exists(MD_OUTPUT_DIR):
    os.makedirs(MD_OUTPUT_DIR)


# ---------------------------------------------------------------------------
# ESTADO GLOBAL
# ---------------------------------------------------------------------------
class AppState:
    def __init__(self):
        self.seleccionados: dict[str, str] = {}
        self.memoria_contexto: dict[str, str] = {}
        self.analisis_md: dict[str, str] = {}
        self.historial_chat: list[dict] = []
        # Widgets
        self.lbl_status = None
        self.chat_container = None
        self.btn_analizar = None
        self.progress_bar = None
        self.lbl_progreso = None
        self.progress_row = None

    def guardar_a_disco(self):
        datos = {
            "contexto": self.memoria_contexto,
            "analisis_md": self.analisis_md,
            "historial": self.historial_chat,
        }
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=4)

    def cargar_de_disco(self):
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                datos = json.load(f)
                self.memoria_contexto = datos.get("contexto", {})
                self.analisis_md = datos.get("analisis_md", {})
                self.historial_chat = datos.get("historial", [])
            return True
        return False


state = AppState()


# ---------------------------------------------------------------------------
# PROMPTS OPTIMIZADOS
# ---------------------------------------------------------------------------
def construir_prompt_analisis(nombre_json, contenido_json, nombre_py, contenido_py):
    nombre_doctype = nombre_json.replace(".json", "")
    return f"""Eres un experto en ERPNext. Analiza "{nombre_doctype}" y genera un Markdown profesional.

### REQUISITO CRÍTICO:
Incluye una sección llamada "## Diagrama de Flujo de Lógica". 
Dentro de esa sección, genera un bloque de código mermaid (usando ```mermaid) con un diagrama 'graph TD' que explique el flujo del archivo .py (validaciones, triggers como on_submit, etc).

# {nombre_doctype}
## Descripción General
## Campos Principales (Tabla Markdown)
## Diagrama de Flujo de Lógica
## Lógica del Controlador (.py)
## Cómo Usar Este Doctype (Paso a paso)

---
JSON: {contenido_json[:2500]}
---
PYTHON: {contenido_py[:2500]}
"""


def construir_prompt_chat(pregunta: str) -> str:
    contexto = "\n\n---\n\n".join(
        [f"DOC {n}:\n{md[:1500]}" for n, md in state.analisis_md.items()]
    )
    return f"Contexto ERPNext:\n{contexto}\n\nPregunta: {pregunta}\nRespuesta profesional en español:"


# ---------------------------------------------------------------------------
# UI HELPERS
# ---------------------------------------------------------------------------
def renderizar_contenido_mixto(texto_md, contenedor):
    """Detecta bloques de mermaid y los renderiza con ui.mermaid, el resto con ui.markdown"""
    contenedor.clear()
    with contenedor:
        # Expresión regular para encontrar bloques ```mermaid ... ```
        partes = re.split(r"```mermaid\s*(.*?)\s*```", texto_md, flags=re.DOTALL)

        for i, fragmento in enumerate(partes):
            if i % 2 == 1:  # Es un bloque de código mermaid
                with ui.card().classes("w-full bg-slate-50 border-dashed border-2 p-2"):
                    ui.mermaid(fragmento.strip())
            else:  # Es texto markdown normal
                if fragmento.strip():
                    ui.markdown(fragmento)


# ---------------------------------------------------------------------------
# PÁGINA PRINCIPAL
# ---------------------------------------------------------------------------
@ui.page("/")
def main_page():
    ui.colors(primary="#3949ab")

    with ui.column().classes("w-full items-center pb-12"):
        with ui.column().classes("w-full max-w-5xl p-4 gap-4"):
            ui.label("🧠 ERPNext DocBot + Flowcharts").classes(
                "text-4xl font-black text-indigo-900 self-center"
            )

            # PANEL ARCHIVOS
            with ui.expansion("📁 Configuración", icon="folder_open").classes(
                "w-full border rounded-xl"
            ):
                with ui.column().classes("p-4 w-full gap-3"):
                    input_ruta = ui.input("Ruta de la carpeta").classes("w-full")
                    with ui.row():
                        ui.button("Escanear", on_click=lambda: listar(input_ruta.value))
                        ui.button("Cargar Sesión", on_click=lambda: recuperar()).props(
                            "outline"
                        )
                    container_lista = ui.column().classes(
                        "w-full max-h-48 overflow-auto border p-2 bg-slate-50"
                    )

            # PROGRESO
            state.progress_row = (
                ui.row().classes("w-full items-center gap-3").set_visibility(False)
            )
            with state.progress_row:
                state.lbl_progreso = ui.label("").classes(
                    "text-sm text-slate-600 min-w-48"
                )
                state.progress_bar = ui.linear_progress(value=0).classes("flex-grow")

            state.btn_analizar = (
                ui.button(
                    "🔍 Analizar y Generar Diagramas",
                    on_click=lambda: asyncio.ensure_future(analizar()),
                )
                .classes("w-full bg-indigo-700 text-white py-3")
                .set_visibility(False)
            )

            # DOCUMENTOS GENERADOS
            ui.label("📄 Documentación Generada").classes("text-xl font-bold mt-4")
            container_docs = ui.column().classes("w-full gap-2")

            # CHAT
            with ui.card().classes(
                "w-full shadow-2xl rounded-2xl overflow-hidden mt-6"
            ):
                ui.label("💬 Consultor Inteligente").classes(
                    "w-full bg-indigo-800 text-white p-4 font-bold text-center"
                )
                state.chat_container = ui.column().classes(
                    "w-full h-[400px] overflow-y-auto p-6 bg-white"
                )
                with ui.row().classes("w-full p-4 bg-gray-100 gap-2"):
                    prompt_input = (
                        ui.input(placeholder="Pregunta...")
                        .classes("flex-grow")
                        .props("rounded outlined bg-white")
                    )
                    ui.button(
                        icon="send", on_click=lambda: asyncio.ensure_future(enviar())
                    ).classes("bg-indigo-600 text-white rounded-full")

        # --- LÓGICA ---
        def listar(ruta):
            if not os.path.exists(ruta):
                return
            container_lista.clear()
            state.seleccionados.clear()
            archivos = [f for f in os.listdir(ruta) if f.endswith((".py", ".json"))]
            with container_lista:
                for f in sorted(archivos):
                    full_p = os.path.join(ruta, f)
                    ui.checkbox(
                        f, on_change=lambda e, p=full_p, n=f: _toggle(e.value, n, p)
                    )

        def _toggle(val, n, p):
            state.seleccionados[n] = p if val else state.seleccionados.pop(n, None)
            state.btn_analizar.set_visibility(len(state.seleccionados) > 0)

        async def analizar():
            state.btn_analizar.disable()
            state.progress_row.set_visibility(True)

            # Agrupar pares
            bases = set(Path(f).stem for f in state.seleccionados.keys())
            total = len(bases)

            for i, base in enumerate(bases):
                state.lbl_progreso.set_text(f"Procesando {base}...")
                state.progress_bar.set_value(i / total)

                # Leer archivos
                cj = _read_file(state.seleccionados.get(f"{base}.json"))
                cp = _read_file(state.seleccionados.get(f"{base}.py"))

                res = await run.io_bound(
                    Settings.llm.complete,
                    construir_prompt_analisis(f"{base}.json", cj, f"{base}.py", cp),
                )
                state.analisis_md[base] = res.text

                # Crear la tarjeta con el renderizado mixto
                with container_docs:
                    with ui.expansion(f"📄 {base}.md", icon="schema").classes(
                        "w-full border rounded"
                    ):
                        # Contenedor interno para el markdown + mermaid
                        cont_interno = ui.column().classes("p-4 w-full")
                        renderizar_contenido_mixto(res.text, cont_interno)

            state.progress_bar.set_value(1.0)
            state.btn_analizar.enable()
            state.guardar_a_disco()
            ui.notify("Análisis completo con diagramas", type="positive")

        def _read_file(p):
            if not p:
                return ""
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                return f.read()

        def recuperar():
            if state.cargar_de_disco():
                container_docs.clear()
                for base, md in state.analisis_md.items():
                    with container_docs:
                        with ui.expansion(f"📄 {base}.md", icon="article").classes(
                            "w-full border rounded"
                        ):
                            c = ui.column().classes("p-4 w-full")
                            renderizar_contenido_mixto(md, c)
                ui.notify("Sesión y diagramas recuperados")

        async def enviar():
            texto = prompt_input.value
            if not texto:
                return
            with state.chat_container:
                ui.chat_message(texto, sent=True, name="Tú")
                wait = ui.spinner()
            prompt_input.value = ""
            res = await run.io_bound(
                Settings.llm.complete, construir_prompt_chat(texto)
            )
            state.chat_container.remove(wait)
            with state.chat_container:
                ui.chat_message(res.text, name="Bot")


ui.run(port=8080)
