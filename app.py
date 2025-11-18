import streamlit as st
import pandas as pd
import altair as alt

from r102_engine import (
    ApplianceType,
    HoodFilterType,
    DesignMode,
    Appliance,
    Hood,
    Duct,
    DesignInput,
    design_r102_system,  # compatibilidad
    PART_CATALOG,
    NOZZLE_FLOW_NUMBER,
    ProjectInput,
    design_project,
)

# -------------------------
# Configuración básica de la app
# -------------------------

st.set_page_config(page_title="Diseñador R-102", layout="wide")

st.title("🧯 Diseñador de sistema de supresión de cocina R-102")
st.write(
    "Herramienta demo para que el vendedor diseñe rápidamente un sistema R-102 "
    "a partir de las dimensiones de la campana, ducto y equipos."
)

st.caption(
    "Versión de prueba para validar diseños reales. Úsala junto al manual técnico R-102."
)

# -------------------------
# Sidebar: datos generales
# -------------------------

with st.sidebar:
    st.header("Datos de proyecto")

    project_name = st.text_input(
        "Nombre del proyecto",
        value="Restaurante Demo",
    )

    client_name = st.text_input(
        "Nombre del cliente",
        value="Cliente X",
    )

    st.divider()
    st.header("Campana y ducto")

    hood_length = st.number_input(
        "Largo campana (mm)",
        min_value=1000,
        max_value=8000,
        value=3000,
        step=100,
        help="Largo total de la campana en planta.",
    )
    hood_depth = st.number_input(
        "Fondo campana (mm)",
        min_value=600,
        max_value=2000,
        value=1200,
        step=50,
        help="Profundidad de la campana medida desde el muro.",
    )
    hood_height = st.number_input(
        "Altura desde piso a la campana (mm)",
        min_value=1800,
        max_value=3000,
        value=2100,
        step=50,
        help="Altura del borde inferior de la campana respecto del piso.",
    )

    filtro_tipo = st.selectbox(
        "Tipo de filtro de campana",
        options=list(HoodFilterType),
        format_func=lambda x: x.value.capitalize(),
        help="Tipo de filtro/plenum según ficha de la campana.",
    )

    num_ducts = st.number_input(
        "Número de ductos",
        min_value=0,
        max_value=5,
        value=1,
        step=1,
        help="Cantidad de ductos conectados a esta campana.",
    )

    duct_perimeter = st.number_input(
        "Perímetro de cada ducto (mm)",
        min_value=0,
        max_value=4000,
        value=1200,
        step=50,
        help="Perímetro del ducto (2·ancho + 2·alto). Usa 0 si aún no está definido.",
    )

    st.divider()
    st.header("Modo de diseño")

    modo_label = st.radio(
        "Modo de diseño",
        [
            "Diseño por equipo (appliance-specific)",
            "Overlapping estándar",
        ],
        help=(
            "Appliance-specific: cada boquilla diseñada para un equipo puntual.\n"
            "Overlapping: zona genérica solapada bajo la campana."
        ),
    )
    design_mode = (
        DesignMode.APPLIANCE_SPECIFIC
        if "equipo" in modo_label
        else DesignMode.OVERLAPPING
    )

    st.divider()
    st.header("Opciones de cotización")

    include_service = st.checkbox("Incluir servicio de montaje", value=True)

    include_ext_k = st.checkbox(
        "Incluir extintor(es) Clase K en la cotización",
        value=False,
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
# Datos del área / campana
# -------------------------

st.subheader("Hazard area / Campana")

area_name = st.text_input(
    "Nombre del área/campana",
    value="Campana 1",
    help="Ej: 'Campana Cocina Caliente', 'Campana Freidoras', etc.",
)

st.subheader("Equipos bajo la campana")
st.markdown(
    "Completa los equipos que están **directamente bajo esta campana**. "
    "La posición se mide desde el borde izquierdo de la campana (0 mm)."
)

num_appliances = st.number_input(
    "Número de equipos",
    min_value=1,
    max_value=10,
    value=2,
    step=1,
)

appliances = []

tipo_options = {
    "Freidora": ApplianceType.FRYER,
    "Plancha": ApplianceType.GRIDDLE,
    "Cocina 2 quemadores": ApplianceType.RANGE_2B,
    "Cocina 4 quemadores": ApplianceType.RANGE_4B,
}

for i in range(num_appliances):
    with st.expander(f"Equipo {i + 1}", expanded=True if i < 2 else False):
        # Fila 1: tipo + nombre + (bates si corresponde)
        row1 = st.columns([1.2, 2.0, 1.0])

        with row1[0]:
            tipo_label = st.selectbox(
                "Tipo",
                options=list(tipo_options.keys()),
                key=f"tipo_{i}",
            )
            tipo = tipo_options[tipo_label]

        with row1[1]:
            nombre = st.text_input(
                "Nombre / referencia",
                value=f"{tipo_label} #{i + 1}",
                key=f"nombre_{i}",
            )

        # Nº de bateas solo si es freidora
        num_vats = 1
        with row1[2]:
            if tipo == ApplianceType.FRYER:
                num_vats = st.selectbox(
                    "Nº bateas",
                    options=[1, 2],
                    index=1 if i == 0 else 0,
                    key=f"vats_{i}",
                )
            else:
                st.markdown("<br>", unsafe_allow_html=True)

        # Fila 2: dimensiones + alturas + posición
        row2 = st.columns(4)

        with row2[0]:
            ancho = st.number_input(
                "Ancho (mm)",
                min_value=300,
                max_value=2000,
                value=600,
                step=50,
                key=f"ancho_{i}",
            )

        with row2[1]:
            fondo = st.number_input(
                "Fondo (mm)",
                min_value=400,
                max_value=1500,
                value=600,
                step=50,
                key=f"fondo_{i}",
            )

        with row2[2]:
            altura_sup = st.number_input(
                "Alt. sup. (mm)",
                min_value=600,
                max_value=1200,
                value=900,
                step=50,
                key=f"altsup_{i}",
            )

        with row2[3]:
            altura_boq = st.number_input(
                "Boq. sobre sup. (mm)",
                min_value=500,
                max_value=1500,
                value=1100,
                step=50,
                key=f"altb_{i}",
            )

        # Fila 3: posición + resumen simple
        row3 = st.columns([1.3, 2.7])

        with row3[0]:
            default_pos = max(0, int((hood_length - ancho) / 2))
            pos_inicio = st.number_input(
                "Pos. desde borde (mm)",
                min_value=0,
                max_value=int(hood_length),
                value=default_pos,
                step=50,
                key=f"pos_{i}",
            )

        with row3[1]:
            fin_eq = pos_inicio + ancho
            dentro = 0 <= pos_inicio and fin_eq <= hood_length
            st.caption(
                f"Ocupa desde **{pos_inicio} mm** hasta **{fin_eq} mm** "
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


# -------------------------
# Botón de cálculo
# -------------------------

if st.button("Calcular sistema R-102", type="primary"):
    try:
        hood = Hood(
            largo_mm=hood_length,
            fondo_mm=hood_depth,
            altura_suelo_mm=hood_height,
            filtro=filtro_tipo,
            num_ductos=num_ducts,
        )
        duct = Duct(perimetro_mm=duct_perimeter, cantidad=num_ducts)

        # Hazard area única (por ahora)
        di = DesignInput(
            hood=hood,
            duct=duct,
            appliances=appliances,
            incluir_servicio_montaje=include_service,
            incluir_extintor_k=include_ext_k,
            cantidad_extintores_k=qty_ext_k,
            design_mode=design_mode,
            nombre_area=area_name,
        )

        # Proyecto con una sola hazard area (dejamos listo para multi-areas a futuro)
        project_input = ProjectInput(
            nombre_proyecto=project_name,
            nombre_cliente=client_name,
            hazard_areas=[di],
            iva_rate=iva_rate / 100.0,
        )

        project_result = design_project(project_input)

        # En esta versión hay solo 1 área
        area_result = project_result.areas[0]
        global_quote = project_result.quote_global

        st.markdown(
            f"## Proyecto: **{project_result.nombre_proyecto}** — Cliente: **{project_result.nombre_cliente}**"
        )
        st.markdown(f"### Área: **{area_result.nombre_area or 'Sin nombre'}**")

        # -------------------------
        # Layout visual de equipos bajo campana
        # -------------------------
        st.markdown("#### Disposición bajo la campana (vista en planta)")

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
            # Codificar estado en colores más intuitivos
            df_layout["Estado"] = df_layout["Dentro campana"].map(
                {"Sí": "Dentro de campana", "No": "Fuera de campana"}
            )

            color_scale = alt.Scale(
                domain=["Dentro de campana", "Fuera de campana"],
                range=["#4CAF50", "#E53935"],  # verde / rojo
            )

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
                    color=alt.Color("Estado:N", scale=color_scale, title="Estado"),
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
                "Las barras muestran el ancho de cada equipo."
            )

        st.markdown("**Resumen geométrico de equipos:**")
        st.dataframe(df_layout, use_container_width=True)

        # Aviso rápido de equipos fuera de campana
        fuera = df_layout[df_layout["Dentro campana"] == "No"]
        if not fuera.empty:
            nombres_fuera = ", ".join(fuera["Equipo"].tolist())
            st.warning(
                f"Los siguientes equipos quedan parcial o totalmente fuera del largo de la campana: "
                f"**{nombres_fuera}**. Revisa dimensiones o posición."
            )

        st.divider()

        # -------------------------
        # Tabs de resultados
        # -------------------------
        tab_resumen, tab_boquillas, tab_bom = st.tabs(
            ["Resumen técnico", "Boquillas y cilindros", "BOM / Costos"]
        )

        # --- Resumen técnico ---
        with tab_resumen:
            st.markdown("#### Resumen técnico del sistema")

            st.metric(
                "Número de caudal total (área)",
                f"{area_result.total_flow_number:.1f}",
            )

            st.write(
                f"- Modo de diseño: **{'Appliance-specific' if design_mode == DesignMode.APPLIANCE_SPECIFIC else 'Overlapping'}**"
            )
            st.write(
                f"- Largo campana: **{hood_length} mm**, fondo: **{hood_depth} mm**, altura: **{hood_height} mm**"
            )
            st.write(
                f"- Nº ductos: **{num_ducts}**, perímetro ducto: **{duct_perimeter} mm**"
            )

            if area_result.warnings:
                st.warning(
                    "Advertencias de diseño detectadas:\n\n- "
                    + "\n- ".join(area_result.warnings)
                )
            else:
                st.success(
                    "Sin advertencias geométricas básicas. Revisa igual contra el manual técnico R-102."
                )

        # --- Boquillas y cilindros ---
        with tab_boquillas:
            st.markdown("#### Boquillas calculadas (área)")

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

            st.markdown("#### Cilindros seleccionados (área)")
            cyl = area_result.cylinder_config
            st.write(
                f"- Cilindros 1,5 gal: **{cyl.num_cylinders_15}**  \n"
                f"- Cilindros 3,0 gal: **{cyl.num_cylinders_30}**  \n"
                f"- Cartucho de disparo: **{cyl.cartridge_code}**"
            )

        # --- BOM / Costos ---
        with tab_bom:
            st.markdown("#### BOM y costos del proyecto")

            bom_rows = []
            for item in global_quote.bom:
                line_total = item.part.unit_price * item.quantity
                bom_rows.append(
                    {
                        "Código": item.part.code,
                        "Descripción": item.part.nombre,
                        "Unidad": item.part.unidad,
                        "Cantidad": item.quantity,
                        "Precio unitario": item.part.unit_price,
                        "Total línea": line_total,
                    }
                )

            df_bom = pd.DataFrame(bom_rows)
            st.dataframe(df_bom, use_container_width=True)

            st.write("**Totales proyecto:**")
            st.write(f"- Subtotal: **${global_quote.subtotal:,.0f}**")
            st.write(
                f"- IVA ({int(global_quote.iva_rate * 100)}%): "
                f"**${global_quote.iva_amount:,.0f}**"
            )
            st.write(f"- Total: **${global_quote.total:,.0f}**")

            st.info(
                "Valores referenciales según catálogo interno. "
                "En la siguiente etapa podremos conectarlo con CRM / listas de precios oficiales."
            )

    except Exception as e:
        st.error(f"Error en el cálculo: {e}")

else:
    st.info(
        "Configura proyecto, campana, ducto y equipos, luego presiona **Calcular sistema R-102**."
    )

