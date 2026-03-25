# 🤖 ERPNext AI Assistant (Local RAG)

Este es un asistente inteligente basado en **RAG (Retrieval-Augmented Generation)** diseñado para consultar documentación técnica de ERPNext, DocTypes y archivos personalizados (JSON, PDF, Markdown) de forma 100% local.

Utiliza **LlamaIndex** para la orquestación, **FAISS** como base de datos vectorial y **Ollama** para ejecutar los modelos de lenguaje y embeddings sin salir de tu máquina.

## ✨ Características

* **Privacidad Total:** Todo se ejecuta localmente a través de Ollama.
* **Optimizado para CPU:** Configurado con fragmentos de texto (chunks) pequeños para funcionar fluidamente en equipos con recursos limitados (como laptops de 14").
* **Soporte Multiformato:** Lector especializado para archivos `.json` de ERPNext, además de `.pdf` y `.md`.
* **Interfaz Interactiva:** Construido con Streamlit para una experiencia de chat moderna y con streaming de respuestas.

## 🛠️ Requisitos Previos

1.  **Ollama instalado:** Descárgalo en [ollama.com](https://ollama.com).
2.  **Modelos necesarios:** Descarga los modelos que usa el script ejecutando en tu terminal:
    ```bash
    ollama pull llama3.2-1b-instruct-q4km:latest
    ollama pull all-minilm:latest
    ```

## 🚀 Instalación y Uso

Este proyecto utiliza `uv` para una gestión de dependencias ultrarrápida.

1.  **Clonar el repositorio:**
    ```bash
    git clone [https://github.com/TU_USUARIO/rag_project.git](https://github.com/TU_USUARIO/rag_project.git)
    cd rag_project
    ```

2.  **Sincronizar el entorno e instalar dependencias:**
    ```bash
    uv sync
    ```

3.  **Preparar tus datos:**
    Coloca tus archivos `.pdf`, `.json` o `.md` dentro de la carpeta `/data`.

4.  **Ejecutar la aplicación:**
    ```bash
    streamlit run main.py
    ```

## ⚙️ Configuración Técnica

* **LLM:** Llama 3.2 (1B) - Elegido por su bajo consumo de memoria.
* **Embeddings:** `all-minilm` (Dimensión 384) - Modelo ligero de ~45MB.
* **Vector Store:** FAISS (IndexFlatL2).
* **Chunk Size:** 256 tokens con un solapamiento de 20 para mantener el contexto en CPUs modestas.

---
Desarrollado usando LlamaIndex, Streamlit y Ollama.