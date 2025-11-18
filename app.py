import streamlit as st
import pandas as pd
import altair as alt
import io

from r102_engine import (
    ApplianceType,
    HoodFilterType,
    DesignMode,
    Appliance,
    Hood,
    Duct,
    DesignInput,
    PART_CATALOG,
    NOZZLE_FLOW_NUMBER,
    ProjectInput,
    design_project,
)

# -------------------------
# Helpers para exportar
# -------------------------

def build_areas_summary_df(areas_data, areas_results):
    rows = []
    for idx, (info, res) in enumerate(zip(areas_data, areas_results)):
        cyl = res.cylinder_config
        rows.append(
            {
                "Campana": res.nombre_area or f"Campana {idx + 1}",
                "Largo_mm": info["hood_length"],
                "Fondo_mm": info["hood_depth"],
                "Altura_mm": info["hood_height"],
                "Ductos": info["num_ducts"],
                "Perimetro_ducto_mm": info["duct_perimeter"],
                "Caudal_total": res.total_flow_number,
                "Cil_1_5_gal": cyl.num_cylinders_15,
                "Cil_3_0_gal": cyl.num_cylinders_30,
                "Cartucho": cyl.cartridge_code,
            }
        )
    return pd.DataFrame(rows)


def build_bom_df(global_quote):
    rows = []
    for item in global_quote.bom:
        line_total = item.part.unit_price * item.quantity
        rows.append(
            {
                "Código": item.part.code,
                "Descripción": item.part.nombre,
                "Unidad": item.part.unidad,
                "Cantidad": item.quantity,
                "Precio unitario": item.part.unit_price,
                "Total línea": line_total,
            }
        )
    return pd.DataFrame(rows)


def export_to_excel(project_result, areas_summary_df, bom_df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        # Hoja de proyecto
        meta_df = pd.DataFrame(
            {
                "Campo": ["Proyecto", "Cliente", "IVA %", "Subtotal", "Total"],
                "Valor": [
                    project_result.nombre_proyecto,
                    project_result.nombre_cliente,
                    int(project_result.quote_global.iva_rate * 100),
                    project_result.quote_global.subtotal,
                    project_result.quote_global.total,
                ],
            }
        )
        meta_df.to_excel(writer, index=False, sheet_name="Proyecto")

        # Hoja de resumen por campana
        areas_summary_df.to_excel(writer, index=False, sheet_name="Resumen_Areas")

        # Hoja de BOM global
        bom_df.to_excel(writer, index=False, sheet_name="BOM_Global")

    output.seek(0)
    return output


def export_to_pdf(project_result, areas_summary_df, bom_df):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError:
        return None, (
            "Para exportar a PDF necesitas instalar reportlab en tu entorno "
            "(pip install reportlab)."
        )

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    y = height - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "Diseño sistema de supresión R-102")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Proyecto: {project_result.nombre_proyecto}")
    y -= 14
    c.drawString(40, y, f"Cliente: {project_result.nombre_cliente}")
    y -= 14
    c.drawString(
        40,
        y,
        f"IVA: {int(project_result.quote_global.iva_rate * 100)}%   "
        f"Total: ${project_result.quote_global.total:,.0f}",
    )
    y -= 24

    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Resumen por campana")
    y -= 16
    c.setFont("Helvetica", 9)
    for _, row in areas_summary_df.iterrows():
        line = (
            f"{row['Campana']}: Caudal={row['Caudal_total']:.1f}, "
            f"Cil 1.5={row['Cil_1_5_gal']}, "
            f"Cil 3.0={row['Cil_3_0_gal']}, Cartucho={row['Cartucho']}"
        )
        if y < 80:
            c.showPage()
            y = height - 40
            c.setFont("Helvetica", 9)
        c.drawString(40, y, line)
        y -= 12

    y -= 16
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "BOM global (resumen)")
    y -= 16
    c.setFont("Helvetica", 9)
    for _, row in bom_df.iterrows():
        line = (
            f"{row['Código']} - {row['Descripción']} "
            f"(x{row['Cantidad']}) = ${row['Total línea']:,.0f}"
        )
        if y < 80:
            c.showPage()
            y = height - 40
            c.setFont("Helvetica", 9)
        c.drawString(40, y, line)
        y -= 12

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer, None


# -------------------------
# Configuración básica de la app
# -------------------------

st.set_page_config(page_title="Diseñador R-102", layout="wide")

