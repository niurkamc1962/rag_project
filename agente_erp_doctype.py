import os
import json
import asyncio
import re
from pathlib import Path
from nicegui import ui, run
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings

# ---------------------------------------------------------------------------
# CONFIGURACIÓN — Ajustada para 12GB RAM + HDD
# ---------------------------------------------------------------------------
# llama3.2-3b: mejor calidad con tu hardware
# qwen2.5-1.5b-instruct-q4_k_m.0: más rápido si el 3b se pone lento
MODELO_LLM = "qwen2.5-1.5b-instruct-q4_k_m.0"

# Timeout alto por el HDD — cada sección pequeña igual puede tardar
Settings.llm = Ollama(model=MODELO_LLM, request_timeout=300.0)

SESSION_FILE = os.path.abspath("./data/sesion_ia.json")
MD_OUTPUT_DIR = os.path.abspath("./data/docs_md")
os.makedirs("./data", exist_ok=True)
os.makedirs(MD_OUTPUT_DIR, exist_ok=True)

# Mermaid.js — se inyecta dentro de @ui.page con ui.add_head_html()
MERMAID_HEAD = """
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
  document.addEventListener('DOMContentLoaded', function() {
    if (window.mermaid) {
      mermaid.initialize({ startOnLoad: false, theme: 'default',
        themeVariables: { primaryColor:'#e8eaf6', primaryTextColor:'#1a237e',
                          primaryBorderColor:'#3949ab', lineColor:'#5c6bc0' } });
    }
  });
  window.renderMermaidNode = function(nodeId) {
    setTimeout(function() {
      var el = document.getElementById(nodeId);
      if (!el || !window.mermaid) return;
      mermaid.run({ nodes:[el] }).catch(function(e) {
        el.innerHTML = '<div style="color:#c62828;padding:8px;border:1px solid #ef9a9a;border-radius:6px">'
          + 'Error en diagrama: ' + e.message + '</div>';
      });
    }, 500);
  };
</script>
<style>
  .mermaid svg { max-width:100% !important; border-radius:8px; }
</style>
"""

# ---------------------------------------------------------------------------
# SECCIONES — cada una es una llamada independiente al LLM
# Las más simples van primero para resultados rápidos visibles
# ---------------------------------------------------------------------------
SECCIONES = [
    {
        "id": "descripcion",
        "titulo": "## Descripción General",
        "prompt": (
            "En 2-3 oraciones cortas explica qué es el Doctype '{doctype}' en ERPNext "
            "y para qué sirve. Solo el texto, sin títulos ni listas.\n\n"
            "JSON:\n{json_snippet}"
        ),
    },
    {
        "id": "campos",
        "titulo": "## Campos Principales",
        "prompt": (
            "Del siguiente JSON del Doctype '{doctype}', lista los campos más importantes "
            "en una tabla Markdown con columnas: Campo | Tipo | Descripción | Obligatorio.\n"
            "Máximo 12 filas. Solo la tabla, sin texto adicional.\n\n"
            "JSON:\n{json_snippet}"
        ),
    },
    {
        "id": "logica",
        "titulo": "## Lógica del Controlador (.py)",
        "prompt": (
            "Explica en lenguaje simple (sin jerga técnica) qué hace el archivo Python "
            "del Doctype '{doctype}': validaciones, cálculos automáticos y eventos "
            "(before_save, on_submit, etc). Máximo 150 palabras.\n\n"
            "PYTHON:\n{py_snippet}"
        ),
    },
    {
        "id": "flujo",
        "titulo": "## Flujo de Creación",
        "prompt": (
            "Genera SOLO un bloque mermaid (flowchart TD) que muestre los pasos para "
            "crear un registro de '{doctype}' en ERPNext. "
            "Usa entre 5 y 8 nodos. Pon TODOS los textos entre comillas dobles. "
            "No escribas nada fuera del bloque mermaid.\n\n"
            "Ejemplo de formato correcto:\n"
            "```mermaid\n"
            "flowchart TD\n"
            '    A["Paso 1"] --> B["Paso 2"]\n'
            '    B --> C{{"¿Condición?"}}\n'
            '    C -->|Sí| D["Paso 3"]\n'
            '    C -->|No| E["Corregir"]\n'
            '    D --> F["Fin"]\n'
            "```\n\n"
            "JSON:\n{json_snippet}"
        ),
    },
    {
        "id": "relaciones",
        "titulo": "## Relaciones con Otros Doctypes",
        "prompt": (
            "Genera SOLO un bloque mermaid (graph LR) que muestre qué Doctypes necesita "
            "'{doctype}' y qué documentos genera. Máximo 6 nodos. "
            "Todos los textos entre comillas dobles. "
            "No escribas nada fuera del bloque mermaid.\n\n"
            "Ejemplo:\n"
            "```mermaid\n"
            "graph LR\n"
            '    A["Maestro requerido"] --> B["{doctype}"]\n'
            '    B --> C["Documento generado"]\n'
            "```\n\n"
            "JSON:\n{json_snippet}"
        ),
    },
    {
        "id": "como_usar",
        "titulo": "## Cómo Usar Este Doctype",
        "prompt": (
            "Escribe una guía numerada de exactamente 5 pasos para crear un registro "
            "de '{doctype}' en ERPNext desde cero. Sé concreto con nombres de campos. "
            "Solo la lista numerada, sin texto antes ni después.\n\n"
            "JSON:\n{json_snippet}"
        ),
    },
    {
        "id": "casos",
        "titulo": "## Casos de Uso Comunes",
        "prompt": (
            "Lista 3 ejemplos concretos de cuándo se usa el Doctype '{doctype}' en "
            "una empresa real. Formato: lista con guiones. Sin texto adicional.\n\n"
            "JSON:\n{json_snippet}"
        ),
    },
]


