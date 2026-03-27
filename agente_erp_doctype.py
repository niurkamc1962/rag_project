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

# HTML de Mermaid.js — se inyecta dentro de @ui.page con ui.add_head_html()
MERMAID_HEAD = """
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
  document.addEventListener('DOMContentLoaded', function() {
    if (window.mermaid) {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'default',
        themeVariables: {
          primaryColor: '#e8eaf6',
          primaryTextColor: '#1a237e',
          primaryBorderColor: '#3949ab',
          lineColor: '#5c6bc0'
        }
      });
    }
  });
  window.renderMermaidNode = function(nodeId) {
    setTimeout(function() {
      var el = document.getElementById(nodeId);
      if (!el || !window.mermaid) return;
      mermaid.run({ nodes: [el] }).catch(function(e) {
        el.innerHTML = '<div style="color:#c62828;padding:8px;border:1px solid #ef9a9a;border-radius:6px">'
          + 'Error en diagrama: ' + e.message + '</div>';
      });
    }, 500);
  };
</script>
<style>
  .mermaid svg { max-width: 100% !important; border-radius: 8px; }
  .mermaid-src { background: #f8f9ff; border: 1px dashed #3949ab;
                 border-radius: 8px; padding: 12px; font-family: monospace;
                 font-size: 12px; color: #5c6bc0; white-space: pre-wrap; }
</style>
"""


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
# PROMPT ANALISIS DOCTYPE — incluye secciones Mermaid
# ---------------------------------------------------------------------------
def construir_prompt_analisis(nombre_json, contenido_json, nombre_py, contenido_py):
    nombre_doctype = nombre_json.replace(".json", "")
    return f"""Eres un experto en ERPNext y Frappe Framework. Analiza el Doctype "{nombre_doctype}" y genera documentación profesional en Markdown con estas secciones EXACTAS:

# {nombre_doctype}

## Descripción General
Explica en 2-3 oraciones qué hace este Doctype y para qué sirve en ERPNext.

## Campos Principales
Tabla Markdown: Campo | Tipo | Descripción | Obligatorio

## Lógica del Controlador (.py)
Explica en lenguaje simple qué hace el Python: validaciones, cálculos, eventos (before_save, on_submit, etc).

## Flujo de Creación
Diagrama del flujo de pasos para crear un registro. Usa EXACTAMENTE este formato de bloque:

```mermaid
flowchart TD
    A["Abrir módulo ERPNext"] --> B["Ir a {nombre_doctype}"]
    B --> C["Hacer clic en Nuevo"]
    C --> D["Completar campos obligatorios"]
    D --> E{{"¿Datos correctos?"}}
    E -->|Sí| F["Guardar registro"]
    E -->|No| G["Corregir errores"]
    G --> D
    F --> H["Registro creado"]
```

## Relaciones con Otros Doctypes
Diagrama de dependencias. Usa EXACTAMENTE este formato:

```mermaid
graph LR
    REQ1["Doctype requerido 1"] --> DOC["{nombre_doctype}"]
    REQ2["Doctype requerido 2"] --> DOC
    DOC --> GEN1["Documento que genera 1"]
    DOC --> GEN2["Documento que genera 2"]
```

## Cómo Usar Este Doctype
Guía numerada paso a paso, mínimo 5 pasos, para crear un registro real en ERPNext.

## Casos de Uso Comunes
3-4 ejemplos concretos.

---
JSON ({nombre_json}):
{contenido_json[:3000]}

---
PYTHON ({nombre_py}):
{contenido_py[:3000]}

---
IMPORTANTE: Responde SOLO con el Markdown. En los bloques mermaid pon SIEMPRE los textos entre comillas dobles. No uses paréntesis ni corchetes sin comillas dentro de nodos.
"""


# ---------------------------------------------------------------------------
# RENDERIZADOR MARKDOWN + MERMAID
# ---------------------------------------------------------------------------
def render_md_con_mermaid(parent_container, md_texto: str):
    """
    Divide el .md en bloques de texto normal y bloques ```mermaid```.
    - Texto normal  → ui.markdown()
    - Bloques mermaid → ui.html() con script que llama a renderMermaidNode()
    """
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
                codigo = parte.strip()
                html = (
                    f'<div class="mermaid" id="{nid}">{codigo}</div>'
                    f"<script>window.renderMermaidNode('{nid}');</script>"
                )
                ui.html(html).classes("w-full my-2")