st.title("🧯 Diseñador de sistema de supresión de cocina R-102")
st.write(
    "Herramienta para que el vendedor diseñe rápidamente un sistema R-102 "
    "a partir de las dimensiones de las campanas, ductos y equipos."
)
st.caption("Versión de validación interna. Úsala siempre junto al manual técnico R-102.")

# -------------------------
# Sidebar: datos de proyecto globales
# -------------------------

with st.sidebar:
    st.header("1️⃣ Datos de proyecto")

    project_name = st.text_input(
        "Nombre del proyecto",
        value="Restaurante Demo",
    )

    client_name = st.text_input(
        "Nombre del cliente",
        value="Cliente X",
    )

    num_areas = st.number_input(
        "Número de campanas / áreas",
        min_value=1,
        max_value=5,
        value=1,
        step=1,
        help="Cantidad de campanas que tendrá el sistema R-102 en este proyecto.",
    )

    st.divider()
    st.header("2️⃣ Modo de diseño (global)")

    modo_label = st.radio(
        "Modo de diseño",
        [
            "Diseño por equipo (appliance-specific)",
            "Overlapping estándar",
        ],
        help=(
            "- **Appliance-specific**: cada boquilla protege un equipo definido.\n"
            "- **Overlapping**: zona de protección solapada bajo la campana."
        ),
    )
    design_mode = (
        DesignMode.APPLIANCE_SPECIFIC
        if "equipo" in modo_label
        else DesignMode.OVERLAPPING
    )

    st.divider()
    st.header("3️⃣ Opciones de cotización")

    include_service = st.checkbox("Incluir servicio de montaje", value=True)

    include_ext_k = st.checkbox(
        "Incluir extintor(es) Clase K",
        value=False,
        help="Agrega extintores Clase K a la cotización como complemento.",
    )
    qty_ext_k = 1
    if include_ext_k:
        qty_ext_k = st.number_input(
            "Cantidad de extintores Clase K",
            min_value=1,
            max_value=10,
            value=1,
            step=1,
        )

    iva_rate = st.slider("IVA (%)", min_value=0, max_value=30, value=19, step=1)

# -------------------------
# Definición de cada campana (hazard area)
# -------------------------

st.markdown("## Definición de campanas / hazard areas")

tabs = st.tabs([f"Campana {i+1}" for i in range(num_areas)])

areas_data = []

tipo_options = {
    "Freidora": ApplianceType.FRYER,
    "Plancha": ApplianceType.GRIDDLE,
    "Cocina 2 quemadores": ApplianceType.RANGE_2B,
    "Cocina 4 quemadores": ApplianceType.RANGE_4B,
}

