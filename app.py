import streamlit as st
import gspread
import sqlite3
import pandas as pd
import time
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
import json
from io import StringIO

json_key = st.secrets["gcp_service_account"]
creds_dict = json.loads(json_key)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# --- CONEXIÓN A GOOGLE SHEETS ---
spreadsheet_key = "1DBKU93EFBjOfxRe03sae2dtycg2X1cY-czMPi5MDit0"
spreadsheet = client.open_by_key(spreadsheet_key)

matricula_sheet = spreadsheet.worksheet('matricula')
curso_sheet = spreadsheet.worksheet('curso')
alumno_sheet = spreadsheet.worksheet('alumno')

matricula_df = pd.DataFrame(matricula_sheet.get_all_records())
curso_df = pd.DataFrame(curso_sheet.get_all_records())
alumno_df = pd.DataFrame(alumno_sheet.get_all_records())

# --- CREAR BD LOCAL EN SQLITE ---
def crear_bd():
    conn = sqlite3.connect('inscripciones.db')
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS matricula")
    cursor.execute("DROP TABLE IF EXISTS alumno")
    cursor.execute("DROP TABLE IF EXISTS curso")

    cursor.execute("""
        CREATE TABLE alumno (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            apellido TEXT,
            correo TEXT,
            celular TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE curso (
            id INTEGER PRIMARY KEY,
            curso TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE matricula (
            id INTEGER PRIMARY KEY,
            id_alumno INTEGER,
            fecha TEXT,
            id_curso INTEGER,
            FOREIGN KEY(id_alumno) REFERENCES alumno(id),
            FOREIGN KEY(id_curso) REFERENCES curso(id)
        )
    """)

    alumno_df.to_sql('alumno', conn, if_exists='append', index=False)
    curso_df.to_sql('curso', conn, if_exists='append', index=False)
    matricula_df.to_sql('matricula', conn, if_exists='append', index=False)

    conn.commit()
    conn.close()

# --- FUNCIONES DE CONSULTA SQL ---
def obtener_totales():
    conn = sqlite3.connect('inscripciones.db')
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM alumno")
    total_alumnos = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM matricula")
    total_matriculas = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM curso")
    total_cursos = cur.fetchone()[0]
    conn.close()
    return total_alumnos, total_matriculas, total_cursos

def obtener_tabla(nombre):
    conn = sqlite3.connect('inscripciones.db')
    df = pd.read_sql_query(f"SELECT * FROM {nombre}", conn)
    conn.close()
    return df

def actualizar_hoja(nombre_hoja, df):
    hoja = spreadsheet.worksheet(nombre_hoja)
    hoja.clear()
    if 'fecha' in df.columns:
        df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce').dt.strftime('%Y-%m-%d')
    hoja.update([df.columns.values.tolist()] + df.values.tolist())

# --- INTERFAZ DE AUTENTICACIÓN ---
def autenticar():
    st.image("portada.jpeg", use_container_width=True)
    st.title("Bienvenido al Sistema de Inscripciones")
    with st.form("login_form"):
        usuario = st.text_input("Usuario")
        clave = st.text_input("Contraseña", type="password")
        login = st.form_submit_button("Ingresar")
        if login:
            if usuario == "master" and clave == "laboratorio":
                st.session_state["autenticado"] = True
            else:
                st.error("Credenciales incorrectas")

