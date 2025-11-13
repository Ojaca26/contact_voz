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

# FUNCIÓN OPTIMIZADA para BIGINT: Limpiar y formatear número de WhatsApp
def limpiar_whatsapp(numero):
    """
    Limpia el número de WhatsApp y lo prepara para BIGINT
    Ahora que la columna es BIGINT, podemos manejar números grandes sin problema
    """
    if not numero:
        return None
    
    # Eliminar todo excepto dígitos
    numero_limpio = re.sub(r'[^\d]', '', str(numero))
    
    if not numero_limpio:
        return None
    
    # Para números colombianos sin código de país
    # Si tiene 10 dígitos y empieza con 3, agregar código 57
    if len(numero_limpio) == 10 and numero_limpio[0] == '3':
        numero_limpio = '57' + numero_limpio
        st.info(f"📱 Número colombiano detectado. Agregando código de país: +57")
    
    # Si el número ya tiene código pero sin el símbolo +
    # Números colombianos con código: 12 dígitos empezando con 57
    elif len(numero_limpio) == 12 and numero_limpio.startswith('57'):
        st.success(f"✓ Número con código de país detectado: +{numero_limpio[:2]}")
    
    # Convertir a entero para BIGINT
    try:
        numero_final = int(numero_limpio)
        
        # Validar que sea un número razonable (no exceder BIGINT límite)
        # BIGINT máximo: 9223372036854775807
        if numero_final > 9223372036854775807:
            st.error(f"❌ Número excede el límite de BIGINT: {numero_final}")
            return None
        
        # Validación adicional para números colombianos
        if str(numero_final).startswith('57'):
            if len(str(numero_final)) != 12:
                st.warning(f"⚠️ Número colombiano con longitud inusual: {len(str(numero_final))} dígitos")
        
        return numero_final
        
    except ValueError as e:
        st.error(f"❌ Error al convertir número: {e}")
        return None

# FUNCIÓN MEJORADA: Guardar en base de datos
def guardar_contacto(datos):
    """Guarda el contacto en la base de datos con columna BIGINT"""
    conexion = conectar_db()
    if not conexion:
        return False
    
    try:
        cursor = conexion.cursor()
        
        # Limpiar el número de WhatsApp
        whatsapp_limpio = limpiar_whatsapp(datos.get('whatsapp'))
        
        # Mostrar información de depuración
        with st.expander("🔍 Información de procesamiento"):
            st.write(f"**Número original:** {datos.get('whatsapp')}")
            st.write(f"**Número procesado:** {whatsapp_limpio}")
            if whatsapp_limpio:
                st.write(f"**Longitud:** {len(str(whatsapp_limpio))} dígitos")
                st.write(f"**Tipo de dato:** BIGINT (soporta hasta 19 dígitos)")
        
        # Insertar en la tabla con columna BIGINT
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
        
        # Obtener el ID del registro insertado para confirmación
        cursor.execute("SELECT LAST_INSERT_ID()")
        last_id = cursor.fetchone()[0]
        
        # Verificar que se insertó correctamente
        cursor.execute(
            "SELECT _Whatsapp FROM contacto_por_voz WHERE _Whatsapp = %s LIMIT 1",
            (whatsapp_limpio,)
        )
        verificacion = cursor.fetchone()
        
        if verificacion:
            st.success(f"✅ Contacto guardado correctamente con WhatsApp: {verificacion[0]}")
        
        cursor.close()
        conexion.close()
        
        return True
    
    except mysql.connector.Error as e:
        st.error(f"❌ Error de base de datos: {e}")
        if conexion:
            conexion.rollback()
            conexion.close()
        return False
    except Exception as e:
        st.error(f"❌ Error inesperado: {e}")
        if conexion:
            conexion.close()
        return False

# FUNCIÓN MEJORADA: Formatear número para mostrar
def formatear_numero_display(numero):
    """Formatea el número de WhatsApp para mostrarlo de manera legible"""
    if not numero:
        return 'N/A'
    
    numero_str = str(numero)
    
    # Número colombiano con código (12 dígitos: 57 + 10)
    if numero_str.startswith('57') and len(numero_str) == 12:
        # Formato: +57 3XX XXX XXXX
        return f"+57 {numero_str[2:5]} {numero_str[5:8]} {numero_str[8:]}"
    
    # Número sin código (10 dígitos)
    elif len(numero_str) == 10:
        # Formato: 3XX XXX XXXX
        return f"{numero_str[:3]} {numero_str[3:6]} {numero_str[6:]}"
    
    # Otros formatos
    else:
        # Agregar + si parece tener código de país
        if len(numero_str) > 10:
            return f"+{numero_str}"
        return numero_str