for area_idx in range(num_areas):
    with tabs[area_idx]:
        st.subheader(f"Hazard area / Campana {area_idx + 1}")

        area_name = st.text_input(
            "Nombre del área/campana",
            value=f"Campana {area_idx + 1}",
            key=f"area_name_{area_idx}",
            help="Ej: 'Campana Cocina Caliente', 'Campana Freidoras', etc.",
        )

        st.markdown("### Paso 1: Datos de campana y ducto")

        col_c1, col_c2, col_c3 = st.columns(3)

        with col_c1:
            hood_length = st.number_input(
                "Largo campana (mm)",
                min_value=1000,
                max_value=8000,
                value=3000,
                step=100,
                key=f"hood_length_{area_idx}",
                help="Largo total de la campana visto en planta (frente).",
            )

        with col_c2:
            hood_depth = st.number_input(
                "Fondo campana (mm)",
                min_value=600,
                max_value=2000,
                value=1200,
                step=50,
                key=f"hood_depth_{area_idx}",
                help="Profundidad de la campana medida desde el muro.",
            )

        with col_c3:
            hood_height = st.number_input(
                "Altura desde piso a la campana (mm)",
                min_value=1800,
                max_value=3000,
                value=2100,
                step=50,
                key=f"hood_height_{area_idx}",
                help="Altura del borde inferior de la campana respecto del piso.",
            )

        col_c4, col_c5, col_c6 = st.columns(3)

        with col_c4:
            filtro_tipo = st.selectbox(
                "Tipo de filtro",
                options=list(HoodFilterType),
                format_func=lambda x: x.value.capitalize(),
                key=f"filtro_{area_idx}",
                help="Selecciona el tipo de filtro / plenum de esta campana.",
            )

        with col_c5:
            num_ducts = st.number_input(
                "Nº de ductos",
                min_value=0,
                max_value=5,
                value=1,
                step=1,
                key=f"num_ducts_{area_idx}",
                help="Cantidad de ductos que salen de esta campana.",
            )

        with col_c6:
            duct_perimeter = st.number_input(
                "Perímetro ducto (mm)",
                min_value=0,
                max_value=4000,
                value=1200,
                step=50,
                key=f"duct_perimeter_{area_idx}",
                help="Perímetro aprox. del ducto (2·ancho + 2·alto).",
            )

        st.markdown("### Paso 2: Equipos bajo esta campana")
        st.markdown(
            "Incluye solo los equipos que están **directamente bajo esta campana**.\n\n"
            "- La posición se mide a lo largo del frente de la campana, desde el borde izquierdo.\n"
            "- **0 mm** = equipo pegado al borde izquierdo de la campana."
        )

        num_appliances = st.number_input(
            "Número de equipos en esta campana",
            min_value=1,
            max_value=10,
            value=2 if area_idx == 0 else 1,
            step=1,
            key=f"num_appliances_{area_idx}",
        )

        appliances = []

        for i in range(num_appliances):
            with st.expander(f"Equipo {i + 1}", expanded=True if i < 2 else False):
                # Fila 1: tipo + nombre + bateas (si aplica)
                row1 = st.columns([1.2, 2.0, 1.0])

                with row1[0]:
                    tipo_label = st.selectbox(
                        "Tipo de equipo",
                        options=list(tipo_options.keys()),
                        key=f"tipo_{area_idx}_{i}",
                    )
                    tipo = tipo_options[tipo_label]

                with row1[1]:
                    nombre = st.text_input(
                        "Nombre / referencia",
                        value=f"{tipo_label} #{i + 1}",
                        key=f"nombre_{area_idx}_{i}",
                    )

                num_vats = 1
                with row1[2]:
                    if tipo == ApplianceType.FRYER:
                        num_vats = st.selectbox(
                            "Nº bateas",
                            options=[1, 2],
                            index=1 if i == 0 and area_idx == 0 else 0,
                            key=f"vats_{area_idx}_{i}",
                        )
                    else:
                        st.markdown("<br>", unsafe_allow_html=True)

                # Fila 2: dimensiones + altura superficie
                row2 = st.columns(3)

                with row2[0]:
                    ancho = st.number_input(
                        "Ancho (mm)",
                        min_value=300,
                        max_value=2000,
                        value=600,
                        step=50,
                        key=f"ancho_{area_idx}_{i}",
                    )

                with row2[1]:
                    fondo = st.number_input(
                        "Fondo (mm)",
                        min_value=400,
                        max_value=1500,
                        value=600,
                        step=50,
                        key=f"fondo_{area_idx}_{i}",
                    )

                with row2[2]:
                    altura_sup = st.number_input(
                        "Altura superficie (mm)",
                        min_value=600,
                        max_value=1200,
                        value=900,
                        step=50,
                        key=f"altsup_{area_idx}_{i}",
                        help="Altura aprox. de la plancha / quemadores / cuba respecto del piso.",
                    )

                # Fila 3: posición + altura boquilla
                row3 = st.columns([1.4, 1.6])

                with row3[0]:
                    default_pos = max(0, int((hood_length - ancho) / 2))
                    pos_inicio = st.number_input(
                        "Distancia desde borde izquierdo (mm)",
                        min_value=0,
                        max_value=int(hood_length),
                        value=default_pos,
                        step=50,
                        key=f"pos_{area_idx}_{i}",
                        help=(
                            "Distancia, medida a lo largo del frente de la campana, "
                            "desde el borde izquierdo hasta el **inicio** del equipo.\n"
                            "Ejemplo: 0 mm = equipo pegado al borde izquierdo."
                        ),
                    )

                with row3[1]:
                    alt_mode = st.selectbox(
                        "Altura de boquilla",
                        options=[
                            "Automática (recomendada)",
                            "Personalizada (mm)",
                        ],
                        key=f"altmode_{area_idx}_{i}",
                        help=(
                            "Si no conoces la altura exacta, usa 'Automática'. "
                            "Se toma un valor típico dentro del rango permitido."
                        ),
                    )
                    if alt_mode.startswith("Auto"):
                        altura_boq = 1100.0  # valor típico recomendado
                        st.caption(
                            "Usando altura recomendada aproximada: **1100 mm** sobre la superficie."
                        )
                    else:
                        altura_boq = st.number_input(
                            "Boquilla sobre superficie (mm)",
                            min_value=500,
                            max_value=1500,
                            value=1100,
                            step=50,
                            key=f"altb_{area_idx}_{i}",
                        )

                fin_eq = pos_inicio + ancho
                dentro = 0 <= pos_inicio and fin_eq <= hood_length

                st.caption(
                    f"Este equipo ocupa desde **{pos_inicio} mm** hasta **{fin_eq} mm** "
                    f"a lo largo de la campana "
                    f"({ '✅ dentro de la campana' if dentro else '⚠️ se sale de la campana' })."
                )

                appliances.append(
                    Appliance(
                        tipo=tipo,
                        nombre=nombre,
                        ancho_mm=ancho,
                        fondo_mm=fondo,
                        altura_superficie_mm=altura_sup,
                        altura_boquilla_sobre_superficie_mm=altura_boq,
                        pos_inicio_mm=pos_inicio,
                        num_vats=num_vats,
                    )
                )

        areas_data.append(
            {
                "nombre_area": area_name,
                "hood_length": hood_length,
                "hood_depth": hood_depth,
                "hood_height": hood_height,
                "filtro_tipo": filtro_tipo,
                "num_ducts": num_ducts,
                "duct_perimeter": duct_perimeter,
                "appliances": appliances,
            }
        )

