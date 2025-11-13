import streamlit as st
import google.generativeai as genai
import json
import re
import mysql.connector
from datetime import datetime
import os

# Configuración de la página
st.set_page_config(
    page_title="Registro de Contactos por Voz",
    page_icon="📞",
    layout="wide"
)

# Título de la aplicación
st.title("📞 Registro de Contactos por Voz")
st.markdown("Habla naturalmente y la IA extraerá: WhatsApp, Nombre, Empresa y Observación")

# Configurar Gemini API
def configurar_gemini():
    """Configura la API de Gemini"""
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        st.error("⚠️ No se encontró GEMINI_API_KEY en secrets")
        st.stop()
    genai.configure(api_key=api_key)
    # Usar el modelo actualizado de Gemini
    return genai.GenerativeModel('gemini-2.5-flash')

# Conectar a la base de datos
def conectar_db():
    """Conecta a la base de datos MySQL/MariaDB"""
    try:
        conexion = mysql.connector.connect(
            host=st.secrets["DB_HOST"],
            user=st.secrets["DB_USER"],
            password=st.secrets["DB_PASSWORD"],
            database=st.secrets.get("DB_NAME", "lbusiness"),
            port=st.secrets.get("DB_PORT", 3306),
            charset='utf8mb4',
            collation='utf8mb4_unicode_ci'
        )
        return conexion
    except Exception as e:
        st.error(f"❌ Error al conectar a la base de datos: {e}")
        st.error(f"Host: {st.secrets['DB_HOST']}, Puerto: {st.secrets.get('DB_PORT', 3306)}, Base de datos: {st.secrets.get('DB_NAME', 'lbusiness')}")
        return None

# Extraer información usando Gemini
def extraer_datos_contacto(texto, modelo):
    """Usa Gemini para extraer los 4 datos del texto"""
    
    prompt = f"""
Analiza el siguiente texto y extrae EXACTAMENTE estos 4 datos:
1. WhatsApp: número de teléfono (puede incluir código de país)
2. Nombre: nombre completo del contacto
3. Empresa: nombre de la empresa u organización
4. Observacion: cualquier información adicional relevante

TEXTO: "{texto}"

INSTRUCCIONES IMPORTANTES:
- Si un dato NO está presente, usa null
- El número de WhatsApp puede estar en formato: +57 300 1234567, 3001234567, etc.
- Busca el nombre de la persona (puede estar como "se llama", "su nombre es", "contacto:", etc.)
- La empresa puede mencionarse como "trabaja en", "de la empresa", "compañía", etc.
- Observación es cualquier dato extra: cargo, motivo del contacto, proyecto, etc.

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{{
    "whatsapp": "número o null",
    "nombre": "nombre o null", 
    "empresa": "empresa o null",
    "observacion": "observación o null"
}}

No incluyas explicaciones adicionales, solo el JSON.
"""
    
    try:
        response = modelo.generate_content(prompt)
        texto_respuesta = response.text.strip()
        
        # Limpiar markdown si existe
        texto_respuesta = texto_respuesta.replace("```json", "").replace("```", "").strip()
        
        # Parsear JSON
        datos = json.loads(texto_respuesta)
        
        # Convertir "null" string a None
        for key in datos:
            if datos[key] == "null" or datos[key] == "":
                datos[key] = None
        
        return datos
    
    except json.JSONDecodeError as e:
        st.error(f"Error al parsear respuesta de IA: {e}")
        st.code(texto_respuesta)
        return None
    except Exception as e:
        st.error(f"Error al procesar con Gemini: {e}")
        return None

# Limpiar número de WhatsApp
def limpiar_whatsapp(numero):
    """Limpia el número de WhatsApp dejando solo dígitos"""
    if not numero:
        return None
    # Eliminar todo excepto dígitos
    numero_limpio = re.sub(r'[^\d]', '', numero)
    # Convertir a entero (la columna _Whatsapp es INT)
    try:
        return int(numero_limpio) if numero_limpio else None
    except:
        return None

# Guardar en base de datos
def guardar_contacto(datos):
    """Guarda el contacto en la base de datos"""
    conexion = conectar_db()
    if not conexion:
        return False
    
    try:
        cursor = conexion.cursor()
        
        # Limpiar el número de WhatsApp (solo números, como INT)
        whatsapp_limpio = limpiar_whatsapp(datos.get('whatsapp'))
        
        # IMPORTANTE: La tabla tiene estas columnas: _Whatsapp, Nombre, Empresa, Observacion
        query = """
        INSERT INTO contacto_por_voz (_Whatsapp, Nombre, Empresa, Observacion)
        VALUES (%s, %s, %s, %s)
        """
        
        valores = (
            whatsapp_limpio,
            datos.get('nombre'),
            datos.get('empresa'),
            datos.get('observacion')
        )
        
        cursor.execute(query, valores)
        conexion.commit()
        
        cursor.close()
        conexion.close()
        
        return True
    
    except Exception as e:
        st.error(f"❌ Error al guardar en base de datos: {e}")
        if conexion:
            conexion.close()
        return False