# ---------------------------------------------------------------------------
# ESTADO GLOBAL
# ---------------------------------------------------------------------------
class AppState:
    def __init__(self):
        self.seleccionados: dict[str, str] = {}
        self.memoria_contexto: dict[str, str] = {}
        self.analisis_md: dict[str, str] = {}
        self.historial_chat: list[dict] = []
        self.lbl_status = None
        self.chat_container = None
        self.btn_analizar = None
        self.progress_bar = None
        self.lbl_progreso = None
        self.progress_row = None

    def guardar_a_disco(self):
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "contexto": self.memoria_contexto,
                    "analisis_md": self.analisis_md,
                    "historial": self.historial_chat,
                },
                f,
                ensure_ascii=False,
                indent=4,
            )

    def cargar_de_disco(self):
        if not os.path.exists(SESSION_FILE):
            return False
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            datos = json.load(f)
        self.memoria_contexto = datos.get("contexto", {})
        self.analisis_md = datos.get("analisis_md", {})
        self.historial_chat = datos.get("historial", [])
        return True


state = AppState()


# ---------------------------------------------------------------------------
# LLAMADA AL LLM — una sección a la vez
# ---------------------------------------------------------------------------
async def generar_seccion(
    seccion: dict, doctype: str, json_snippet: str, py_snippet: str
) -> str:
    """
    Llama al LLM con el prompt de UNA sola sección.
    Reintenta una vez si falla por timeout.
    """
    prompt = seccion["prompt"].format(
        doctype=doctype,
        json_snippet=json_snippet[:1500],
        py_snippet=py_snippet[:1500],
    )
    for intento in range(2):  # máximo 2 intentos
        try:
            res = await run.io_bound(Settings.llm.complete, prompt)
            return res.text.strip()
        except Exception as e:
            if intento == 0:
                await asyncio.sleep(2)  # pequeña pausa antes de reintentar
            else:
                return f"> ⚠️ No se pudo generar esta sección: {e}"
    return "> ⚠️ Error desconocido"


def ensurenar_bloque_mermaid(texto: str) -> str:
    """Si el modelo devolvió el diagrama sin las comillas del bloque, lo envuelve."""
    t = texto.strip()
    if t.startswith("```mermaid"):
        return t
    if t.startswith("flowchart") or t.startswith("graph"):
        return f"```mermaid\n{t}\n```"
    return t


