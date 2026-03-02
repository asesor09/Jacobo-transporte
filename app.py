import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# --- CONFIGURACIÓN DE CONEXIÓN GLOBAL ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

# --- ESTILO ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="📊")

st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border-left: 5px solid #007bff; }
    </style>
    """, unsafe_allow_html=True)

# --- SEGURIDAD ---
password = st.sidebar.text_input("🔑 Contraseña de acceso", type="password")
if password != "Jacobo2026":
    st.title("🚐 C&E Eficiencias")
    st.info("Por favor, ingrese la contraseña.")
    st.stop()

st.sidebar.divider()
menu = st.sidebar.radio("Navegación Principal", ["📊 Dashboard Mensual", "🚐 Vehículos", "💸 Gastos", "💰 Ventas"])

# --- 📊 1. DASHBOARD MENSUAL (VISUAL) ---
if menu == "📊 Dashboard Mensual":
    st.title("📊 Análisis de Eficiencia Mensual")
    conn = conectar_db()
    
    # Cargar datos
    df_g = pd.read_sql("SELECT monto, fecha, tipo_gasto FROM gastos", conn)
    df_v = pd.read_sql("SELECT valor_viaje, fecha FROM ventas", conn)
    conn.close()

    if not df_g.empty or not df_v.empty:
        # Procesar fechas para agrupar por mes
        df_g['mes'] = pd.to_datetime(df_g['fecha']).dt.strftime('%Y-%m')
        df_v['mes'] = pd.to_datetime(df_v['fecha']).dt.strftime('%Y-%m')

        # Agrupar por mes
        gastos_mes = df_g.groupby('mes')['monto'].sum().reset_index()
        ventas_mes = df_v.groupby('mes')['valor_viaje'].sum().reset_index()
        
        # Unir datos para la gráfica comparativa
        df_comparativo = pd.merge(ventas_mes, gastos_mes, on='mes', how='outer').fillna(0)
        df_comparativo.columns = ['Mes', 'Ingresos', 'Egresos']

        # --- MÉTRICAS TOTALES ---
        c1, c2, c3 = st.columns(3)
        total_ingresos = df_comparativo['Ingresos'].sum()
        total_egresos = df_comparativo['Egresos'].sum()
        c1.metric("Total Ingresos", f"$ {total_ingresos:,.0f}".replace(",", "."))
        c2.metric("Total Egresos", f"$ {total_egresos:,.0f}".replace(",", "."))
        c3.metric("Utilidad Neta", f"$ {total_ingresos - total_egresos:,.0f}".replace(",", "."), delta=f"{((total_ingresos-total_egresos)/total_ingresos*100 if total_ingresos>0 else 0):.1f}%")

        st.divider()

        # --- GRÁFICA 1: COMPARATIVO MENSUAL (BARRAS) ---
        st.subheader("📈 Comparativo Ingresos vs Egresos por Mes")
        fig_bar = px.bar(df_comparativo, x='Mes', y=['Ingresos', 'Egresos'], 
                         barmode='group', color_discrete_map={'Ingresos': '#28a745', 'Egresos': '#dc3545'},
                         labels={'value': 'Monto ($)', 'variable': 'Categoría'})
        st.plotly_chart(fig_bar, use_container_width=True)

        # --- GRÁFICA 2: DISTRIBUCIÓN DE GASTOS (PIE) ---
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("🍕 ¿En qué estamos gastando?")
            fig_pie = px.pie(df_g, values='monto', names='tipo_gasto', hole=0.4,
                             color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col_b:
            st.subheader("💰 Utilidad Mensual")
            df_comparativo['Utilidad'] = df_comparativo['Ingresos'] - df_comparativo['Egresos']
            fig_line = px.line(df_comparativo, x='Mes', y='Utilidad', markers=True,
                               line_shape='spline', render_mode='svg')
            st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("Registre datos en Gastos o Ventas para ver las gráficas.")

# --- SECCIONES DE REGISTRO (IGUAL QUE ANTES) ---
elif menu == "🚐 Vehículos":
    st.title("🚐 Gestión de Flota")
    with st.form("v"):
        c1, c2 = st.columns(2)
        placa = c1.text_input("Placa").upper()
        cond = c2.text_input("Conductor")
        if st.form_submit_button("Guardar"):
            conn = conectar_db(); cur = conn.cursor()
            cur.execute("INSERT INTO vehiculos (placa, conductor) VALUES (%s,%s)", (placa, cond))
            conn.commit(); conn.close(); st.success("Guardado"); st.rerun()

elif menu == "💸 Gastos":
    st.title("💸 Registro de Gastos")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.form("g"):
        c1, c2 = st.columns(2)
        v_sel = c1.selectbox("Vehículo", v_data['placa'])
        v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
        tipo = c1.selectbox("Tipo", ["Combustible", "Peaje", "Mantenimiento", "Otros"])
        monto = c2.number_input("Valor ($)", min_value=0)
        fecha = c2.date_input("Fecha")
        if st.form_submit_button("Registrar"):
            cur = conn.cursor()
            cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha) VALUES (%s,%s,%s,%s)", (v_id, tipo, monto, fecha))
            conn.commit(); st.success("Registrado"); st.rerun()
    conn.close()

elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    conn = conectar_db()
    v_data = pd.read_sql("SELECT id, placa FROM vehiculos", conn)
    with st.form("s"):
        c1, c2 = st.columns(2)
        v_sel = c1.selectbox("Vehículo", v_data['placa'])
        v_id = int(v_data[v_data['placa'] == v_sel]['id'].values[0])
        cliente = c1.text_input("Cliente")
        valor = c2.number_input("Valor ($)", min_value=0)
        fecha = c2.date_input("Fecha")
        if st.form_submit_button("Guardar"):
            cur = conn.cursor()
            cur.execute("INSERT INTO ventas (vehiculo_id, cliente, valor_viaje, fecha) VALUES (%s,%s,%s,%s)", (v_id, cliente, valor, fecha))
            conn.commit(); st.success("Registrado"); st.rerun()
    conn.close()
