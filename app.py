import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime
import io

# --- 1. CONFIGURACIÓN DE CONEXIÓN GLOBAL ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

# Función para Excel
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

# --- 2. DISEÑO Y ESTILO (TU ESTILO ORIGINAL) ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="📈")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }
    div.stButton > button:first-child { background-color: #007bff; color: white; border-radius: 5px; width: 100%; }
    .st-emotion-cache-12w0qpk { background-color: #dc3545 !important; } /* Estilo botón rojo salida */
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
        st.title("🚐 C&E Eficiencias - Transporte")
        st.info("Por favor, introduce tu contraseña en el menú lateral.")
        st.stop()

if st.sidebar.button("🚪 CERRAR SESIÓN"):
    st.session_state.login = False
    st.rerun()

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

    g_t = df_g['monto'].sum() if not df_g.empty else 0
    s_t = df_s['valor_viaje'].sum() if not df_s.empty else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Vehículos Activos", v)
    c2.metric("📉 Total Gastos", f"$ {g_t:,.0f}".replace(",", "."))
    c3.metric("📈 Total Ventas", f"$ {s_t:,.0f}".replace(",", "."))
    
    st.divider()
    st.subheader("🗓️ Totales por Mes")
    if not df_g.empty or not df_s.empty:
        df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
        df_s['Mes'] = pd.to_datetime(df_s['fecha']).dt.strftime('%Y-%m')
        g_m = df_g.groupby('Mes')['monto'].sum().reset_index()
        s_m = df_s.groupby('Mes')['valor_viaje'].sum().reset_index()
        res = pd.merge(s_m, g_m, on='Mes', how='outer').fillna(0)
        res.columns = ['Mes', 'Ventas', 'Gastos']
        res['Utilidad'] = res['Ventas'] - res['Gastos']
        for col in ['Ventas', 'Gastos', 'Utilidad']:
            res[col] = res[col].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.table(res)

# --- 🚐 2. GESTIÓN DE VEHÍCULOS ---
elif menu == "🚐 Flota de Vehículos":
    st.markdown("# 🚐 Gestión de Unidades")
    with st.expander("➕ Registrar Nueva Unidad"):
        with st.form("f_v"):
            c1, c2 = st.columns(2)
            placa = c1.text_input("Placa").upper()
            marca = c1.text_input("Marca"); mod = c2.text_input("Modelo"); cond = c2.text_input("Conductor")
            if st.form_submit_button("Guardar"):
                conn = conectar_db(); cur = conn.cursor()
                cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (placa, marca, mod, cond))
                conn.commit(); conn.close(); st.success("✅ Guardado"); st.rerun()
    conn = conectar_db()
    st.table(pd.read_sql("SELECT placa, marca, modelo, conductor FROM vehiculos", conn))
    conn.close()

# --- 💸 3. GASTOS (EDICIÓN TOTAL) ---
elif menu == "💸 Registro de Gastos":
    st.markdown("# 💸 Control de Gastos")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    t1, t2 = st.tabs(["➕ Registrar / Ver", "✏️ Editar Gasto (Corregir Todo)"])

    with t1:
        with st.form("f_g"):
            c1, c2 = st.columns(2)
            v_sel = c1.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
            tipo = c1.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Otros"])
            monto = c2.number_input("Monto ($)", min_value=0)
            fecha = c2.date_input("Fecha")
            if st.form_submit_button("💾 Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha) VALUES (%s,%s,%s,%s)", (v_id, tipo, monto, fecha))
                conn.commit(); st.success("Gasto guardado"); st.rerun()
        
        df_l = pd.read_sql('SELECT g.fecha, v.placa, g.tipo_gasto, g.monto FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC', conn)
        df_v = df_l.copy(); df_v["monto"] = df_v["monto"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_v, use_container_width=True)
        st.download_button("📥 Excel", data=to_excel(df_l), file_name='gastos.xlsx')

    with t2:
        st.subheader("✏️ Formulario de Corrección Total")
        df_e = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.id DESC LIMIT 20", conn)
        if not df_e.empty:
            df_e['Label'] = df_e.apply(lambda r: f"ID:{r['id']} | {r['placa']} | {r['fecha']} | $ {r['monto']}", axis=1)
            sel = st.selectbox("Seleccione el gasto a corregir", df_e['Label'])
            id_edit = int(sel.split("|")[0].split(":")[1].strip())
            
            with st.form("edit_g_form"):
                col1, col2 = st.columns(2)
                n_tipo = col1.selectbox("Corregir Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Otros"])
                n_monto = col1.number_input("Corregir Monto ($)", min_value=0)
                n_fecha = col2.date_input("Corregir Fecha")
                n_veh = col2.selectbox("Corregir Vehículo", v_data['placa'])
                n_v_id = int(v_data[v_data['placa'] == n_veh]['id'].values[0])
                if st.form_submit_button("✅ Aplicar Cambios Totales"):
                    cur = conn.cursor()
                    cur.execute("UPDATE gastos SET vehiculo_id=%s, tipo_gasto=%s, monto=%s, fecha=%s WHERE id=%s", (n_v_id, n_tipo, n_monto, n_fecha, id_edit))
                    conn.commit(); st.warning(f"Gasto ID {id_edit} actualizado"); st.rerun()
    conn.close()