# FUNCIÓN MEJORADA: Mostrar últimos contactos registrados
def mostrar_ultimos_contactos():
    """Muestra los últimos contactos con formato mejorado para BIGINT"""
    conexion = conectar_db()
    if not conexion:
        return
    
    try:
        cursor = conexion.cursor(dictionary=True)
        
        # Obtener los últimos registros ordenados por WhatsApp descendente
        # Esto funciona bien ahora con BIGINT
        query = """
        SELECT _Whatsapp, Nombre, Empresa, Observacion
        FROM contacto_por_voz
        WHERE _Whatsapp IS NOT NULL
        ORDER BY _Whatsapp DESC
        LIMIT 5
        """
        cursor.execute(query)
        resultados = cursor.fetchall()
        
        if resultados:
            st.subheader("📋 Últimos contactos registrados")
            
            # Crear tabla con información formateada
            for idx, contacto in enumerate(resultados, 1):
                whatsapp_formateado = formatear_numero_display(contacto['_Whatsapp'])
                
                with st.expander(
                    f"#{idx} • {contacto['Nombre'] or 'Sin nombre'} - "
                    f"{contacto['Empresa'] or 'Sin empresa'} • "
                    f"{whatsapp_formateado}"
                ):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**📱 WhatsApp:** {whatsapp_formateado}")
                        # Mostrar número sin formato también
                        st.caption(f"Número en BD: {contacto['_Whatsapp']}")
                        st.write(f"**👤 Nombre:** {contacto['Nombre'] or 'N/A'}")
                    with col2:
                        st.write(f"**🏢 Empresa:** {contacto['Empresa'] or 'N/A'}")
                        st.write(f"**📝 Observación:** {contacto['Observacion'] or 'Sin observaciones'}")
        else:
            st.info("📭 No hay contactos registrados aún")
        
        cursor.close()
        conexion.close()
    
    except Exception as e:
        st.error(f"Error al cargar contactos: {e}")
        if conexion:
            conexion.close()

# Función para verificar estadísticas de la BD
def mostrar_estadisticas():
    """Muestra estadísticas de los contactos en la BD"""
    conexion = conectar_db()
    if not conexion:
        return
    
    try:
        cursor = conexion.cursor(dictionary=True)
        
        # Obtener estadísticas
        query = """
        SELECT 
            COUNT(*) as total_contactos,
            COUNT(_Whatsapp) as con_whatsapp,
            COUNT(DISTINCT Empresa) as empresas_unicas,
            MIN(_Whatsapp) as whatsapp_min,
            MAX(_Whatsapp) as whatsapp_max
        FROM contacto_por_voz
        """
        cursor.execute(query)
        stats = cursor.fetchone()
        
        if stats['total_contactos'] > 0:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Contactos", stats['total_contactos'])
            with col2:
                st.metric("Con WhatsApp", stats['con_whatsapp'])
            with col3:
                st.metric("Empresas Únicas", stats['empresas_unicas'] or 0)
        
        cursor.close()
        conexion.close()
        
    except Exception as e:
        st.error(f"Error al cargar estadísticas: {e}")
        if conexion:
            conexion.close()

