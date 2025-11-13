import streamlit as st
import google.generativeai as genai
import json
import re
import mysql.connector
from datetime import datetime
import os

# --- NUEVO ---
from audiorecorder import audiorecorder
# --------------
# Recuerda agregar en requirements.txt:
# streamlit
# google-generativeai
# mysql-connector-python
# streamlit-audiorecorder


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

st.set_page_config(
    page_title="Registro de Contactos por Voz",
    page_icon="📞",
    layout="wide"
)

st.title("📞 Registro de Contactos por Voz")
st.markdown("Habla y la IA extraerá WhatsApp, Nombre, Empresa y Observación")

# ============================================================
# CONFIGURACIÓN GEMINI
# ============================================================

def configurar_gemini():
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        st.error("⚠️ No se encontró GEMINI_API_KEY en secrets")
        st.stop()
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")


# ============================================================
# CONEXIÓN A BASE DE DATOS
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
        st.error(f"❌ Error al conectar BD: {e}")
        return None


# ============================================================
# TRANSCRIPCIÓN DE AUDIO DIRECTO (GRABACIÓN)
# ============================================================

def transcribir_audio(audio_bytes, modelo):
    try:
        st.info("🎧 Transcribiendo audio...")

        response = modelo.generate_content([
            {
                "mime_type": "audio/wav",
                "data": audio_bytes
            },
            "Transcribe este audio exactamente como se escucha y devuelve solo texto."
        ])

        return response.text.strip()

    except Exception as e:
        st.error(f"❌ Error al transcribir: {e}")
        return None


# ============================================================
# EXTRACCIÓN DE LOS 4 DATOS
# ============================================================

def extraer_datos_contacto(texto, modelo):

    prompt = f"""
Extrae EXACTAMENTE estos 4 datos del texto dado:

1. whatsapp
2. nombre
3. empresa
4. observacion

TEXTO: "{texto}"

Entrega SOLO este JSON:

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
        st.error(f"❌ Error procesando IA: {e}")
        return None


# ============================================================
# LIMPIAR NÚMERO WHATSAPP
# ============================================================

def limpiar_whatsapp(numero):
    if not numero:
        return None

    num = re.sub(r"[^\d]", "", str(numero))

    if len(num) == 10 and num.startswith("3"):
        num = "57" + num

    try:
        return int(num)
    except:
        return None


# ============================================================
# GUARDAR EN BD
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
            for c in rows:
                st.write(
                    f"📱 **{c['_Whatsapp']}** • 👤 {c['Nombre']} • 🏢 {c['Empresa']} • 📝 {c['Observacion']}"
                )
        else:
            st.info("Aún no hay registros")

    except:
        pass


# ============================================================
# GRABADOR DE AUDIO (BOTÓN DE GRABAR / DETENER)
# ============================================================

def grabador():
    st.subheader("🎙️ Hablar para registrar contacto")

    audio = audiorecorder("🎤 Presiona para hablar", "⏹️ Presiona para detener")

    if len(audio) > 0:
        st.audio(audio.tobytes())
        return audio.tobytes()

    return None


# ============================================================
# INTERFAZ PRINCIPAL
# ============================================================

def main():

    modelo = configurar_gemini()

    if "datos_extraidos" not in st.session_state:
        st.session_state.datos_extraidos = None

    col1, col2 = st.columns([2, 1])

    # ---------------------
    # COLUMNA IZQUIERDA
    # ---------------------
    with col1:

        st.subheader("🎤 Entrada por Voz")

        audio_bytes = grabador()

        if audio_bytes and st.button("🚀 Transcribir y procesar", use_container_width=True):
            texto = transcribir_audio(audio_bytes, modelo)

            if texto:
                st.success("📝 Transcripción completada")
                st.text_area("Texto transcrito", texto, height=120)

                datos = extraer_datos_contacto(texto, modelo)
                st.session_state.datos_extraidos = datos

        st.markdown("---")
        st.subheader("💬 Entrada por Texto")

        mensaje = st.text_area("Mensaje manual:")

        if st.button("📥 Procesar Texto", use_container_width=True):
            if mensaje.strip():
                datos = extraer_datos_contacto(mensaje, modelo)
                st.session_state.datos_extraidos = datos
            else:
                st.warning("Ingrese texto por favor")

        if st.session_state.datos_extraidos:
            st.markdown("---")
            st.success("Datos extraídos:")

            datos = st.session_state.datos_extraidos
            st.json(datos)

            if st.button("💾 Guardar en BD", type="primary", use_container_width=True):
                if guardar_contacto(datos):
                    st.success("Registro guardado correctamente 🎉")
                    st.balloons()
                    st.session_state.datos_extraidos = None
                    st.rerun()

    # ---------------------
    # COLUMNA DERECHA
    # ---------------------
    with col2:
        st.subheader("ℹ️ Guía")
        st.write("- Presiona para grabar y detener")
        st.write("- La IA extrae los datos automáticamente")
        st.write("- Puedes editar antes de guardar")
        st.markdown("---")
        mostrar_ultimos_contactos()


if __name__ == "__main__":
    main()