# --- 💰 4. VENTAS (EDICIÓN TOTAL) ---
elif menu == "💰 Control de Ventas":
    st.markdown("# 💰 Registro de Ventas")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    t1, t2 = st.tabs(["➕ Registrar / Ver", "✏️ Editar Venta (Corregir Todo)"])

    with t1:
        with st.form("f_s"):
            c1, c2 = st.columns(2)
            v_sel = c1.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
            cli = c1.text_input("Cliente"); val = c2.number_input("Valor ($)", min_value=0); fec = c2.date_input("Fecha")
            if st.form_submit_button("💾 Guardar"):
                cur = conn.cursor(); cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (v_id, cli, val, fec))
                conn.commit(); st.success("Venta guardada"); st.rerun()

        df_l = pd.read_sql('SELECT s.fecha, v.placa, s.cliente, s.valor_viaje FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC', conn)
        df_v = df_l.copy(); df_v["valor_viaje"] = df_v["valor_viaje"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        st.dataframe(df_v, use_container_width=True)
        st.download_button("📥 Excel", data=to_excel(df_l), file_name='ventas.xlsx')

    with t2:
        st.subheader("✏️ Formulario de Corrección Total")
        df_e = pd.read_sql("SELECT s.id, s.fecha, v.placa, s.cliente, s.valor_viaje FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.id DESC LIMIT 20", conn)
        if not df_e.empty:
            df_e['Label'] = df_e.apply(lambda r: f"ID:{r['id']} | {r['placa']} | {r['cliente']} | $ {r['valor_viaje']}", axis=1)
            sel = st.selectbox("Seleccione la venta a corregir", df_e['Label'])
            id_edit = int(sel.split("|")[0].split(":")[1].strip())
            
            with st.form("edit_s_form"):
                col1, col2 = st.columns(2)
                n_cli = col1.text_input("Corregir Cliente")
                n_val = col1.number_input("Corregir Valor ($)", min_value=0)
                n_fecha = col2.date_input("Corregir Fecha")
                n_veh = col2.selectbox("Corregir Vehículo", v_data['placa'])
                n_v_id = int(v_data[v_data['placa'] == n_veh]['id'].values[0])
                if st.form_submit_button("✅ Aplicar Cambios Totales"):
                    cur = conn.cursor()
                    cur.execute("UPDATE ventas SET vehiculo_id=%s, cliente=%s, valor_viaje=%s, fecha=%s WHERE id=%s", (n_v_id, n_cli, n_val, n_fecha, id_edit))
                    conn.commit(); st.warning(f"Venta ID {id_edit} actualizada"); st.rerun()
    conn.close()