# Interfaz principal
def main():
    # Configurar Gemini
    modelo = configurar_gemini()
    
    # Inicializar session state
    if 'datos_extraidos' not in st.session_state:
        st.session_state.datos_extraidos = None
    if 'mensaje_procesado' not in st.session_state:
        st.session_state.mensaje_procesado = False
    
    # Mostrar estadísticas
    mostrar_estadisticas()
    
    st.markdown("---")
    
    # Crear dos columnas
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("💬 Ingresa el mensaje")
        st.info("📝 Escribe o pega el texto con la información del contacto")
        
        # Área de texto para el mensaje
        mensaje = st.text_area(
            "Mensaje:",
            height=120,
            placeholder="Ejemplo: Registrar a Juan Pérez, su WhatsApp es 300 123 4567, trabaja en Tecnología XYZ como gerente de ventas.",
            key="mensaje_input"
        )
        
        # Botón para procesar
        if st.button("🚀 Procesar y Extraer Datos", type="primary", use_container_width=True):
            if mensaje.strip():
                with st.spinner("🤖 Analizando con IA..."):
                    datos = extraer_datos_contacto(mensaje, modelo)
                    
                    if datos:
                        st.session_state.datos_extraidos = datos
                        st.session_state.mensaje_procesado = True
                        st.rerun()
            else:
                st.warning("⚠️ Por favor, ingresa un mensaje")
        
        # Mostrar datos extraídos si existen
        if st.session_state.mensaje_procesado and st.session_state.datos_extraidos:
            st.markdown("---")
            st.success("✅ **Datos extraídos correctamente**")
            
            datos = st.session_state.datos_extraidos
            
            # Mostrar preview del número procesado
            numero_preview = limpiar_whatsapp(datos.get('whatsapp'))
            
            # Crear cards con los datos
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("##### 📱 WhatsApp")
                if datos.get('whatsapp'):
                    st.write(f"Original: `{datos.get('whatsapp')}`")
                    if numero_preview:
                        st.write(f"Formateado: **{formatear_numero_display(numero_preview)}**")
                else:
                    st.write("❌ No detectado")
                
                st.markdown("##### 👤 Nombre")
                st.write(datos.get('nombre') or '❌ No detectado')
            
            with col_b:
                st.markdown("##### 🏢 Empresa")
                st.write(datos.get('empresa') or '❌ No detectado')
                
                st.markdown("##### 📝 Observación")
                st.write(datos.get('observacion') or '❌ No detectado')
            
            st.markdown("---")
            
            # Botones de acción
            col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 1])
            with col_btn1:
                if st.button("💾 **Guardar en Base de Datos**", type="primary", use_container_width=True):
                    with st.spinner("Guardando..."):
                        if guardar_contacto(datos):
                            st.balloons()
                            # Limpiar session state
                            st.session_state.datos_extraidos = None
                            st.session_state.mensaje_procesado = False
                            # Recargar
                            import time
                            time.sleep(1.5)
                            st.rerun()
                        else:
                            st.error("❌ Error al guardar. Revisa los mensajes arriba.")
            
            with col_btn2:
                if st.button("✏️ Editar Datos", type="secondary", use_container_width=True):
                    st.info("🚧 Función en desarrollo")
            
            with col_btn3:
                if st.button("🔄 Cancelar", use_container_width=True):
                    st.session_state.datos_extraidos = None
                    st.session_state.mensaje_procesado = False
                    st.rerun()
    
    with col2:
        st.subheader("ℹ️ Guía de uso")
        
        with st.expander("📝 Ejemplos de mensajes", expanded=True):
            st.markdown("""
            **Formato libre:**
            - *"María López, 3001234567, Soluciones ABC"*
            - *"Contacto: Carlos Ruiz de Tech SA, cel +57 310 9876543"*
            - *"Ana Torres 320-999-8877, Global Services, reunión viernes"*
            
            **Con detalles:**
            - *"Registrar a Juan Pérez, WhatsApp 315 888 9999, empresa XYZ, es el gerente de ventas"*
            """)
        
        with st.expander("🔢 Formatos de números"):
            st.markdown("""
            **Aceptados:**
            - `3001234567` → Se agrega +57
            - `+57 300 123 4567` → Con código
            - `300-123-4567` → Con guiones
            - `573001234567` → Código sin +
            
            **Base de datos:**
            - Columna: `BIGINT(20)`
            - Soporta hasta 19 dígitos
            - Guarda números completos
            """)
        
        with st.expander("💡 Tips"):
            st.markdown("""
            - La IA detecta los datos en cualquier orden
            - No importa el formato del número
            - Se agrega código +57 automáticamente
            - Campos opcionales si no están presentes
            """)
    
    # Separador
    st.markdown("---")
    
    # Mostrar últimos contactos
    mostrar_ultimos_contactos()
    
    # Footer con información técnica
    with st.expander("🔧 Información técnica"):
        col_tech1, col_tech2 = st.columns(2)
        with col_tech1:
            st.markdown("""
            **Base de datos:**
            - Tabla: `contacto_por_voz`
            - Motor: MariaDB
            - Columna WhatsApp: `BIGINT(20)`
            """)
        with col_tech2:
            st.markdown("""
            **Límites numéricos:**
            - BIGINT máx: 9,223,372,036,854,775,807
            - Soporta todos los números telefónicos
            - Incluye códigos internacionales
            """)

if __name__ == "__main__":
    main()