# -------------------------
# Botón de cálculo global
# -------------------------

st.markdown("## Calcular sistema completo")

if st.button("Calcular sistema R-102 para todo el proyecto", type="primary"):
    try:
        hazard_areas = []
        for area_info in areas_data:
            hood = Hood(
                largo_mm=area_info["hood_length"],
                fondo_mm=area_info["hood_depth"],
                altura_suelo_mm=area_info["hood_height"],
                filtro=area_info["filtro_tipo"],
                num_ductos=area_info["num_ducts"],
            )
            duct = Duct(
                perimetro_mm=area_info["duct_perimeter"],
                cantidad=area_info["num_ducts"],
            )

            di = DesignInput(
                hood=hood,
                duct=duct,
                appliances=area_info["appliances"],
                incluir_servicio_montaje=include_service,
                incluir_extintor_k=include_ext_k,
                cantidad_extintores_k=qty_ext_k,
                design_mode=design_mode,
                nombre_area=area_info["nombre_area"],
            )
            hazard_areas.append(di)

        project_input = ProjectInput(
            nombre_proyecto=project_name,
            nombre_cliente=client_name,
            hazard_areas=hazard_areas,
            iva_rate=iva_rate / 100.0,
        )

        project_result = design_project(project_input)

        st.markdown(
            f"## Proyecto: **{project_result.nombre_proyecto}** — Cliente: **{project_result.nombre_cliente}**"
        )

        # Detalle por campana / área
        for idx, (area_info, area_result) in enumerate(
            zip(areas_data, project_result.areas)
        ):
            st.divider()
            with st.expander(
                f"Detalle {area_result.nombre_area or f'Campana {idx+1}'}",
                expanded=(idx == 0),
            ):
                hood_length = area_info["hood_length"]
                appliances = area_info["appliances"]

                st.markdown("### Disposición bajo la campana (vista en planta)")

                layout_rows = []
                for app in appliances:
                    fin = app.pos_inicio_mm + app.ancho_mm
                    dentro = 0 <= app.pos_inicio_mm and fin <= hood_length
                    layout_rows.append(
                        {
                            "Equipo": app.nombre,
                            "Tipo": app.tipo.value,
                            "Inicio (mm)": app.pos_inicio_mm,
                            "Fin (mm)": fin,
                            "Dentro campana": "Sí" if dentro else "No",
                        }
                    )

                df_layout = pd.DataFrame(layout_rows)

                if not df_layout.empty:
                    chart = (
                        alt.Chart(df_layout)
                        .mark_bar()
                        .encode(
                            x=alt.X(
                                "Inicio (mm):Q",
                                scale=alt.Scale(domain=[0, hood_length]),
                                title="Posición (mm) a lo largo de la campana",
                            ),
                            x2="Fin (mm):Q",
                            y=alt.Y("Equipo:N", sort=None, title="Equipo"),
                            color="Dentro campana:N",
                            tooltip=[
                                "Equipo",
                                "Tipo",
                                "Inicio (mm)",
                                "Fin (mm)",
                                "Dentro campana",
                            ],
                        )
                        .properties(
                            width=800,
                            height=max(80, 40 * len(df_layout)),
                        )
                    )

                    st.altair_chart(chart, use_container_width=True)
                    st.caption(
                        f"La campana va de **0 mm** a **{hood_length} mm** (eje horizontal). "
                        "Cada barra muestra el ancho de un equipo bajo la campana."
                    )

                st.markdown("**Resumen geométrico de equipos:**")
                st.dataframe(df_layout, use_container_width=True)

                fuera = df_layout[df_layout["Dentro campana"] == "No"]
                if not fuera.empty:
                    nombres_fuera = ", ".join(fuera["Equipo"].tolist())
                    st.warning(
                        "Hay equipos que quedan parcial o totalmente fuera del largo de la campana: "
                        f"**{nombres_fuera}**. Revisa dimensiones o posición."
                    )

                st.markdown("#### Resumen técnico del sistema (esta campana)")

                st.metric(
                    "Número de caudal total (área)",
                    f"{area_result.total_flow_number:.1f}",
                )

                st.write(
                    f"- Modo de diseño: **{'Appliance-specific' if design_mode == DesignMode.APPLIANCE_SPECIFIC else 'Overlapping'}**"
                )
                st.write(
                    f"- Largo campana: **{area_info['hood_length']} mm**, "
                    f"fondo: **{area_info['hood_depth']} mm**, "
                    f"altura: **{area_info['hood_height']} mm**"
                )
                st.write(
                    f"- Nº ductos: **{area_info['num_ducts']}**, "
                    f"perímetro ducto: **{area_info['duct_perimeter']} mm**"
                )

                if area_result.warnings:
                    st.warning(
                        "Advertencias de diseño detectadas:\n\n- "
                        + "\n- ".join(area_result.warnings)
                    )
                else:
                    st.success(
                        "Sin advertencias geométricas básicas. Validar igual contra el manual técnico."
                    )

                st.markdown("#### Boquillas calculadas (esta campana)")

                nozzle_rows = []
                for code, qty in area_result.nozzle_breakdown.items():
                    part = PART_CATALOG.get(code)
                    nozzle_rows.append(
                        {
                            "Código": code,
                            "Descripción": part.nombre if part else "",
                            "Cantidad": qty,
                            "N° caudal por boquilla": NOZZLE_FLOW_NUMBER.get(code, ""),
                        }
                    )
                df_nozzles = pd.DataFrame(nozzle_rows)
                st.dataframe(df_nozzles, use_container_width=True)

                st.markdown("#### Cilindros seleccionados (esta campana)")
                cyl = area_result.cylinder_config
                st.write(
                    f"- Cilindros 1,5 gal: **{cyl.num_cylinders_15}**  \n"
                    f"- Cilindros 3,0 gal: **{cyl.num_cylinders_30}**  \n"
                    f"- Cartucho de disparo: **{cyl.cartridge_code}**"
                )

        # -------------------------
        # BOM y totales globales del proyecto + export
        # -------------------------
        st.divider()
        st.markdown("## BOM y costos globales del proyecto")

        global_quote = project_result.quote_global
        bom_df = build_bom_df(global_quote)
        st.dataframe(bom_df, use_container_width=True)

        st.write("**Totales proyecto:**")
        st.write(f"- Subtotal: **${global_quote.subtotal:,.0f}**")
        st.write(
            f"- IVA ({int(global_quote.iva_rate * 100)}%): "
            f"**${global_quote.iva_amount:,.0f}**"
        )
        st.write(f"- Total: **${global_quote.total:,.0f}**")

        # DataFrames para exportar
        areas_summary_df = build_areas_summary_df(areas_data, project_result.areas)

        st.markdown("### Exportar resultados")

        # Excel
        excel_bytes = export_to_excel(project_result, areas_summary_df, bom_df)
        st.download_button(
            label="⬇️ Descargar Excel (proyecto)",
            data=excel_bytes,
            file_name=f"R102_{project_result.nombre_proyecto}.xlsx",
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
        )

        # PDF
        pdf_bytes, pdf_error = export_to_pdf(project_result, areas_summary_df, bom_df)
        if pdf_bytes:
            st.download_button(
                label="⬇️ Descargar PDF (proyecto)",
                data=pdf_bytes,
                file_name=f"R102_{project_result.nombre_proyecto}.pdf",
                mime="application/pdf",
            )
        elif pdf_error:
            st.warning(pdf_error)

        st.info(
            "Usa estos archivos como respaldo del cálculo y para comparar con "
            "proyectos reales. Si encuentras diferencias con el diseño manual, "
            "anótalas para ajustar el motor en la siguiente iteración."
        )

    except Exception as e:
        st.error(f"Error en el cálculo: {e}")

else:
    st.info(
        "Configura las campanas (hazard areas) y sus equipos, luego presiona "
        "**Calcular sistema R-102 para todo el proyecto**."
    )
