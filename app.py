import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONFIGURACIÓN DINÁMICA (Para que sirva para Jacobo y Luzma) ---
# En vez de una URL fija, usamos la de la empresa seleccionada
def conectar_db():
    try:
        # Usamos la URL que se guardó al iniciar sesión
        return psycopg2.connect(st.session_state.db_url)
    except:
        st.error("❌ No se pudo conectar a la base de datos de esta empresa.")
        return None

def inicializar_db():
    conn = conectar_db()
    if conn:
        cur = conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
        cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                        id SERIAL PRIMARY KEY, 
                        vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                        soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                        p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
        cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "vendedor")')
        # Si es Luzma, creamos su tabla de precios
        if st.session_state.get('modulo_textil', False):
            cur.execute('CREATE TABLE IF NOT EXISTS tarifario_textil (id SERIAL PRIMARY KEY, servicio TEXT UNIQUE, precio_unitario NUMERIC)')
        
        # Aseguramos el admin por defecto
        cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Admin Principal', 'admin', '1234', 'admin') ON CONFLICT (usuario) DO NOTHING")
        conn.commit(); conn.close()

# --- 2. FUNCIONES DE APOYO (Excel) ---
def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance General')
        df_g.to_excel(writer, index=False, sheet_name='Detalle Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Detalle Ventas')
    return output.getvalue()

# --- 3. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="🚐")

# --- 4. SISTEMA DE LOGIN (Multi-Empresa) ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.sidebar.title("🔐 Acceso al Sistema")
    
    # Selector de empresa (Se alimenta de tus Secrets de Streamlit)
    if "connections" in st.secrets:
        empresas = list(st.secrets["connections"].keys())
        empresa_sel = st.sidebar.selectbox("Seleccione Empresa", empresas, 
                                          format_func=lambda x: st.secrets["connections"][x]["nombre"])
        
        u_input = st.sidebar.text_input("Usuario")
        p_input = st.sidebar.text_input("Contraseña", type="password")
        
        if st.sidebar.button("Ingresar"):
            # Guardamos la configuración de la empresa seleccionada
            conf = st.secrets["connections"][empresa_sel]
            st.session_state.db_url = conf["url"]
            st.session_state.modulo_textil = conf.get("modulo_textil", False)
            st.session_state.empresa_nombre = conf["nombre"]
            
            inicializar_db() # Creamos tablas si no existen en esa DB
            
            conn = conectar_db()
            if conn:
                cur = conn.cursor()
                cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (u_input, p_input))
                res = cur.fetchone(); conn.close()
                if res:
                    st.session_state.logged_in = True
                    st.session_state.u_name, st.session_state.u_rol = res[0], res[1]
                    st.rerun()
                else: st.sidebar.error("Usuario o clave incorrectos")
    else:
        st.error("No se han configurado empresas en los 'Secrets' de Streamlit.")
    st.stop()

# --- 5. MENÚ PRINCIPAL ---
st.sidebar.write(f"🏢 **{st.session_state.empresa_nombre}**")
st.sidebar.write(f"👋 Bienvenid@, **{st.session_state.u_name}**")
st.sidebar.divider()

opciones = ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida"]
if st.session_state.modulo_textil: opciones.append("🧵 Tarifas Textil")
if st.session_state.u_rol == "admin": opciones.append("⚙️ Usuarios")

menu = st.sidebar.selectbox("📂 MÓDULOS", opciones)
target = st.sidebar.number_input("🎯 Meta Utilidad ($)", value=5000000, step=500000)

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.logged_in = False; st.rerun()

