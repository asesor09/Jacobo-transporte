import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
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
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); border-left: 5px solid #007bff; }
    div.stButton > button:first-child { background-color: #007bff; color: white; border-radius: 5px; width: 100%; }
    .st-emotion-cache-12w0qpk { background-color: #dc3545 !important; } /* Botón Salir Rojo */
    </style>
    """, unsafe_allow_html=True)

# --- 3. SEGURIDAD Y LOGOUT ---
if 'login' not in st.session_state:
    st.session_state.login = False

st.sidebar.markdown("## 🛡️ Acceso Seguro")
if not st.session_state.login:
    pwd = st.sidebar.text_input("Contraseña", type="password")
    if pwd == "Jacobo2026":
        st.session_state.login = True
        st.rerun()
    else:
        st.title("🚐 C&E Eficiencias")
        st.info("Por favor, introduce tu contraseña.")
        st.stop()

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.login = False
    st.rerun()

# --- 4. MENÚ LATERAL ---
st.sidebar.divider()
menu = st.sidebar.selectbox("📂 MÓDULOS", ["📊 Dashboard y Mensuales", "🚐 Flota", "💸 Gastos", "💰 Ventas"])

# --- 📊 1. DASHBOARD Y TOTALES MENSUALES ---
if menu == "📊 Dashboard y Mensuales":
    st.title("📊 Análisis Mensual de Eficiencia")
    conn = conectar_db()
    df_g = pd.read_sql("SELECT monto, fecha, tipo_gasto FROM gastos", conn)
    df_s = pd.read_sql("SELECT valor_viaje, fecha FROM ventas", conn)
    conn.close()

    if not df_g.empty or not df_s.empty:
        df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
        df_s['Mes'] = pd.to_datetime(df_s['fecha']).dt.strftime('%Y-%m')
        
        g_t = df_g['monto'].sum(); s_t = df_s['valor_viaje'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos Totales", f"$ {s_t:,.0f}".replace(",", "."))
        c2.metric("Gastos Totales", f"$ {g_t:,.0f}".replace(",", "."))
        c3.metric("Utilidad Neta", f"$ {s_t - g_t:,.0f}".replace(",", "."), delta=f"$ {s_t - g_t:,.0f}")

        st.divider()
        st.subheader("🗓️ Comparativo por Mes")
        g_m = df_g.groupby('Mes')['monto'].sum().reset_index()
        s_m = df_s.groupby('Mes')['valor_viaje'].sum().reset_index()
        res = pd.merge(s_m, g_m, on='Mes', how='outer').fillna(0)
        res.columns = ['Mes', 'Ingresos', 'Gastos']
        res['Utilidad'] = res['Ingresos'] - res['Gastos']

        fig = px.bar(res, x='Mes', y=['Ingresos', 'Gastos'], barmode='group', color_discrete_map={'Ingresos': '#28a745', 'Gastos': '#dc3545'})
        st.plotly_chart(fig, use_container_width=True)
        
        res_v = res.copy()
        for col in ['Ingresos', 'Gastos', 'Utilidad']:
            res_v[col] = res_v[col].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.table(res_v)
    else:
        st.info("Registre datos para ver el análisis.")

# --- 🚐 2. FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Gestión de Flota")
    with st.expander("➕ Añadir Unidad"):
        with st.form("f_v"):
            c1, c2 = st.columns(2)
            placa = c1.text_input("Placa").upper()
            marca = c1.text_input("Marca"); mod = c2.text_input("Modelo"); cond = c2.text_input("Conductor")
            if st.form_submit_button("Guardar"):
                conn = conectar_db(); cur = conn.cursor()
                cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (placa, marca, mod, cond))
                conn.commit(); conn.close(); st.success("Guardado"); st.rerun()
    conn = conectar_db()
    st.table(pd.read_sql("SELECT placa, marca, modelo, conductor FROM vehiculos", conn))
    conn.close()

# --- 💸 3. GASTOS (CON DETALLE Y EDICIÓN TOTAL) ---
elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    t1, t2 = st.tabs(["📝 Registro y Vista", "✏️ Editar Gasto (Corregir Todo)"])

    with t1:
        with st.form("f_g", clear_on_submit=True):
            c1, c2 = st.columns(2)
            v_sel = c1.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
            tipo = c1.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Otros"])
            monto = c2.number_input("Monto ($)", min_value=0)
            fecha = c2.date_input("Fecha")
            detalle = st.text_input("Detalle / Observación")
            if st.form_submit_button("💾 Guardar"):
                cur = conn.cursor()
                cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (v_id, tipo, monto, fecha, detalle))
                conn.commit(); st.success("Gasto guardado"); st.rerun()
        
        st.divider()
        df_l = pd.read_sql('SELECT g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC', conn)
        df_v = df_l.copy(); df_v["monto"] = df_v["monto"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_v, use_container_width=True)
        st.download_button("📥 Excel Gastos", data=to_excel(df_l), file_name='gastos.xlsx')

    with t2:
        st.subheader("✏️ Corrección de Gasto")
        df_e = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.id DESC LIMIT 20", conn)
        if not df_e.empty:
            df_e['Label'] = df_e.apply(lambda r: f"ID:{r['id']} | {r['placa']} | {r['fecha']} | $ {r['monto']}", axis=1)
            sel = st.selectbox("Seleccione el registro", df_e['Label'])
            id_edit = int(sel.split("|")[0].split(":")[1].strip())
            
            with st.form("edit_g_form"):
                col1, col2 = st.columns(2)
                n_tipo = col1.selectbox("Corregir Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Otros"])
                n_monto = col1.number_input("Corregir Monto ($)", min_value=0)
                n_fecha = col2.date_input("Corregir Fecha")
                n_det = st.text_input("Corregir Detalle")
                if st.form_submit_button("✅ Aplicar Cambios"):
                    cur = conn.cursor()
                    cur.execute("UPDATE gastos SET tipo_gasto=%s, monto=%s, fecha=%s, detalle=%s WHERE id=%s", (n_tipo, n_monto, n_fecha, n_det, id_edit))
                    conn.commit(); st.warning(f"Gasto {id_edit} actualizado"); st.rerun()
    conn.close()

# --- 💰 4. VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    t1, t2 = st.tabs(["📝 Registro y Vista", "✏️ Editar Venta"])

    with t1:
        with st.form("f_s"):
            c1, c2 = st.columns(2)
            v_sel = c1.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
            cli = c1.text_input("Cliente"); val = c2.number_input("Valor ($)", min_value=0); fec = c2.date_input("Fecha")
            desc = st.text_input("Descripción del Viaje")
            if st.form_submit_button("💾 Guardar"):
                cur = conn.cursor()
                cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha, descripcion) VALUES (%s,%s,%s,%s,%s)", (v_id, cli, val, fec, desc))
                conn.commit(); st.success("Venta guardada"); st.rerun()

        df_l = pd.read_sql('SELECT s.fecha, v.placa, s.cliente, s.valor_viaje, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC', conn)
        df_v = df_l.copy(); df_v["valor_viaje"] = df_v["valor_viaje"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_v, use_container_width=True)
        st.download_button("📥 Excel Ventas", data=to_excel(df_l), file_name='ventas.xlsx')

    with t2:
        st.subheader("✏️ Corrección de Venta")
        df_e = pd.read_sql("SELECT s.id, s.fecha, v.placa, s.cliente, s.valor_viaje FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.id DESC LIMIT 20", conn)
        if not df_e.empty:
            df_e['Label'] = df_e.apply(lambda r: f"ID:{r['id']} | {r['placa']} | {r['cliente']} | $ {r['valor_viaje']}", axis=1)
            sel = st.selectbox("Seleccione la venta", df_e['Label'])
            id_edit = int(sel.split("|")[0].split(":")[1].strip())
            
            with st.form("edit_s_form"):
                n_cli = st.text_input("Corregir Cliente")
                n_val = st.number_input("Corregir Valor ($)", min_value=0)
                n_fecha = st.date_input("Corregir Fecha")
                n_desc = st.text_input("Corregir Descripción")
                if st.form_submit_button("✅ Aplicar Cambios"):
                    cur = conn.cursor()
                    cur.execute("UPDATE ventas SET cliente=%s, valor_viaje=%s, fecha=%s, descripcion=%s WHERE id=%s", (n_cli, n_val, n_fecha, n_desc, id_edit))
                    conn.commit(); st.warning(f"Venta {id_edit} actualizada"); st.rerun()
    conn.close()