# Mostrar últimos contactos registrados
def mostrar_ultimos_contactos():
    """Muestra los últimos 5 contactos registrados"""
    conexion = conectar_db()
    if not conexion:
        return
    
    try:
        cursor = conexion.cursor(dictionary=True)
        # IMPORTANTE: La tabla tiene: _Whatsapp, Nombre, Empresa, Observacion (sin fecha_registro)
        query = """
        SELECT _Whatsapp, Nombre, Empresa, Observacion
        FROM contacto_por_voz
        LIMIT 5
        """
        cursor.execute(query)
        resultados = cursor.fetchall()
        
        if resultados:
            st.subheader("📋 Últimos contactos registrados")
            for contacto in resultados:
                with st.expander(f"🔹 {contacto['Nombre'] or 'Sin nombre'} - {contacto['Empresa'] or 'Sin empresa'}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**WhatsApp:** {contacto['_Whatsapp'] or 'N/A'}")
                        st.write(f"**Nombre:** {contacto['Nombre'] or 'N/A'}")
                    with col2:
                        st.write(f"**Empresa:** {contacto['Empresa'] or 'N/A'}")
                    st.write(f"**Observación:** {contacto['Observacion'] or 'Sin observaciones'}")
        
        cursor.close()
        conexion.close()
    
    except Exception as e:
        st.error(f"Error al cargar contactos: {e}")
        if conexion:
            conexion.close()

# Interfaz principal
def main():
    # Configurar Gemini
    modelo = configurar_gemini()
    
    # Inicializar session state para guardar datos extraídos
    if 'datos_extraidos' not in st.session_state:
        st.session_state.datos_extraidos = None
    if 'mensaje_procesado' not in st.session_state:
        st.session_state.mensaje_procesado = False
    
    # Crear dos columnas
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("💬 Ingresa el mensaje")
        st.info("Puedes escribir o pegar el texto transcrito de tu mensaje de voz")
        
        # Área de texto para el mensaje
        mensaje = st.text_area(
            "Escribe aquí el mensaje:",
            height=150,
            placeholder="Ejemplo: Hola, quiero registrar a Juan Pérez, su WhatsApp es +57 300 1234567, trabaja en Tecnología XYZ como gerente de ventas. Es un contacto del proyecto nuevo."
        )
        
        # Botón para procesar
        if st.button("🚀 Procesar y Extraer Datos", type="primary", use_container_width=True):
            if mensaje.strip():
                with st.spinner("🤖 Analizando mensaje con IA..."):
                    # Extraer datos
                    datos = extraer_datos_contacto(mensaje, modelo)
                    
                    if datos:
                        st.session_state.datos_extraidos = datos
                        st.session_state.mensaje_procesado = True
                        st.rerun()
            else:
                st.warning("⚠️ Por favor, ingresa un mensaje")
        
        # Mostrar datos extraídos si existen
        if st.session_state.mensaje_procesado and st.session_state.datos_extraidos:
            st.success("✅ Datos extraídos correctamente")
            
            datos = st.session_state.datos_extraidos
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**📱 WhatsApp:**", datos.get('whatsapp') or '❌ No detectado')
                st.write("**👤 Nombre:**", datos.get('nombre') or '❌ No detectado')
            with col_b:
                st.write("**🏢 Empresa:**", datos.get('empresa') or '❌ No detectado')
                st.write("**📝 Observación:**", datos.get('observacion') or '❌ No detectado')
            
            st.markdown("---")
            
            # Botones para guardar o cancelar
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("💾 Guardar en Base de Datos", type="primary", use_container_width=True):
                    with st.spinner("Guardando..."):
                        if guardar_contacto(datos):
                            st.success("🎉 ¡Contacto guardado exitosamente!")
                            st.balloons()
                            # Limpiar session state
                            st.session_state.datos_extraidos = None
                            st.session_state.mensaje_procesado = False
                            # Esperar un poco antes de recargar
                            import time
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("❌ No se pudo guardar el contacto. Revisa la conexión a la BD.")
            
            with col_btn2:
                if st.button("🔄 Nuevo Registro", type="secondary", use_container_width=True):
                    # Limpiar session state
                    st.session_state.datos_extraidos = None
                    st.session_state.mensaje_procesado = False
                    st.rerun()
    
    with col2:
        st.subheader("ℹ️ Ayuda")
        st.markdown("""
        **Ejemplos de mensajes:**
        
        📝 *"Registrar a María López, WhatsApp 3001234567, empresa Soluciones ABC, es la directora de marketing"*
        
        📝 *"Nuevo contacto: +57 310 9876543, se llama Carlos Ruiz de Innovación Tech, interesado en el proyecto"*
        
        📝 *"Ana Torres, trabaja en Global Services, su número es +573209998877, contacto para la reunión del viernes"*
        
        ---
        
        **La IA puede identificar los datos aunque:**
        - No estén en orden
        - Falte algún campo
        - Use lenguaje natural
        """)
    
    # Separador
    st.markdown("---")
    
    # Mostrar últimos contactos
    mostrar_ultimos_contactos()

if __name__ == "__main__":
    main()