# --- INTERFAZ STREAMLIT PRINCIPAL ---
def main():
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False

    if not st.session_state["autenticado"]:
        autenticar()
        return

    st.set_page_config(page_title="Gestión de Inscripciones", layout="wide")
    st.title("📚 Gestión de Inscripciones a Cursos")

    crear_bd()  # carga inicial desde Google Sheets

    menu = st.sidebar.radio("Menú", ["Dashboard", "Consulta de Cursos", "Consulta de Alumnos", "Módulo Matrículas", "Módulo Alumnos", "Módulo Cursos"])

    conn = sqlite3.connect('inscripciones.db')

    if menu == "Dashboard":
        total_a, total_m, total_c = obtener_totales()
        st.metric("Total de Alumnos", total_a)
        st.metric("Total de Matrículas", total_m)
        st.metric("Total de Cursos", total_c)

    elif menu == "Consulta de Cursos":
        cursos = obtener_tabla("curso")
        st.subheader("📘 Cursos Disponibles")
        st.dataframe(cursos)

        if not cursos.empty:
            opciones = {f"{row['curso']} (ID {row['id']})": row['id'] for _, row in cursos.iterrows()}
            curso_sel = st.selectbox("Selecciona un curso", list(opciones.keys()))
            id_sel = opciones[curso_sel]

            query = '''
                SELECT a.nombre, a.apellido, a.correo, a.celular, m.fecha
                FROM matricula m
                JOIN alumno a ON m.id_alumno = a.id
                WHERE m.id_curso = ?
            '''
            df = pd.read_sql_query(query, conn, params=(id_sel,))
            st.write(f"### Alumnos matriculados en: {curso_sel}")
            st.dataframe(df)

    elif menu == "Consulta de Alumnos":
        alumnos = obtener_tabla("alumno")
        st.subheader("👩‍🎓 Alumnos Registrados")
        st.dataframe(alumnos)

        if not alumnos.empty:
            alumnos['identificador'] = alumnos['nombre'] + " " + alumnos['apellido'] + " | " + alumnos['correo']
            opciones = {row['identificador']: row['id'] for _, row in alumnos.iterrows()}
            alumno_sel = st.selectbox("Selecciona un alumno", list(opciones.keys()))
            id_alumno = opciones[alumno_sel]

            query = '''
                SELECT c.curso, m.fecha
                FROM matricula m
                JOIN curso c ON m.id_curso = c.id
                WHERE m.id_alumno = ?
            '''
            df = pd.read_sql_query(query, conn, params=(id_alumno,))
            st.write(f"### Cursos matriculados por: {alumno_sel}")
            st.dataframe(df)

    elif menu == "Módulo Matrículas":
        st.subheader("📝 Registro de Matrículas")

        alumnos = obtener_tabla("alumno")
        cursos = obtener_tabla("curso")

        alumno_map = {f"{row['nombre']} {row['apellido']}": row['id'] for _, row in alumnos.iterrows()}
        curso_map = {row['curso']: row['id'] for _, row in cursos.iterrows()}

        alumno_sel = st.selectbox("Selecciona un alumno", list(alumno_map.keys()))
        curso_sel = st.selectbox("Selecciona un curso", list(curso_map.keys()))
        fecha_sel = st.date_input("Fecha de matrícula").strftime('%Y-%m-%d')

        if st.button("Registrar matrícula"):
            conn.execute("INSERT INTO matricula (id_alumno, fecha, id_curso) VALUES (?, ?, ?)", (alumno_map[alumno_sel], fecha_sel, curso_map[curso_sel]))
            conn.commit()
            nueva_df = obtener_tabla("matricula")
            actualizar_hoja('matricula', nueva_df)
            st.success("Matrícula registrada exitosamente. Por favor recarga manualmente la app para ver los cambios.")

        st.dataframe(obtener_tabla("matricula"))

    elif menu == "Módulo Alumnos":
        st.subheader("👨‍🏫 Registro y Edición de Alumnos")

        with st.form("form_nuevo_alumno"):
            nombre = st.text_input("Nombre")
            apellido = st.text_input("Apellido")
            correo = st.text_input("Correo")
            celular = st.text_input("Celular")
            submitted = st.form_submit_button("Agregar Alumno")
            if submitted:
                conn.execute("INSERT INTO alumno (nombre, apellido, correo, celular) VALUES (?, ?, ?, ?)", (nombre, apellido, correo, celular))
                conn.commit()
                actualizar_hoja('alumno', obtener_tabla("alumno"))
                st.success("Alumno agregado. Por favor recarga manualmente la app para ver los cambios.")

        st.dataframe(obtener_tabla("alumno"))

    elif menu == "Módulo Cursos":
        st.subheader("📖 Registro de Cursos")
        st.dataframe(obtener_tabla("curso"))

    conn.close()

if __name__ == "__main__":
    main()
