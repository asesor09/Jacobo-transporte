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

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }
    div.stButton > button:first-child { background-color: #007bff; color: white; border-radius: 5px; width: 100%; }
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

# --- 📊 1. RESUMEN EJECUTIVO (CON TOTALES MENSUALES) ---
if menu == "📊 Resumen Ejecutivo":
    st.markdown("# 📊 Tablero de Eficiencia")
    conn = conectar_db()
    
    # Datos básicos
    v = pd.read_sql("SELECT COUNT(*) FROM vehiculos", conn).iloc[0,0]
    df_g = pd.read_sql("SELECT monto, fecha FROM gastos", conn)
    df_s = pd.read_sql("SELECT valor_viaje, fecha FROM ventas", conn)
    conn.close()

    g = df_g['monto'].sum() if not df_g.empty else 0
    s = df_s['valor_viaje'].sum() if not df_s.empty else 0
    
    # Tarjetas visuales
    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Vehículos Activos", v)
    c2.metric("📉 Total Egresos", f"$ {g:,.0f}".replace(",", "."))
    c3.metric("📈 Total Ingresos", f"$ {s:,.0f}".replace(",", "."))
    
    st.divider()
    
    # BALANCE MENSUAL CONSOLIDADO
    st.subheader("🗓️ Balance Consolidado por Mes")
    if not df_g.empty or not df_s.empty:
        df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
        df_s['Mes'] = pd.to_datetime(df_s['fecha']).dt.strftime('%Y-%m')
        
        g_mes = df_g.groupby('Mes')['monto'].sum().reset_index()
        s_mes = df_s.groupby('Mes')['valor_viaje'].sum().reset_index()
        
        resumen_mensual = pd.merge(s_mes, g_mes, on='Mes', how='outer').fillna(0)
        resumen_mensual.columns = ['Mes', 'Ingresos', 'Gastos']
        resumen_mensual['Utilidad'] = resumen_mensual['Ingresos'] - resumen_mensual['Gastos']
        
        # Formateo visual
        resumen_view = resumen_mensual.copy()
        for col in ['Ingresos', 'Gastos', 'Utilidad']:
            resumen_view[col] = resumen_view[col].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
        
        st.table(resumen_view)
        st.bar_chart(resumen_mensual.set_index('Mes')[['Ingresos', 'Gastos']])
    else:
        st.info("No hay datos suficientes para el resumen mensual.")

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
                        conn.commit(); st.success("✅ Unidad agregada"); st.rerun()
                    except: st.error("❌ Error: La placa ya existe.")
                    finally: conn.close()

    conn = conectar_db()
    df_v = pd.read_sql("SELECT placa as \"Placa\", marca as \"Marca\", modelo as \"Modelo\", conductor as \"Conductor\" FROM vehiculos", conn)
    conn.close()
    st.table(df_v)

# --- 💸 3. GASTOS (CON TOTAL MENSUAL) ---
elif menu == "💸 Registro de Gastos":
    st.markdown("# 💸 Control de Gastos")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    if not v_data.empty:
        with st.form("form_g"):
            c1, c2 = st.columns(2)
            veh = c1.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == veh]['id'].values[0])
            tipo = c1.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Otros"])
            monto = c2.number_input("Monto ($)", min_value=0)
            fecha = c2.date_input("Fecha", value=datetime.now())
            if st.form_submit_button("💾 Guardar Gasto"):
                cur = conn.cursor()
                cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha) VALUES (%s,%s,%s,%s)", (v_id, tipo, monto, fecha))
                conn.commit(); st.success("Gasto registrado"); st.rerun()

        st.divider()
        
        # TABLA DE TOTALES POR MES
        df_g = pd.read_sql("SELECT monto, fecha FROM gastos", conn)
        if not df_g.empty:
            st.subheader("💰 Totales Gastados por Mes")
            df_g['Mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
            resumen_g = df_g.groupby('Mes')['monto'].sum().reset_index()
            resumen_g.columns = ['Mes', 'Total Gastado']
            resumen_g['Total Gastado'] = resumen_g['Total Gastado'].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
            st.dataframe(resumen_g, use_container_width=True)

        st.divider()
        df_list = pd.read_sql('''SELECT g.fecha as "Fecha", v.placa as "Placa", g.tipo_gasto as "Tipo", g.monto as "Monto_Num" 
                                 FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC''', conn)
        if not df_list.empty:
            st.markdown("### 📋 Historial Detallado")
            df_visto = df_list.copy()
            df_visto["Valor"] = df_visto["Monto_Num"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
            st.dataframe(df_visto[["Fecha", "Placa", "Tipo", "Valor"]], use_container_width=True)
            st.download_button("📥 Exportar Gastos (Excel)", data=to_excel(df_list), file_name='gastos.xlsx')
    conn.close()

# --- 💰 4. VENTAS (CON TOTAL MENSUAL) ---
elif menu == "💰 Control de Ventas":
    st.markdown("# 💰 Registro de Ventas")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    
    if not v_data.empty:
        with st.form("form_s"):
            c1, c2 = st.columns(2)
            veh = c1.selectbox("Vehículo", v_data['placa'])
            v_id = int(v_data[v_data['placa'] == veh]['id'].values[0])
            cliente = c1.text_input("Cliente")
            valor = c2.number_input("Valor Facturado ($)", min_value=0)
            fecha = c2.date_input("Fecha")
            if st.form_submit_button("💾 Guardar Viaje"):
                cur = conn.cursor()
                cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (v_id, cliente, valor, fecha))
                conn.commit(); st.success("Venta guardada"); st.rerun()

        st.divider()
        
        # TABLA DE TOTALES POR MES
        df_s = pd.read_sql("SELECT valor_viaje, fecha FROM ventas", conn)
        if not df_s.empty:
            st.subheader("💵 Totales Vendidos por Mes")
            df_s['Mes'] = pd.to_datetime(df_s['fecha']).dt.strftime('%Y-%m')
            resumen_s = df_s.groupby('Mes')['valor_viaje'].sum().reset_index()
            resumen_s.columns = ['Mes', 'Total Ventas']
            resumen_s['Total Ventas'] = resumen_s['Total Ventas'].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
            st.dataframe(resumen_s, use_container_width=True)

        st.divider()
        df_list_s = pd.read_sql('''SELECT s.fecha as "Fecha", v.placa as "Placa", s.cliente as "Cliente", s.valor_viaje as "Valor_Num" 
                                   FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id ORDER BY s.fecha DESC''', conn)
        if not df_list_s.empty:
            st.markdown("### 📋 Historial Detallado")
            df_visto_s = df_list_s.copy()
            df_visto_s["Ingreso"] = df_visto_s["Valor_Num"].apply(lambda x: f"$ {x:,.0f}".replace(",", "."))
            st.dataframe(df_visto_s[["Fecha", "Placa", "Cliente", "Ingreso"]], use_container_width=True)
            st.download_button("📥 Exportar Ventas (Excel)", data=to_excel(df_list_s), file_name='ventas.xlsx')
    conn.close()
