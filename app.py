import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px
import smtplib
from email.mime.text import MIMEText

# --- INTENTO DE IMPORTACIÓN DE TWILIO ---
try:
    from twilio.rest import Client 
    TWILIO_INSTALADO = True
except ImportError:
    TWILIO_INSTALADO = False

# --- 1. CONFIGURACIÓN DE LA BASE DE DATOS ---
DB_URL = "postgresql://neondb_owner:npg_c7Dkwlh1jzGQ@ep-lucky-shadow-ac1thtiq-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

def conectar_db():
    return psycopg2.connect(DB_URL)

def inicializar_db():
    conn = conectar_db(); cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS configuracion (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    email_remitente TEXT, email_clave TEXT, email_destino TEXT,
                    twilio_sid TEXT, twilio_token TEXT, twilio_whatsapp_de TEXT, whatsapp_a TEXT,
                    CONSTRAINT single_row CHECK (id = 1))''')
    cur.execute('CREATE TABLE IF NOT EXISTS vehiculos (id SERIAL PRIMARY KEY, placa TEXT UNIQUE NOT NULL, marca TEXT, modelo TEXT, conductor TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), tipo_gasto TEXT, monto NUMERIC, fecha DATE, detalle TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, vehiculo_id INTEGER REFERENCES vehiculos(id), cliente TEXT, valor_viaje NUMERIC, fecha DATE, descripcion TEXT)')
    cur.execute('''CREATE TABLE IF NOT EXISTS hoja_vida (
                    id SERIAL PRIMARY KEY, 
                    vehiculo_id INTEGER UNIQUE REFERENCES vehiculos(id), 
                    soat_vence DATE, tecno_vence DATE, prev_vence DATE,
                    p_contractual DATE, p_extracontractual DATE, p_todoriesgo DATE, t_operaciones DATE)''')
    cur.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT DEFAULT "vendedor")')
    cur.execute("INSERT INTO usuarios (nombre, usuario, clave, rol) VALUES ('Jacobo Admin', 'admin', 'Jacobo2026', 'admin') ON CONFLICT (usuario) DO NOTHING")
    conn.commit(); conn.close()

# --- 2. LÓGICA DE NOTIFICACIONES ---
def enviar_alertas_sistema(mensaje):
    try:
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM configuracion WHERE id = 1")
        conf = cur.fetchone(); conn.close()
        if not conf:
            st.error("⚠️ Configura los datos en 'Config. Alertas'")
            return
        msg = MIMEText(mensaje); msg['Subject'] = '⚠️ ALERTA C&E'; msg['From'] = conf[1]; msg['To'] = conf[3]
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(conf[1], conf[2]); server.sendmail(conf[1], conf[3], msg.as_string())
        if TWILIO_INSTALADO and conf[4]:
            client = Client(conf[4], conf[5])
            client.messages.create(body=mensaje, from_=conf[6], to=conf[7])
        st.success("✅ Alertas enviadas.")
    except Exception as e: st.error(f"Error: {e}")

# --- 3. FUNCIÓN PARA GENERAR EXCEL ---
def generar_excel(df_balance, df_g, df_v):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_balance.to_excel(writer, index=False, sheet_name='Balance General')
        df_g.to_excel(writer, index=False, sheet_name='Detalle Gastos')
        df_v.to_excel(writer, index=False, sheet_name='Detalle Ventas')
    return output.getvalue()

# --- 4. CONFIGURACIÓN PÁGINA ---
st.set_page_config(page_title="C&E Eficiencias", layout="wide", page_icon="🚐")
inicializar_db()

# --- 5. LOGIN ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if not st.session_state.logged_in:
    st.sidebar.title("🔐 Acceso")
    u_in = st.sidebar.text_input("Usuario")
    p_in = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Ingresar"):
        conn = conectar_db(); cur = conn.cursor()
        cur.execute("SELECT nombre, rol FROM usuarios WHERE usuario = %s AND clave = %s", (u_in, p_in))
        res = cur.fetchone(); conn.close()
        if res:
            st.session_state.logged_in, st.session_state.u_name, st.session_state.u_rol = True, res[0], res[1]
            st.rerun()
    st.stop()

# --- 6. MENÚ ---
st.sidebar.write(f"👋 **{st.session_state.u_name}**")
st.sidebar.divider()
target = st.sidebar.number_input("Meta Utilidad ($)", value=5000000, step=500000)
opciones = ["📊 Dashboard", "🚐 Flota", "💸 Gastos", "💰 Ventas", "📑 Hoja de Vida", "⚙️ Usuarios"]
if st.session_state.u_rol == "admin": opciones.append("🔒 Config. Alertas")
menu = st.sidebar.selectbox("MÓDULOS", opciones)
if st.sidebar.button("🚪 CERRAR SESIÓN"): st.session_state.logged_in = False; st.rerun()

conn = conectar_db()
v_query = pd.read_sql("SELECT id, placa FROM vehiculos", conn)

# --- DASHBOARD (CON BOTÓN DE EXCEL) ---
if menu == "📊 Dashboard":
    st.title("📊 Análisis de Operación")
    c1, c2 = st.columns(2)
    with c1: placa_f = st.selectbox("Vehículo:", ["TODOS"] + v_query['placa'].tolist())
    with c2: rango = st.date_input("Rango de Fechas:", [datetime.now().date() - timedelta(days=30), datetime.now().date()])

    if len(rango) == 2:
        df_g = pd.read_sql("SELECT g.fecha, v.placa, g.tipo_gasto as concepto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id WHERE g.fecha BETWEEN %s AND %s", conn, params=[rango[0], rango[1]])
        df_v = pd.read_sql("SELECT s.fecha, v.placa, s.cliente, s.valor_viaje as monto, s.descripcion FROM ventas s JOIN vehiculos v ON s.vehiculo_id = v.id WHERE s.fecha BETWEEN %s AND %s", conn, params=[rango[0], rango[1]])
        
        if placa_f != "TODOS":
            df_g = df_g[df_g['placa'] == placa_f]; df_v = df_v[df_v['placa'] == placa_f]

        utilidad = df_v['monto'].sum() - df_g['monto'].sum()
        st.metric("Utilidad Neta", f"${utilidad:,.0f}", delta=f"{utilidad-target:,.0f}")
        
        # Consolidado de Gastos
        st.subheader("📊 Consolidado de Gastos por Concepto")
        df_con = df_g.groupby('concepto')['monto'].sum().reset_index().sort_values(by='monto', ascending=False)
        st.dataframe(df_con.style.format({'monto': '${:,.0f}'}), use_container_width=True, hide_index=True)
        st.plotly_chart(px.pie(df_con, values='monto', names='concepto', hole=0.4), use_container_width=True)
        
        # BOTÓN DE DESCARGA EXCEL (AQUÍ ESTÁ)
        res_g = df_g.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Gasto'})
        res_v = df_v.groupby('placa')['monto'].sum().reset_index().rename(columns={'monto': 'Venta'})
        balance_df = pd.merge(res_v, res_g, on='placa', how='outer').fillna(0)
        balance_df['Utilidad'] = balance_df['Venta'] - balance_df['Gasto']
        
        st.download_button(
            label="📥 Descargar Reporte en Excel",
            data=generar_excel(balance_df, df_g, df_v),
            file_name=f"Reporte_CE_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        with st.expander("🔍 Detalles fila por fila"):
            st.write("**Gastos:**"); st.dataframe(df_g, use_container_width=True, hide_index=True)
            st.write("**Ventas:**"); st.dataframe(df_v, use_container_width=True, hide_index=True)

# --- FLOTA ---
elif menu == "🚐 Flota":
    st.title("🚐 Administración de Vehículos")
    with st.form("f_flota"):
        p, m, mod, cond = st.text_input("Placa").upper(), st.text_input("Marca"), st.text_input("Modelo"), st.text_input("Conductor")
        if st.form_submit_button("➕ Añadir"):
            cur = conn.cursor(); cur.execute("INSERT INTO vehiculos (placa, marca, modelo, conductor) VALUES (%s,%s,%s,%s)", (p, m, mod, cond)); conn.commit(); st.rerun()
    df_f = pd.read_sql("SELECT id, placa, marca, modelo, conductor FROM vehiculos", conn)
    st.data_editor(df_f, column_config={"id": None}, hide_index=True, use_container_width=True)

# --- GASTOS (CON EDICIÓN) ---
elif menu == "💸 Gastos":
    st.title("💸 Gastos")
    tab1, tab2 = st.tabs(["📝 Nuevo", "✏️ Editar/Borrar"])
    with tab1:
        with st.form("fg"):
            v_sel = st.selectbox("Vehículo", v_query['placa'])
            tipo = st.selectbox("Concepto", ["Combustible", "Peaje", "Mantenimiento", "Lavada", "Viáticos", "Otros"])
            mon, fec, det = st.number_input("Valor"), st.date_input("Fecha"), st.text_input("Nota")
            if st.form_submit_button("💾 Guardar"):
                v_id = v_query[v_query['placa'] == v_sel]['id'].values[0]
                cur = conn.cursor(); cur.execute("INSERT INTO gastos (vehiculo_id, tipo_gasto, monto, fecha, detalle) VALUES (%s,%s,%s,%s,%s)", (int(v_id), tipo, mon, fec, det)); conn.commit(); st.rerun()
    with tab2:
        df_ge = pd.read_sql("SELECT g.id, g.fecha, v.placa, g.tipo_gasto, g.monto, g.detalle FROM gastos g JOIN vehiculos v ON g.vehiculo_id = v.id ORDER BY g.fecha DESC", conn)
        ed_g = st.data_editor(df_ge, column_config={"id": None, "placa": st.column_config.SelectboxColumn("Vehículo", options=v_query['placa'].tolist())}, hide_index=True, use_container_width=True, num_rows="dynamic")
        if st.button("💾 Guardar Cambios Gastos"):
            cur = conn.cursor(); ids_vivos = ed_g['id'].tolist()
            cur.execute(f"DELETE FROM gastos WHERE id NOT IN ({','.join(map(str, ids_vivos)) if ids_vivos else '0'})")
            for _, r in ed_g.iterrows():
                v_id_n = v_query[v_query['placa'] == r['placa']]['id'].values[0]
                cur.execute("UPDATE gastos SET vehiculo_id=%s, tipo_gasto=%s, monto=%s, fecha=%s, detalle=%s WHERE id=%s", (int(v_id_n), r['tipo_gasto'], r['monto'], r['fecha'], r['detalle'], int(r['id'])))
            conn.commit(); st.rerun()

# --- VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Ventas")
    # ... (Lógica de ventas completa como antes)
    pass

# --- HOJA DE VIDA ---
elif menu == "📑 Hoja de Vida":
    st.title("📑 Vencimientos")
    # ... (Lógica de semáforos completa como antes)
    pass

# --- CONFIGURACIÓN ---
elif menu == "🔒 Config. Alertas":
    st.title("🔒 Configuración de Notificaciones")
    # ... (Lógica de configuración protegida como antes)
    pass

conn.close()