# ---------------------------------------------------------------------------
# PROMPT CHAT
# ---------------------------------------------------------------------------
def construir_prompt_chat(pregunta: str) -> str:
    if state.analisis_md:
        contexto = "\n\n---\n\n".join(
            [f"## {nombre}:\n{md[:2000]}" for nombre, md in state.analisis_md.items()]
        )
        fuente = "documentación analizada de los Doctypes"
    else:
        contexto = "\n".join(
            [f"DOC {n}:\n{c[:1500]}" for n, c in state.memoria_contexto.items()]
        )
        fuente = "archivos cargados"

    return (
        f"Eres un experto en ERPNext. Usa la siguiente {fuente} para responder "
        f"de forma clara, precisa y en español.\n\n"
        f"CONTEXTO:\n{contexto}\n\n"
        f"PREGUNTA: {pregunta}\n\n"
        f"RESPUESTA PROFESIONAL:"
    )


# ---------------------------------------------------------------------------
# PÁGINA PRINCIPAL
# ---------------------------------------------------------------------------
@ui.page("/")
def main_page():
    # ── Inyectar Mermaid.js en el HEAD de esta página ─────────────────────
    ui.add_head_html(MERMAID_HEAD)

    ui.colors(primary="#3949ab")

    with ui.column().classes("w-full items-center pb-12"):
        with ui.column().classes("w-full max-w-5xl p-4 gap-4"):

            ui.label("🧠 ERPNext DocBot").classes(
                "text-4xl font-black text-indigo-900 self-center"
            )

            # ── Panel de archivos ────────────────────────────────────────────
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

            # ── Barra de progreso ────────────────────────────────────────────
            state.progress_row = ui.row().classes("w-full items-center gap-3")
            with state.progress_row:
                state.lbl_progreso = ui.label("").classes(
                    "text-sm text-slate-600 min-w-48"
                )
                state.progress_bar = ui.linear_progress(value=0).classes("flex-grow")
            state.progress_row.set_visibility(False)

            # ── Botón Analizar ───────────────────────────────────────────────
            state.btn_analizar = ui.button(
                "🔍 Analizar Archivos Seleccionados",
                on_click=lambda: asyncio.ensure_future(analizar_archivos()),
            ).classes(
                "w-full bg-indigo-700 text-white text-lg font-bold py-3 rounded-xl"
            )
            state.btn_analizar.set_visibility(False)

            # ── Panel de .md generados ───────────────────────────────────────
            with ui.expansion(
                "📄 Documentos .md Generados", icon="description"
            ).classes("w-full border rounded-xl"):
                with ui.column().classes("p-4 w-full gap-2"):
                    container_docs = ui.column().classes("w-full gap-2")
                    ui.label("(Aquí aparecerán los .md tras el análisis)").classes(
                        "text-slate-400 text-sm"
                    )

            # ── Estado ───────────────────────────────────────────────────────
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
        # FUNCIONES INTERNAS
        # ====================================================================

        def actualizar_btn_analizar():
            state.btn_analizar.set_visibility(len(state.seleccionados) > 0)

        def listar(ruta: str):
            if not ruta or not os.path.exists(ruta):
                ui.notify("⚠️ Ruta no válida o no existe", color="negative")
                return

            archivos = sorted(
                [f for f in os.listdir(ruta) if f.endswith((".py", ".json", ".md"))]
            )

            if not archivos:
                ui.notify("No se encontraron archivos .py, .json o .md")
                return

            container_lista.clear()
            state.seleccionados.clear()
            actualizar_btn_analizar()

            with container_lista:
                bases: dict[str, list[str]] = {}
                for f in archivos:
                    base = Path(f).stem
                    bases.setdefault(base, []).append(f)

                for base, archivos_grupo in bases.items():
                    with ui.row().classes("items-center gap-1 py-1 border-b"):
                        ui.label(f"📦 {base}").classes(
                            "font-semibold text-indigo-800 w-48 truncate"
                        )
                        for archivo in archivos_grupo:
                            full_path = os.path.join(ruta, archivo)
                            ext = Path(archivo).suffix
                            color = {
                                ".json": "text-green-700 bg-green-50",
                                ".py": "text-blue-700 bg-blue-50",
                                ".md": "text-purple-700 bg-purple-50",
                            }.get(ext, "")
                            ui.checkbox(
                                ext,
                                on_change=lambda e, p=full_path, n=archivo: _toggle(
                                    e.value, n, p
                                ),
                            ).classes(f"text-xs px-2 rounded {color}")

            state.lbl_status.set_text(
                f"Encontrados {len(archivos)} archivos en {len(bases)} doctypes."
            )

        def _toggle(seleccionado: bool, nombre: str, path: str):
            if seleccionado:
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

            # Identificar pares json+py
            bases_procesadas: set[str] = set()
            pares = []
            for nombre in list(state.memoria_contexto.keys()):
                base = Path(nombre).stem
                if base in bases_procesadas:
                    continue
                nj = base + ".json"
                np_ = base + ".py"
                cj = state.memoria_contexto.get(nj, "")
                cp = state.memoria_contexto.get(np_, "")
                if cj or cp:
                    pares.append((nj, cj, np_, cp))
                    bases_procesadas.add(base)

            total_pares = len(pares)
            container_docs.clear()

            for i, (nj, cj, np_, cp) in enumerate(pares):
                base = Path(nj).stem
                state.progress_bar.set_value(i / total_pares)
                state.lbl_progreso.set_text(
                    f"Analizando {i+1}/{total_pares}: {base}..."
                )

                prompt = construir_prompt_analisis(nj, cj, np_, cp)
                try:
                    res = await run.io_bound(Settings.llm.complete, prompt)
                    md_texto = res.text.strip()
                except Exception as e:
                    md_texto = f"# {base}\n\n> ⚠️ Error al generar: {e}"

                state.analisis_md[base] = md_texto

                md_path = os.path.join(MD_OUTPUT_DIR, f"{base}.md")
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_texto)

                with container_docs:
                    with ui.expansion(f"📄 {base}.md", icon="article").classes(
                        "w-full border rounded-lg bg-slate-50"
                    ):
                        with ui.column().classes("p-3 gap-2 w-full") as card:
                            render_md_con_mermaid(card, md_texto)
                            ui.button(
                                "⬇️ Descargar .md",
                                on_click=lambda p=md_path: ui.download(p),
                            ).props("flat dense").classes("text-indigo-600 self-end")

            state.progress_bar.set_value(1.0)
            state.lbl_progreso.set_text(
                f"✅ {total_pares} doctypes analizados — guardados en ./data/docs_md/"
            )
            state.btn_analizar.enable()
            state.guardar_a_disco()
            ui.notify(f"✅ {total_pares} documentos generados", color="positive")

            with state.chat_container:
                ui.chat_message(
                    f"✅ Analicé **{total_pares}** doctype(s): "
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
                with container_docs:
                    for base, md_texto in state.analisis_md.items():
                        md_path = os.path.join(MD_OUTPUT_DIR, f"{base}.md")
                        with ui.expansion(f"📄 {base}.md", icon="article").classes(
                            "w-full border rounded-lg bg-slate-50"
                        ):
                            with ui.column().classes("p-3 gap-2 w-full") as card:
                                render_md_con_mermaid(card, md_texto)
                                if os.path.exists(md_path):
                                    ui.button(
                                        "⬇️ Descargar .md",
                                        on_click=lambda p=md_path: ui.download(p),
                                    ).props("flat dense").classes(
                                        "text-indigo-600 self-end"
                                    )
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
            full_prompt = construir_prompt_chat(texto)

            try:
                res = await run.io_bound(Settings.llm.complete, full_prompt)
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
                ui.notify(f"Error al consultar el modelo: {e}", color="negative")


ui.run(title="ERPNext DocBot", port=8080, reload=False)
