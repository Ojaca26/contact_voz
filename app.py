
import streamlit as st
import google.generativeai as genai
import json
import re
import mysql.connector
from datetime import datetime
import os
import base64

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

st.set_page_config(
    page_title="Registro de Contactos por Voz",
    page_icon="📞",
    layout="wide"
)

st.title("📞 Registro de Contactos por Voz")
st.markdown("Habla naturalmente y la IA extraerá: WhatsApp, Nombre, Empresa y Observación")

# ============================================================
# CONFIGURAR GEMINI
# ============================================================

def configurar_gemini():
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        st.error("⚠️ No se encontró GEMINI_API_KEY en secrets")
        st.stop()
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")

# ============================================================
# CONEXIÓN BD
# ============================================================

def conectar_db():
    try:
        return mysql.connector.connect(
            host=st.secrets["DB_HOST"],
            user=st.secrets["DB_USER"],
            password=st.secrets["DB_PASSWORD"],
            database=st.secrets.get("DB_NAME", "lbusiness"),
            port=st.secrets.get("DB_PORT", 3306),
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci"
        )
    except Exception as e:
        st.error(f"❌ Error al conectar a la base de datos: {e}")
        return None

# ============================================================
# TRANSCRIBIR AUDIO (NUEVA FUNCIÓN)
# ============================================================

def transcribir_audio(audio_file, modelo):
    """Envía el archivo de audio a Gemini y devuelve el texto transcrito."""
    try:
        bytes_data = audio_file.read()

        extension = audio_file.name.split(".")[-1].lower()
        mime_map = {
            "wav": "audio/wav",
            "mp3": "audio/mpeg",
            "m4a": "audio/mp4",
            "webm": "audio/webm",
            "ogg": "audio/ogg"
        }
        mime_type = mime_map.get(extension, "audio/mpeg")

        st.info("🎧 Transcribiendo audio con Gemini...")

        response = modelo.generate_content([
            {
                "mime_type": mime_type,
                "data": bytes_data
            },
            "Transcribe este audio en español y solo devuelve el texto sin nada más."
        ])

        return response.text.strip()

    except Exception as e:
        st.error(f"❌ Error al transcribir: {e}")
        return None

# ============================================================
# EXTRAER LOS 4 DATOS DEL TEXTO
# ============================================================

def extraer_datos_contacto(texto, modelo):

    prompt = f"""
Analiza el siguiente texto y extrae EXACTAMENTE estos 4 datos:
1. WhatsApp
2. Nombre
3. Empresa
4. Observacion

TEXTO: "{texto}"

Responde SOLO con JSON:
{{
    "whatsapp": "número o null",
    "nombre": "nombre o null", 
    "empresa": "empresa o null",
    "observacion": "observación o null"
}}
"""

    try:
        res = modelo.generate_content(prompt)
        txt = res.text.strip().replace("```json", "").replace("```", "")
        datos = json.loads(txt)

        for k in datos:
            if datos[k] in ["", "null"]:
                datos[k] = None

        return datos

    except Exception as e:
        st.error(f"❌ Error al procesar con Gemini: {e}")
        return None

# ============================================================
# LIMPIAR WHATSAPP
# ============================================================

def limpiar_whatsapp(numero):
    if not numero:
        return None
    num = re.sub(r"[^\d]", "", str(numero))
    if len(num) == 10 and num.startswith("3"):
        num = "57" + num
        st.info("📱 Número colombiano detectado (+57 agregado)")
    try:
        return int(num)
    except:
        return None

# ============================================================
# GUARDAR BD
# ============================================================

def guardar_contacto(datos):
    con = conectar_db()
    if not con:
        return False
    try:
        cur = con.cursor()
        whatsapp = limpiar_whatsapp(datos.get("whatsapp"))

        cur.execute("""
            INSERT INTO contacto_por_voz (_Whatsapp, Nombre, Empresa, Observacion)
            VALUES (%s, %s, %s, %s)
        """, (whatsapp, datos.get("nombre"), datos.get("empresa"), datos.get("observacion")))

        con.commit()
        cur.close()
        con.close()
        return True

    except Exception as e:
        st.error(f"❌ Error BD: {e}")
        return False

# ============================================================
# MOSTRAR ÚLTIMOS CONTACTOS
# ============================================================

def mostrar_ultimos_contactos():
    con = conectar_db()
    if not con:
        return
    try:
        cur = con.cursor(dictionary=True)
        cur.execute("""
            SELECT _Whatsapp, Nombre, Empresa, Observacion
            FROM contacto_por_voz
            ORDER BY _Whatsapp DESC
            LIMIT 5
        """)
        rows = cur.fetchall()
        cur.close()
        con.close()

        if rows:
            st.subheader("📋 Últimos contactos")
            for r in rows:
                st.write(f"**{r['Nombre']} - {r['Empresa']} - {r['_Whatsapp']}**")
        else:
            st.info("Sin registros aún.")

    except:
        pass

# ============================================================
# INTERFAZ PRINCIPAL
# ============================================================

def main():

    modelo = configurar_gemini()

    if "datos_extraidos" not in st.session_state:
        st.session_state.datos_extraidos = None

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("🎙️ Ingreso por Voz")

        audio_file = st.file_uploader("Sube un audio (m4a, mp3, wav, ogg, webm)", type=["mp3","m4a","wav","ogg","webm"])

        if audio_file:
            st.audio(audio_file)

            if st.button("🎧 Transcribir Audio", type="primary", use_container_width=True):
                texto = transcribir_audio(audio_file, modelo)
                if texto:
                    st.success("📝 Transcripción completada")
                    st.text_area("Texto transcrito", texto, height=120, key="transcripcion")
                    datos = extraer_datos_contacto(texto, modelo)
                    if datos:
                        st.session_state.datos_extraidos = datos
                        st.success("Datos extraídos con éxito")

        st.markdown("---")
        st.subheader("💬 Ingreso por Texto")

        mensaje = st.text_area("Mensaje manual", placeholder="Escribe o pega texto aquí...")

        if st.button("🚀 Procesar Texto", type="primary", use_container_width=True):
            if mensaje.strip():
                datos = extraer_datos_contacto(mensaje, modelo)
                st.session_state.datos_extraidos = datos
            else:
                st.warning("Ingresa texto primero.")

        if st.session_state.datos_extraidos:
            st.markdown("---")
            st.success("Datos extraídos:")

            datos = st.session_state.datos_extraidos

            st.json(datos)

            if st.button("💾 Guardar en BD", type="primary", use_container_width=True):
                if guardar_contacto(datos):
                    st.balloons()
                    st.success("Contacto guardado correctamente")
                    st.session_state.datos_extraidos = None
                    st.rerun()

    with col2:
        st.subheader("ℹ️ Guía de uso")
        st.write("- Sube un audio o escribe un texto.")
        st.write("- Se detecta WhatsApp, Nombre, Empresa y Observación automáticamente.")
        st.write("- Guarda en la BD con un clic.")
        st.markdown("---")
        mostrar_ultimos_contactos()

if __name__ == "__main__":
    main()
