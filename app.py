import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime
import io

# --- CONFIGURACIÓN DE CONEXIÓN GLOBAL ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

# Función para Excel
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

# --- DISEÑO Y ESTILO ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="📈")

# Estilo CSS personalizado para mejorar la elegancia
st.markdown("""
    <style>
    .main {
        background-color: #f5f7f9;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    div.stButton > button:first-child {
        background-color: #007bff;
        color: white;
        border-radius: 5px;
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SEGURIDAD ---
st.sidebar.markdown("## 🛡️ Acceso Seguro")
password = st.sidebar.text_input("Contraseña", type="password")
if password != "Jacobo2026":
    st.title("🚐 C&E Eficiencias - Transporte")
    st.info("Por favor, introduce tu contraseña para gestionar la flota.")
    st.stop()

# --- MENÚ LATERAL ---
st.sidebar.divider()
menu = st.sidebar.selectbox("📂 SELECCIONE UN MÓDULO", 
                            ["📊 Resumen Ejecutivo", "🚐 Flota de Vehículos", "💸 Registro de Gastos", "💰 Control de Ventas"])

# --- 📊 1. RESUMEN EJECUTIVO (ELEGANTE) ---
if menu == "📊 Resumen Ejecutivo":
    st.markdown("# 📊 Tablero de Eficiencia")
    st.markdown("---")
    
    conn = conectar_db()
    v = pd.read_sql("SELECT COUNT(*) FROM vehiculos", conn).iloc[0,0]
    g = pd.read_sql("SELECT SUM(monto) FROM gastos", conn).iloc[0,0] or 0
    s = pd.read_sql("SELECT SUM(valor_viaje) FROM ventas", conn).iloc[0,0] or 0
    conn.close()
    
    # Tarjetas visuales
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("📦 Vehículos Activos", v)
    with c2:
        st.metric("📉 Egresos (Gastos)", f"$ {g:,.0f}".replace(",", "."))
    with c3:
        st.metric("📈 Ingresos (Ventas)", f"$ {s:,.0f}".replace(",", "."))
    
    st.divider()
    utilidad = s - g
    if utilidad >= 0:
        st.success(f"### 🚀 Utilidad Neta Actual: **$ {utilidad:,.0f}**".replace(",", "."))
    else:
        st.error(f"### ⚠️ Déficit en Operación: **$ {utilidad:,.0f}**".replace(",", "."))

# --- 🚐 2. GESTIÓN DE VEHÍCULOS ---
elif menu == "🚐 Flota de Vehículos":
    st.markdown("# 🚐 Gestión de Unidades")
    with st.expander("➕ Registrar Nueva Unidad"):
        with st.form("form_v"):
            c1, c2 = st.columns(2)
            placa = c1.text_input("Placa").upper()
            marca = c1.text_input("Marca")
            modelo = c2.text_input("Modelo")
            cond = c2.text_input("Conductor")
            if st.form_submit_button("Guardar Vehículo"):
                if placa:
                    conn = conectar_db(); cur = conn.cursor()
                    try:
                        cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (placa, marca, modelo, cond))
                        conn.commit(); st.success("✅ Unidad agregada")
                    except: st.error("❌ Error: La placa ya existe.")
                    finally: conn.close(); st.rerun()

    st.markdown("### 🔍 Listado de Flota")
    conn = conectar_db()
    df_v = pd.read_sql("SELECT placa as \"Placa\", marca as \"Marca\", modelo as \"Modelo\", conductor as \"Conductor\" FROM vehiculos", conn)
    conn.close()
    st.table(df_v) # Usamos table para una vista más limpia

# --- 💸 3. GASTOS ---
elif menu == "💸 Registro de Gastos":
    st.markdown("# 💸 Control de Gastos")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    if not v_data.empty:
        with st.container():
            with st.form("form_g"):
                col1, col2 = st.columns(2)
                veh = col1.selectbox("Vehículo", v_data['placa'])
                v_id = int(v_data[v_data['placa'] == veh]['id'].values[0])
                tipo = col1.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Seguros", "Otros"])
                monto = col2.number_input("Monto ($)", min_value=0)
                fecha = col2.date_input("Fecha", value=datetime.now())
                detalle = st.text_input("Descripción breve")
                if st.form_submit_button("💾 Guardar Gasto"):
                    cur = conn.cursor()
                    cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (v_id, tipo, monto, fecha, detalle))
                    conn.commit(); st.success("Gasto registrado"); st.rerun()

        st.divider()
        df_g = pd.read_sql('''
            SELECT g.fecha as "Fecha", v.placa as "Placa", g.tipo_gasto as "Tipo", g.monto as "Monto_Num", g.detalle as "Detalle" 
            FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC
        ''', conn)
        if not df_g.empty:
            df_mostrar = df_g.copy()
            df_mostrar["Valor"] = df_mostrar["Monto_Num"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
            st.dataframe(df_mostrar[["Fecha", "Placa", "Tipo", "Valor", "Detalle"]], use_container_width=True)
            st.download_button("📥 Exportar Gastos (Excel)", data=to_excel(df_g), file_name='gastos.xlsx')
    conn.close()

# --- 💰 4. VENTAS ---
elif menu == "💰 Control de Ventas":
    st.markdown("# 💰 Registro de Ventas")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    if not v_data.empty:
        with st.form("form_s"):
            c1, c2 = st.columns(2)
            veh = c1.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == veh]['id'].values[0])
            cliente = c1.text_input("Cliente / Empresa")
            valor = c2.number_input("Valor Facturado ($)", min_value=0)
            fecha = c2.date_input("Fecha")
            if st.form_submit_button("💾 Guardar Viaje"):
                cur = conn.cursor()
                cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (v_id, cliente, valor, fecha))
                conn.commit(); st.success("Venta guardada"); st.rerun()
        
        st.divider()
        df_s = pd.read_sql('''
            SELECT s.fecha as "Fecha", v.placa as "Placa", s.cliente as "Cliente", s.valor_viaje as "Valor_Num" 
            FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC
        ''', conn)
        if not df_s.empty:
            df_mostrar_s = df_s.copy()
            df_mostrar_s["Ingreso"] = df_mostrar_s["Valor_Num"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
            st.dataframe(df_mostrar_s[["Fecha", "Placa", "Cliente", "Ingreso"]], use_container_width=True)
            st.download_button("📥 Exportar Ventas (Excel)", data=to_excel(df_s), file_name='ventas.xlsx')
    conn.close()