# ---------------------------------------------------------------------------
# RENDERIZADOR MARKDOWN + MERMAID
# ---------------------------------------------------------------------------
def render_md_con_mermaid(parent_container, md_texto: str):
    patron = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
    partes = patron.split(md_texto)
    counter = [0]

    with parent_container:
        for i, parte in enumerate(partes):
            if not parte.strip():
                continue
            if i % 2 == 0:
                ui.markdown(parte).classes("text-sm w-full")
            else:
                counter[0] += 1
                nid = f"mermaid-{abs(hash(md_texto))}-{counter[0]}"
                code = parte.strip()
                ui.html(
                    f'<div class="mermaid" id="{nid}">{code}</div>'
                    f"<script>window.renderMermaidNode('{nid}');</script>"
                ).classes("w-full my-2")


# ---------------------------------------------------------------------------
# PROMPT CHAT
# ---------------------------------------------------------------------------
def construir_prompt_chat(pregunta: str) -> str:
    if state.analisis_md:
        ctx = "\n\n---\n\n".join(
            f"## {n}:\n{md[:2000]}" for n, md in state.analisis_md.items()
        )
        fuente = "documentación analizada"
    else:
        ctx = "\n".join(
            f"DOC {n}:\n{c[:1500]}" for n, c in state.memoria_contexto.items()
        )
        fuente = "archivos cargados"

    return (
        f"Eres un experto en ERPNext. Usa la {fuente} para responder "
        f"de forma clara y en español.\n\n"
        f"CONTEXTO:\n{ctx}\n\n"
        f"PREGUNTA: {pregunta}\nRESPUESTA:"
    )


# ---------------------------------------------------------------------------
# HELPERS UI — tarjeta de doctype
# ---------------------------------------------------------------------------
def dibujar_tarjeta_doctype(container, base: str, md_texto: str, md_path: str):
    with container:
        with ui.expansion(f"📄 {base}.md", icon="article").classes(
            "w-full border rounded-lg bg-slate-50"
        ):
            with ui.column().classes("p-3 gap-2 w-full") as card:
                render_md_con_mermaid(card, md_texto)
                ui.button(
                    "⬇️ Descargar .md", on_click=lambda p=md_path: ui.download(p)
                ).props("flat dense").classes("text-indigo-600 self-end")