# --- 6. LÓGICA DE MÓDULOS (TU CÓDIGO PROTEGIDO) ---
conn = conectar_db()

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title(f"📊 Análisis - {st.session_state.empresa_nombre}")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    c1, c2 = st.columns(2)
    with c1:
        placa_f = st.selectbox("Vehículo:", ["TODOS"] + v_data['placa'].tolist())
    with c2:
        rango = st.date_input("Fechas:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])

    if len(rango) == 2:
        q_g = "SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s"
        q_v = "SELECT s.fecha, v.placa, s.valor_viaje as monto FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s"
        params = [rango[0], rango[1]]
        if placa_f != "TODOS":
            q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"; params.append(placa_f)
        
        df_g = pd.read_sql(q_g, conn, params=params)
        df_v = pd.read_sql(q_v, conn, params=params)

        utilidad = df_v['monto'].sum() - df_g['monto'].sum()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Ingresos", f"${df_v['monto'].sum():,.0f}")
        m2.metric("Gastos", f"${df_g['monto'].sum():,.0f}")
        m3.metric("Utilidad", f"${utilidad:,.0f}", delta=f"{utilidad-target:,.0f}")

# --- FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Administración de Vehículos")
    with st.form("form_f"):
        p = st.text_input("Placa").upper()
        m = st.text_input("Marca")
        mod = st.text_input("Modelo")
        cond = st.text_input("Conductor")
        if st.form_submit_button("➕ Añadir Carro"):
            cur = conn.cursor()
            cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, cond))
            conn.commit(); st.success("Vehículo añadido"); st.rerun()
    st.dataframe(pd.read_sql("SELECT placa, marca, modelo, conductor FROM vehiculos", conn), use_container_width=True)

# --- VENTAS (CON CORRECCIÓN DE ERROR) ---
elif menu == "💰 Ventas":
    st.title("💰 Control de Ingresos")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    if v_data.empty:
        st.warning("⚠️ Primero crea vehículos en el módulo Flota.")
    else:
        with st.form("form_v"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            
            # Si es Luzma, mostramos calculador textil
            if st.session_state.modulo_textil:
                st.info("Módulo de Confección Activo")
                tarifas = pd.read_sql("SELECT * FROM tarifario_textil", conn)
                if not tarifas.empty:
                    serv = st.selectbox("Servicio", tarifas['servicio'].tolist())
                    p_u = tarifas[tarifas['servicio'] == serv]['precio_unitario'].values[0]
                    cant = st.number_input(f"Cantidad (Precio/U: ${p_u:,.0f})", min_value=1)
                    monto = cant * p_u
                    det = f"Servicio: {serv} - Cant: {cant}"
                else:
                    st.error("Configura primero las 'Tarifas Textil'")
                    monto = 0; det = ""
            else:
                det = st.text_input("Cliente / Empresa")
                monto = st.number_input("Valor del Viaje", min_value=0)
            
            if st.form_submit_button("💰 Registrar Venta"):
                cur = conn.cursor()
                cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", 
                           (int(v_id), det, monto, datetime.now().date(), "Venta registrada"))
                conn.commit(); st.success("Guardado"); st.rerun()
        
        st.dataframe(pd.read_sql("SELECT * FROM ventas ORDER BY fecha DESC", conn), use_container_width=True)

# --- TARIFAS TEXTIL (Solo para Luzma) ---
elif menu == "🧵 Tarifas Textil":
    st.title("🧵 Tarifario de Confección")
    with st.form("f_t"):
        s = st.text_input("Servicio (Ej: Jeans Lavado)")
        p = st.number_input("Precio por unidad", min_value=0)
        if st.form_submit_button("💾 Guardar Tarifa"):
            cur = conn.cursor()
            cur.execute("INSERT INTO tarifario_textil (servicio, precio_unitario) VALUES (%s,%s) ON CONFLICT (servicio) DO UPDATE SET precio_unitario=EXCLUDED.precio_unitario", (s, p))
            conn.commit(); st.rerun()
    st.table(pd.read_sql("SELECT * FROM tarifario_textil", conn))

# --- HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Documentación")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if not v_data.empty:
        with st.expander("📅 Actualizar Fechas"):
            with st.form("f_hv"):
                v_sel = st.selectbox("Vehículo", v_data['placa'])
                v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
                s_v = st.date_input("SOAT")
                if st.form_submit_button("🔄 Actualizar"):
                    cur = conn.cursor()
                    cur.execute("INSERT INTO hoja_vida (vehiculo_id, soat_vence) VALUES (%s,%s) ON CONFLICT (vehiculo_id) DO UPDATE SET soat_vence=EXCLUDED.soat_vence", (int(v_id), s_v))
                    conn.commit(); st.success("Actualizado"); st.rerun()
    else: st.warning("Crea vehículos primero")

conn.close()
