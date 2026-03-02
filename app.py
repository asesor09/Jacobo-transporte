import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime
import io

# --- 1. CONFIGURACIÓN DE CONEXIÓN GLOBAL ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

# --- 2. DISEÑO Y ESTILO ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="📈")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }
    div.stButton > button:first-child { background-color: #007bff; color: white; border-radius: 5px; width: 100%; }
    .st-emotion-cache-12w0qpk { background-color: #dc3545 !important; } /* Color para botón de salida */
    </style>
    """, unsafe_allow_html=True)

# --- 3. SEGURIDAD Y BOTÓN DE SALIDA ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

def cerrar_sesion():
    st.session_state.autenticado = False
    st.rerun()

st.sidebar.markdown("## 🛡️ Acceso Seguro")
if not st.session_state.autenticado:
    password = st.sidebar.text_input("Contraseña", type="password")
    if password == "Jacobo2026":
        st.session_state.autenticado = True
        st.rerun()
    else:
        st.title("🚐 C&E Eficiencias - Transporte")
        st.info("Por favor, introduce tu contraseña en el menú lateral.")
        st.stop()

# Botón de Salida en la parte inferior del menú
if st.sidebar.button("🚪 SALIR DE LA APLICACIÓN"):
    cerrar_sesion()

# --- 4. MENÚ LATERAL ---
st.sidebar.divider()
menu = st.sidebar.selectbox("📂 SELECCIONE UN MÓDULO", 
                            ["📊 Resumen Ejecutivo", "🚐 Flota de Vehículos", "💸 Registro de Gastos", "💰 Control de Ventas"])

# --- 📊 1. RESUMEN EJECUTIVO (TOTALES MENSUALES) ---
if menu == "📊 Resumen Ejecutivo":
    st.markdown("# 📊 Tablero de Eficiencia")
    conn = conectar_db()
    v = pd.read_sql("SELECT COUNT(*) FROM vehiculos", conn).iloc[0,0]
    df_g = pd.read_sql("SELECT monto, fecha FROM gastos", conn)
    df_s = pd.read_sql("SELECT valor_viaje, fecha FROM ventas", conn)
    conn.close()

    g = df_g['monto'].sum() if not df_g.empty else 0
    s = df_s['valor_viaje'].sum() if not df_s.empty else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Vehículos Activos", v)
    c2.metric("📉 Total Egresos", f"$ {g:,.0f}".replace(",", "."))
    c3.metric("📈 Total Ingresos", f"$ {s:,.0f}".replace(",", "."))
    
    st.divider()
    st.subheader("🗓️ Balance Consolidado por Mes")
    if not df_g.empty or not df_s.empty:
        df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
        df_s['Mes'] = pd.to_datetime(df_s['fecha']).dt.strftime('%Y-%m')
        g_mes = df_g.groupby('Mes')['monto'].sum().reset_index()
        s_mes = df_s.groupby('Mes')['valor_viaje'].sum().reset_index()
        resumen_mensual = pd.merge(s_mes, g_mes, on='Mes', how='outer').fillna(0)
        resumen_mensual.columns = ['Mes', 'Ingresos', 'Gastos']
        resumen_mensual['Utilidad'] = resumen_mensual['Ingresos'] - resumen_mensual['Gastos']
        
        resumen_view = resumen_mensual.copy()
        for col in ['Ingresos', 'Gastos', 'Utilidad']:
            resumen_view[col] = resumen_view[col].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.table(resumen_view)
        st.bar_chart(resumen_mensual.set_index('Mes')[['Ingresos', 'Gastos']])

# --- 🚐 2. GESTIÓN DE VEHÍCULOS ---
elif menu == "🚐 Flota de Vehículos":
    st.markdown("# 🚐 Gestión de Unidades")
    with st.expander("➕ Registrar Nueva Unidad"):
        with st.form("form_v"):
            c1, c2 = st.columns(2)
            placa = c1.text_input("Placa").upper()
            marca = c1.text_input("Marca"); modelo = c2.text_input("Modelo"); cond = c2.text_input("Conductor")
            if st.form_submit_button("Guardar Vehículo"):
                conn = conectar_db(); cur = conn.cursor()
                cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (placa, marca, modelo, cond))
                conn.commit(); conn.close(); st.success("✅ Unidad agregada"); st.rerun()

    conn = conectar_db()
    df_v = pd.read_sql("SELECT placa as \"Placa\", marca as \"Marca\", modelo as \"Modelo\", conductor as \"Conductor\" FROM vehiculos", conn)
    conn.close()
    st.table(df_v)

# --- 💸 3. GASTOS (CON EDICIÓN) ---
elif menu == "💸 Registro de Gastos":
    st.markdown("# 💸 Control de Gastos")
    t1, t2 = st.tabs(["📝 Registrar / Editar", "📊 Historial y Totales"])
    
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    with t1:
        st.subheader("Ingresar nuevo gasto")
        with st.form("f_g"):
            c1, c2 = st.columns(2)
            veh = c1.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == veh]['id'].values[0])
            tipo = c1.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Otros"])
            monto = c2.number_input("Monto ($)", min_value=0)
            fecha = c2.date_input("Fecha")
            if st.form_submit_button("💾 Guardar Gasto"):
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha) VALUES (%s,%s,%s,%s)", (v_id, tipo, monto, fecha))
                conn.commit(); st.success("Gasto guardado"); st.rerun()
        
        st.divider()
        st.subheader("✏️ Corregir Error en Gasto")
        df_edit_g = pd.read_sql("SELECT id, fecha, tipo_gasto, monto FROM gastos ORDER BY id DESC LIMIT 10", conn)
        if not df_edit_g.empty:
            df_edit_g['Identificador'] = df_edit_g.apply(lambda r: f"ID: {r['id']} | {r['fecha']} | {r['tipo_gasto']} | $ {r['monto']}", axis=1)
            sel_g = st.selectbox("Seleccione el gasto a corregir", df_edit_g['Identificador'])
            id_g = int(sel_g.split("|")[0].split(":")[1].strip())
            nuevo_monto = st.number_input("Nuevo Monto ($)", min_value=0)
            if st.button("Actualizar Gasto"):
                cur = conn.cursor(); cur.execute("UPDATE gastos SET monto = %s WHERE id = %s", (nuevo_monto, id_g))
                conn.commit(); st.warning("Registro actualizado"); st.rerun()

    with t2:
        df_g = pd.read_sql("SELECT monto, fecha FROM gastos", conn)
        if not df_g.empty:
            df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
            resumen_g = df_g.groupby('Mes')['monto'].sum().reset_index()
            resumen_g['monto'] = resumen_g['monto'].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
            st.write("**Totales por Mes:**", resumen_g)
        
        df_list = pd.read_sql('SELECT g.fecha, v.placa, g.tipo_gasto, g.monto FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC', conn)
        df_visto = df_list.copy()
        df_visto["monto"] = df_visto["monto"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_visto, use_container_width=True)
        st.download_button("📥 Exportar a Excel", data=to_excel(df_list), file_name='gastos.xlsx')
    conn.close()

# --- 💰 4. VENTAS (CON EDICIÓN) ---
elif menu == "💰 Control de Ventas":
    st.markdown("# 💰 Registro de Ventas")
    t1, t2 = st.tabs(["📝 Registrar / Editar", "📊 Historial y Totales"])
    
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    with t1:
        with st.form("f_s"):
            c1, c2 = st.columns(2)
            veh = c1.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == veh]['id'].values[0])
            cliente = c1.text_input("Cliente"); valor = c2.number_input("Valor ($)", min_value=0); fecha = c2.date_input("Fecha")
            if st.form_submit_button("💾 Guardar Viaje"):
                cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (v_id, cliente, valor, fecha))
                conn.commit(); st.success("Venta guardada"); st.rerun()
        
        st.divider()
        st.subheader("✏️ Corregir Error en Venta")
        df_edit_v = pd.read_sql("SELECT id, fecha, cliente, valor_viaje FROM ventas ORDER BY id DESC LIMIT 10", conn)
        if not df_edit_v.empty:
            df_edit_v['Identificador'] = df_edit_v.apply(lambda r: f"ID: {r['id']} | {r['fecha']} | {r['cliente']} | $ {r['valor_viaje']}", axis=1)
            sel_v = st.selectbox("Seleccione la venta a corregir", df_edit_v['Identificador'])
            id_v = int(sel_v.split("|")[0].split(":")[1].strip())
            nuevo_valor = st.number_input("Nuevo Valor Viaje ($)", min_value=0)
            if st.button("Actualizar Venta"):
                cur = conn.cursor(); cur.execute("UPDATE ventas SET valor_viaje = %s WHERE id = %s", (nuevo_valor, id_v))
                conn.commit(); st.warning("Registro actualizado"); st.rerun()

    with t2:
        df_s = pd.read_sql("SELECT valor_viaje, fecha FROM ventas", conn)
        if not df_s.empty:
            df_s['Mes'] = pd.to_datetime(df_s['fecha']).dt.strftime('%Y-%m')
            res_s = df_s.groupby('Mes')['valor_viaje'].sum().reset_index()
            res_s['valor_viaje'] = res_s['valor_viaje'].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
            st.write("**Totales por Mes:**", res_s)

        df_list_s = pd.read_sql('SELECT s.fecha, v.placa, s.cliente, s.valor_viaje FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC', conn)
        df_visto_s = df_list_s.copy()
        df_visto_s["valor_viaje"] = df_visto_s["valor_viaje"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_visto_s, use_container_width=True)
        st.download_button("📥 Exportar a Excel", data=to_excel(df_list_s), file_name='ventas.xlsx')
    conn.close()
