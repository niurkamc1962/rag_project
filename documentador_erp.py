import os
import json
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog

# Intentamos importar streamlit, si falla es que estamos en la fase de "Lanzador"
try:
    import streamlit as st
    from llama_index.llms.ollama import Ollama
    from llama_index.core import Settings

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False


# === FASE 1: EL LANZADOR (Python Puro) ===
def lanzador():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    print("Seleccionando carpeta del proyecto ERPNext...")
    ruta = filedialog.askdirectory(
        title="Selecciona la carpeta raíz de tu App personalizada"
    )
    root.destroy()

    if ruta:
        # Guardamos la ruta en una variable de entorno y relanzamos este mismo script con Streamlit
        os.environ["ERP_PATH_LOCAL"] = ruta
        subprocess.run(["streamlit", "run", __file__])
    else:
        print("Operación cancelada.")


# === FASE 2: LA INTERFAZ (Streamlit) ===
def interfaz():
    # Configuración de Modelos
    MODELO_LLM = "llama3.2-1b-instruct-q4km:latest"
    Settings.llm = Ollama(model=MODELO_LLM, request_timeout=600.0)

    ruta_proyecto = os.environ.get("ERP_PATH_LOCAL", "")

    st.set_page_config(page_title="Generador de Documentación ERPNext", layout="wide")
    st.title("📖 Documentador de ERPNext Personalizado")
    st.info(f"📁 Proyecto actual: `{ruta_proyecto}`")

    # Carpeta donde se guardarán los resultados
    OUTPUT_DIR = "./data/manuales_md"
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # Buscador automático de DocTypes en la ruta seleccionada
    doctypes_encontrados = []
    for root, dirs, files in os.walk(ruta_proyecto):
        if "doctype" in dirs:
            path_dt = os.path.join(root, "doctype")
            for d in os.listdir(path_dt):
                json_file = os.path.join(path_dt, d, f"{d}.json")
                if os.path.exists(json_file):
                    doctypes_encontrados.append(
                        {
                            "nombre": d,
                            "ruta_json": json_file,
                            "modulo": os.path.basename(root),
                        }
                    )

    if not doctypes_encontrados:
        st.warning(
            "No se encontraron DocTypes (archivos .json) en la ruta seleccionada."
        )
        return

    # Selector de DocType
    st.sidebar.header("Configuración")
    opcion = st.sidebar.selectbox(
        "Selecciona un DocType para documentar:",
        options=doctypes_encontrados,
        format_func=lambda x: f"{x['modulo']} > {x['nombre']}",
    )

    if st.button(f"Generar Manual para {opcion['nombre']}"):
        with open(opcion["ruta_json"], "r", encoding="utf-8") as f:
            data_json = json.load(f)

        with st.spinner(
            "🤖 El agente está leyendo el código y redactando el manual..."
        ):
            prompt = f"""
            Actúa como un experto funcional de ERPNext. Tu tarea es leer este JSON técnico y escribir un manual de usuario en Markdown (.md).
            
            ESTRUCTURA DEL MANUAL:
            # Manual de Usuario: {data_json.get('name')}
            ## 1. Introducción
            Explica para qué sirve este formulario de forma sencilla.
            
            ## 2. Campos del Formulario
            Lista los campos más importantes (label). Explica qué debe ingresar el usuario.
            
            ## 3. Notas Técnicas y Validaciones
            Menciona campos obligatorios o de solo lectura.
            
            CONTENIDO TÉCNICO (JSON):
            {json.dumps(data_json, indent=2)}
            """

            try:
                respuesta = Settings.llm.complete(prompt)

                # Guardar el archivo MD
                nombre_archivo = f"{opcion['nombre']}_manual.md"
                ruta_final = os.path.join(OUTPUT_DIR, nombre_archivo)
                with open(ruta_final, "w", encoding="utf-8") as f_md:
                    f_md.write(respuesta.text)

                st.success(f"✅ Manual generado exitosamente en: `{ruta_final}`")
                st.markdown("---")
                st.markdown(respuesta.text)

            except Exception as e:
                st.error(f"Error con Ollama: {e}")


# === LÓGICA DE EJECUCIÓN ===
if __name__ == "__main__":
    # Si la variable de entorno NO existe, estamos en modo Lanzador
    if "ERP_PATH_LOCAL" not in os.environ:
        lanzador()
    # Si existe, Streamlit ya está corriendo y mostramos la interfaz
    else:
        interfaz()