# ---------------------------------------------------------------------------
# PÁGINA PRINCIPAL
# ---------------------------------------------------------------------------
@ui.page("/")
def main_page():
    ui.add_head_html(MERMAID_HEAD)
    ui.colors(primary="#3949ab")

    with ui.column().classes("w-full items-center pb-12"):
        with ui.column().classes("w-full max-w-5xl p-4 gap-4"):

            ui.label("🧠 ERPNext DocBot").classes(
                "text-4xl font-black text-indigo-900 self-center"
            )

            # ── Panel archivos ───────────────────────────────────────────────
            with ui.expansion("📁 Selección de Archivos", icon="folder_open").classes(
                "w-full border rounded-xl"
            ):
                with ui.column().classes("p-4 w-full gap-3"):
                    input_ruta = ui.input(
                        "Ruta de la carpeta con archivos del Doctype",
                        placeholder="/home/usuario/frappe-bench/apps/erpnext/...",
                    ).classes("w-full")
                    with ui.row().classes("gap-2"):
                        ui.button(
                            "📂 Escanear Carpeta",
                            on_click=lambda: listar(input_ruta.value),
                        )
                        ui.button(
                            "💾 Cargar Sesión", on_click=lambda: recuperar()
                        ).props("outline")
                    container_lista = ui.column().classes(
                        "w-full max-h-60 overflow-y-auto border rounded-lg p-3 bg-slate-50"
                    )

            # ── Progreso ─────────────────────────────────────────────────────
            state.progress_row = ui.row().classes("w-full items-center gap-3")
            with state.progress_row:
                state.lbl_progreso = ui.label("").classes(
                    "text-sm text-slate-600 min-w-64"
                )
                state.progress_bar = ui.linear_progress(value=0).classes("flex-grow")
            state.progress_row.set_visibility(False)

            # ── Botón analizar ───────────────────────────────────────────────
            state.btn_analizar = ui.button(
                "🔍 Analizar Archivos Seleccionados",
                on_click=lambda: asyncio.ensure_future(analizar_archivos()),
            ).classes(
                "w-full bg-indigo-700 text-white text-lg font-bold py-3 rounded-xl"
            )
            state.btn_analizar.set_visibility(False)

            # ── Panel docs ───────────────────────────────────────────────────
            with ui.expansion(
                "📄 Documentos .md Generados", icon="description"
            ).classes("w-full border rounded-xl"):
                with ui.column().classes("p-4 w-full gap-2"):
                    container_docs = ui.column().classes("w-full gap-2")
                    ui.label("(Aquí aparecerán los .md tras el análisis)").classes(
                        "text-slate-400 text-sm"
                    )

            state.lbl_status = ui.label("Seleccione una carpeta para comenzar").classes(
                "text-sm text-slate-500 self-center"
            )

            # ── Chat ─────────────────────────────────────────────────────────
            with ui.card().classes(
                "w-full shadow-2xl rounded-2xl overflow-hidden border-0"
            ):
                ui.label("💬 Consultor de Doctypes ERPNext").classes(
                    "w-full bg-indigo-800 text-white p-4 font-bold text-center text-lg"
                )
                state.chat_container = ui.column().classes(
                    "w-full h-[500px] overflow-y-auto p-6 bg-white"
                )
                with ui.row().classes(
                    "w-full p-4 bg-gray-100 border-t items-center gap-2"
                ):
                    prompt_input = (
                        ui.input(placeholder="Ej: ¿Cómo creo una cuenta bancaria?")
                        .classes("flex-grow")
                        .props("rounded outlined bg-white")
                    )
                    ui.button(
                        icon="send", on_click=lambda: asyncio.ensure_future(enviar())
                    ).classes("bg-indigo-600 text-white rounded-full p-3")

        # ====================================================================
        # FUNCIONES
        # ====================================================================

        def actualizar_btn_analizar():
            state.btn_analizar.set_visibility(len(state.seleccionados) > 0)

        def listar(ruta: str):
            if not ruta or not os.path.exists(ruta):
                ui.notify("⚠️ Ruta no válida", color="negative")
                return
            archivos = sorted(
                [f for f in os.listdir(ruta) if f.endswith((".py", ".json", ".md"))]
            )
            if not archivos:
                ui.notify("No se encontraron archivos .py .json .md")
                return
            container_lista.clear()
            state.seleccionados.clear()
            actualizar_btn_analizar()
            with container_lista:
                bases: dict[str, list[str]] = {}
                for f in archivos:
                    bases.setdefault(Path(f).stem, []).append(f)
                for base, grupo in bases.items():
                    with ui.row().classes("items-center gap-1 py-1 border-b"):
                        ui.label(f"📦 {base}").classes(
                            "font-semibold text-indigo-800 w-48 truncate"
                        )
                        for archivo in grupo:
                            ext = Path(archivo).suffix
                            color = {
                                ".json": "text-green-700 bg-green-50",
                                ".py": "text-blue-700 bg-blue-50",
                                ".md": "text-purple-700 bg-purple-50",
                            }.get(ext, "")
                            ui.checkbox(
                                ext,
                                on_change=lambda e, p=os.path.join(
                                    ruta, archivo
                                ), n=archivo: _toggle(e.value, n, p),
                            ).classes(f"text-xs px-2 rounded {color}")
            state.lbl_status.set_text(
                f"Encontrados {len(archivos)} archivos en {len(bases)} doctypes."
            )

        def _toggle(sel: bool, nombre: str, path: str):
            if sel:
                state.seleccionados[nombre] = path
            else:
                state.seleccionados.pop(nombre, None)
            actualizar_btn_analizar()
            state.lbl_status.set_text(
                f"{len(state.seleccionados)} archivos seleccionados."
            )

        async def analizar_archivos():
            if not state.seleccionados:
                ui.notify("Selecciona al menos un archivo primero")
                return

            state.btn_analizar.disable()
            state.progress_row.set_visibility(True)
            state.progress_bar.set_value(0)

            # Leer contenidos
            for nombre, path in state.seleccionados.items():
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    state.memoria_contexto[nombre] = f.read()

            # Agrupar en pares json+py
            bases_vistas: set[str] = set()
            pares = []
            for nombre in state.memoria_contexto:
                base = Path(nombre).stem
                if base in bases_vistas:
                    continue
                cj = state.memoria_contexto.get(base + ".json", "")
                cp = state.memoria_contexto.get(base + ".py", "")
                if cj or cp:
                    pares.append((base, cj, cp))
                    bases_vistas.add(base)

            total_pasos = len(pares) * len(SECCIONES)
            paso_actual = 0
            container_docs.clear()

            for base, cj, cp in pares:
                secciones_generadas: list[str] = [f"# {base}\n"]

                for sec in SECCIONES:
                    paso_actual += 1
                    pct = paso_actual / total_pasos
                    state.progress_bar.set_value(pct)
                    state.lbl_progreso.set_text(
                        f"[{base}] {sec['titulo'].replace('## ','')} "
                        f"({paso_actual}/{total_pasos})"
                    )

                    contenido = await generar_seccion(sec, base, cj, cp)

                    # Para secciones de diagrama, asegurar bloque mermaid
                    if sec["id"] in ("flujo", "relaciones"):
                        contenido = ensurenar_bloque_mermaid(contenido)

                    secciones_generadas.append(f"{sec['titulo']}\n\n{contenido}")

                md_texto = "\n\n".join(secciones_generadas)
                state.analisis_md[base] = md_texto

                md_path = os.path.join(MD_OUTPUT_DIR, f"{base}.md")
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_texto)

                dibujar_tarjeta_doctype(container_docs, base, md_texto, md_path)

            state.progress_bar.set_value(1.0)
            state.lbl_progreso.set_text(
                f"✅ {len(pares)} doctype(s) analizados — guardados en ./data/docs_md/"
            )
            state.btn_analizar.enable()
            state.guardar_a_disco()
            ui.notify(f"✅ {len(pares)} documentos generados", color="positive")
            with state.chat_container:
                ui.chat_message(
                    f"✅ Analicé **{len(pares)}** doctype(s): "
                    + ", ".join(state.analisis_md.keys())
                    + ". ¡Ahora puedes preguntarme sobre ellos!",
                    name="DocBot",
                    sent=False,
                ).classes("bg-indigo-50 text-sm")

        def recuperar():
            if state.cargar_de_disco():
                state.lbl_status.set_text(
                    f"Sesión recuperada: {len(state.memoria_contexto)} archivos, "
                    f"{len(state.analisis_md)} .md generados."
                )
                state.chat_container.clear()
                with state.chat_container:
                    for m in state.historial_chat:
                        ui.chat_message(
                            m["text"], name=m["name"], sent=m["sent"]
                        ).classes("text-sm")
                container_docs.clear()
                for base, md_texto in state.analisis_md.items():
                    md_path = os.path.join(MD_OUTPUT_DIR, f"{base}.md")
                    dibujar_tarjeta_doctype(container_docs, base, md_texto, md_path)
                ui.notify("💾 Historial y documentos restaurados", color="positive")
            else:
                ui.notify("No hay sesión previa guardada", color="warning")

        async def enviar():
            texto = prompt_input.value.strip()
            if not texto:
                return
            if not state.analisis_md and not state.memoria_contexto:
                ui.notify("⚠️ Primero selecciona y analiza archivos", color="warning")
                return
            state.historial_chat.append({"name": "Tú", "text": texto, "sent": True})
            with state.chat_container:
                ui.chat_message(texto, sent=True, name="Tú").classes("text-sm")
                espera = ui.spinner(size="md")
            prompt_input.value = ""
            try:
                res = await run.io_bound(
                    Settings.llm.complete, construir_prompt_chat(texto)
                )
                state.chat_container.remove(espera)
                respuesta = res.text.strip()
                state.historial_chat.append(
                    {"name": "DocBot", "text": respuesta, "sent": False}
                )
                with state.chat_container:
                    ui.chat_message(respuesta, name="DocBot", sent=False).classes(
                        "bg-indigo-50 text-sm"
                    )
                state.guardar_a_disco()
                state.chat_container.run_method("scrollTo", 0, 99999)
            except Exception as e:
                state.chat_container.remove(espera)
                ui.notify(f"Error: {e}", color="negative")


ui.run(title="ERPNext DocBot", port=8080, reload=False)
