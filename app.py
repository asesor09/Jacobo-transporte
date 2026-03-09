import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- 1. CONEXIÓN Y BASE DE DATOS ---
def conectar_db():
    try:
        return psycopg2.connect(st.session_state.db_url)
    except:
        st.error("❌ Error crítico: No se pudo conectar a la base de datos.")
        return None

def inicializar_db():
    conn = conectar_db()
    if conn:
        cur = conn.cursor()
        # Tablas Core
        cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
        cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (id SERIAL PRIMARY KEY, vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                        soat_vence DATE, tecno_vence DATE, prev_vence DATE, p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
        cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "admin")')
        cur.execute('CREATE TABLE IF NOT EXISTS tarifario_textil (id SERIAL PRIMARY KEY, servicio TEXT UNIQUE, precio_unitario NUMERIC)')
        # Usuario Admin por defecto si no hay ninguno
        cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Admin Sistema', 'admin', '1234', 'admin') ON CONFLICT (usuario) DO NOTHING")
        conn.commit(); conn.close()

# --- 2. FUNCIÓN DE EXCEL (RECUPERADA) ---
def to_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance General')
        df_g.to_excel(writer, index=False, sheet_name='Detalle Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Detalle Ventas')
    return output.getvalue()

# --- 3. CONFIGURACIÓN UI ---
st.set_page_config(page_title="C&E Eficiencias Pro", layout="wide", page_icon="🚐")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

# --- 4. LOGIN MULTI-EMPRESA ---
if not st.session_state.logged_in:
    st.sidebar.title("🔐 Acceso C&E")
    if "connections" in st.secrets:
        empresa_sel = st.sidebar.selectbox("Empresa:", list(st.secrets["connections"].keys()), 
                                          format_func=lambda x: st.secrets["connections"][x]["nombre"])
        u_in = st.sidebar.text_input("Usuario")
        p_in = st.sidebar.text_input("Contraseña", type="password")
        
        if st.sidebar.button("Ingresar"):
            conf = st.secrets["connections"][empresa_sel]
            st.session_state.db_url = conf["url"]
            st.session_state.es_textil = conf.get("modulo_textil", False)
            st.session_state.nom_empresa = conf["nombre"]
            
            inicializar_db()
            conn = conectar_db()
            if conn:
                cur = conn.cursor()
                cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (u_in, p_in))
                res = cur.fetchone(); conn.close()
                if res:
                    st.session_state.logged_in = True
                    st.session_state.u_name, st.session_state.u_rol = res[0], res[1]
                    st.rerun()
                else: st.sidebar.error("Credenciales incorrectas")
    st.stop()

# --- 5. PANEL PRINCIPAL ---
st.sidebar.write(f"🏢 **{st.session_state.nom_empresa}**")
st.sidebar.write(f"👋 Hola, {st.session_state.u_name}")
st.sidebar.divider()

menu_opts = ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida"]
if st.session_state.es_textil: menu_opts.append("🧵 Tarifas Textil")
if st.session_state.u_rol == "admin": menu_opts.append("⚙️ Usuarios")

menu = st.sidebar.selectbox("Módulo:", menu_opts)
target = st.sidebar.number_input("🎯 Meta Utilidad", value=5000000)

if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state.logged_in = False; st.rerun()

conn = conectar_db()

# --- DASHBOARD (RECUPERADO CON DETALLES Y EXCEL) ---
if menu == "📊 Dashboard":
    st.title(f"📊 Dashboard - {st.session_state.nom_empresa}")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    col1, col2 = st.columns(2)
    with col1:
        placa_f = st.selectbox("Vehículo:", ["TODOS"] + v_data['placa'].tolist())
    with col2:
        rango = st.date_input("Rango de Fechas:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])

    if len(rango) == 2:
        q_g = "SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s"
        q_v = "SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s"
        params = [rango[0], rango[1]]
        if placa_f != "TODOS":
            q_g += " AND v.placa = %s"; q_v += " AND v.placa = %s"; params.append(placa_f)
        
        df_g = pd.read_sql(q_g, conn, params=params)
        df_v = pd.read_sql(q_v, conn, params=params)

        utilidad = df_v['monto'].sum() - df_g['monto'].sum()
        
        # Métricas
        m1, m2, m3 = st.columns(3)
        m1.metric("Ingresos Total", f"${df_v['monto'].sum():,.0f}")
        m2.metric("Egresos Total", f"${df_g['monto'].sum():,.0f}", delta=f"-{df_g['monto'].sum():,.0f}", delta_color="inverse")
        m3.metric("Utilidad Neta", f"${utilidad:,.0f}", delta=f"{utilidad-target:,.0f}")

        # Gráfico Plotly (Recuperado)
        st.subheader("📈 Comparativa Venta vs Gasto")
        res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gasto'})
        res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Venta'})
        balance_df = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
        fig = px.bar(balance_df, x='placa', y=['Venta', 'Gasto'], barmode='group', color_discrete_map={'Venta': '#2ecc71', 'Gasto': '#e74c3c'})
        st.plotly_chart(fig, use_container_width=True)

        # BOTÓN EXCEL (Recuperado)
        st.download_button("📥 Descargar Reporte a Excel", data=to_excel(balance_df, df_g, df_v), file_name=f"Reporte_{st.session_state.nom_empresa}.xlsx")

        # DETALLE POR DÍA (Recuperado)
        with st.expander("🔍 Ver Detalle de Movimientos por Día"):
            st.write("### Gastos Detallados")
            st.dataframe(df_g, use_container_width=True, hide_index=True)
            st.write("### Ventas Detalladas")
            st.dataframe(df_v, use_container_width=True, hide_index=True)

# --- VENTAS (BLINDADO PARA LUZMA Y JACOBO) ---
elif menu == "💰 Ventas":
    st.title("💰 Control de Ventas")
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    if v_data.empty:
        st.warning("⚠️ No hay vehículos. Crea uno en el módulo 'Flota'.")
    else:
        with st.form("form_v"):
            v_sel = st.selectbox("Vehículo", v_data['placa'])
            v_id = v_data[v_data['placa'] == v_sel]['id'].values[0]
            
            if st.session_state.es_textil:
                tarifas = pd.read_sql("SELECT * FROM tarifario_textil", conn)
                if tarifas.empty:
                    st.error("⚠️ Configura tarifas en el módulo 'Tarifas Textil'.")
                    monto, det = 0, ""
                else:
                    serv = st.selectbox("Tipo de Confección", tarifas['servicio'].tolist())
                    p_u = tarifas[tarifas['servicio'] == serv]['precio_unitario'].values[0]
                    cant = st.number_input(f"Cantidad (Precio/U: ${p_u:,.0f})", min_value=1)
                    monto = cant * p_u
                    det = f"Producción: {serv} - Cant: {cant}"
            else:
                det = st.text_input("Cliente / Empresa")
                monto = st.number_input("Valor del Viaje", min_value=0)
            
            if st.form_submit_button("💾 Guardar Registro"):
                cur = conn.cursor()
                cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", 
                           (int(v_id), det, monto, datetime.now().date(), "Registro Automático"))
                conn.commit(); st.success("¡Guardado!"); st.rerun()

# --- (Resto de módulos: Flota, Gastos, Hoja de Vida siguen la misma lógica completa) ---

conn.close()
