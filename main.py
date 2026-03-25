import streamlit as st
import os
import faiss
import httpx
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    Settings,
    load_index_from_storage,
)
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.faiss import FaissVectorStore
from llama_index.readers.json import JSONReader

# === 1. CONFIGURACIÓN DE HARDWARE Y MODELOS ===
# Aumentamos el tiempo de espera a 10 minutos (600s) para evitar el error 'ReadTimeout'
TIMEOUT_EXTENDIDO = 600.0

# Nombres exactos de tus modelos en Ollama
MODELO_LLM = "llama3.2-1b-instruct-q4km:latest"
MODELO_EMBED = "all-minilm:latest"  # Modelo ultra-ligero de ~45MB ideal para tu HP 14
D_FAISS = 384  # Dimensión obligatoria para 'all-minilm'

# Configuración global de LlamaIndex
Settings.llm = Ollama(
    model=MODELO_LLM,
    request_timeout=TIMEOUT_EXTENDIDO,
    additional_kwargs={"timeout": TIMEOUT_EXTENDIDO},
)
Settings.embed_model = OllamaEmbedding(model_name=MODELO_EMBED)

# Optimización de fragmentos: trozos más pequeños para que la CPU no se agote
Settings.chunk_size = 256
Settings.chunk_overlap = 20

# === 2. INTERFAZ DE STREAMLIT ===
st.set_page_config(page_title="ERPNext AI Assistant", layout="wide")
st.title("🤖 Asistente de DocTypes y Documentos sobre ERPNext Personalizado")

DATA_DIR = "./data"
PERSIST_DIR = "./storage_faiss"  # Carpeta donde se guardará el índice procesado

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# === 3. BARRA LATERAL: SELECCIÓN E INDEXACIÓN ===
st.sidebar.header("📂 Gestión de Archivos")
archivos_disponibles = [
    f for f in os.listdir(DATA_DIR) if f.endswith((".json", ".pdf", ".md"))
]

# Selector múltiple para que elijas qué analizar
seleccion = st.sidebar.multiselect(
    "Selecciona archivos para el índice:", options=archivos_disponibles
)

if st.sidebar.button("🚀 Indexar / Cargar Base"):
    if seleccion:
        with st.spinner(
            "Procesando documentos... Esto puede tardar unos minutos en CPU."
        ):
            try:
                # Definimos los archivos específicos a leer
                input_files = [os.path.join(DATA_DIR, f) for f in seleccion]

                # Lector especializado para JSON de ERPNext
                json_reader = JSONReader(levels_back=2)
                file_extractor = {".json": json_reader}

                # Cargamos los documentos seleccionados
                documents = SimpleDirectoryReader(
                    input_files=input_files, file_extractor=file_extractor
                ).load_data()

                # Configuramos FAISS (Espacio vectorial local)
                faiss_index = faiss.IndexFlatL2(D_FAISS)
                vector_store = FaissVectorStore(faiss_index=faiss_index)
                storage_context = StorageContext.from_defaults(
                    vector_store=vector_store
                )

                # Creamos el índice (esto consume CPU/RAM)
                index = VectorStoreIndex.from_documents(
                    documents, storage_context=storage_context
                )

                # Guardamos el índice en sesión para no repetirlo
                st.session_state.index = index
                st.sidebar.success(f"¡{len(seleccion)} archivos indexados!")

            except Exception as e:
                st.error(f"Error durante la indexación: {e}")
    else:
        st.sidebar.warning("Selecciona al menos un archivo de la carpeta /data")

# === 4. CHAT PRINCIPAL ===
# Historial de chat para que la interfaz se vea profesional
if "messages" not in st.session_state:
    st.session_state.messages = []

# Mostrar mensajes anteriores
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Entrada del usuario
if prompt := st.chat_input("Ej: ¿Qué campos son obligatorios en este DocType?"):
    if "index" not in st.session_state:
        st.warning("⚠️ Primero selecciona archivos e indexa en la barra lateral.")
    else:
        # Añadir pregunta al historial
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generar respuesta con streaming (efecto máquina de escribir)
        with st.chat_message("assistant"):
            try:
                # similarity_top_k=3 busca los 3 fragmentos más relevantes
                query_engine = st.session_state.index.as_query_engine(
                    streaming=True, similarity_top_k=3
                )

                response = query_engine.query(prompt)
                full_response = st.write_stream(response.response_gen)

                # Guardar respuesta en historial
                st.session_state.messages.append(
                    {"role": "assistant", "content": full_response}
                )

            except Exception as e:
                st.error(f"Ollama tardó demasiado o hubo un error: {e}")
                st.info(
                    "Intenta hacer una pregunta más específica o reduce el número de archivos seleccionados."
                )
