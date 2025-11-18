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
    "a partir de las dimensiones de las campanas, ductos y equipos."
)
st.caption("Versión de validación interna. Usar siempre junto al manual técnico R-102.")

# -------------------------
# Sidebar: datos de proyecto globales
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

    num_areas = st.number_input(
        "Número de campanas / hazard areas",
        min_value=1,
        max_value=5,
        value=1,
        step=1,
        help="Cantidad de campanas que tendrá el sistema R-102 en este proyecto.",
    )

    st.divider()
    st.header("Modo de diseño")

    modo_label = st.radio(
        "Modo de diseño (para todas las campanas)",
        [
            "Diseño por equipo (appliance-specific)",
            "Overlapping estándar",
        ],
        help=(
            "Appliance-specific: cada boquilla está diseñada para un equipo específico.\n"
            "Overlapping: zona de protección solapada bajo la campana."
        ),
    )
    design_mode = (
        DesignMode.APPLIANCE_SPECIFIC
        if "equipo" in modo_label
        else DesignMode.OVERLAPPING
    )

    st.divider()
    st.header("Opciones de cotización (global)")

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
# Definición de cada campana (hazard area)
# -------------------------

tabs = st.tabs([f"Campana {i+1}" for i in range(num_areas)])

# Guardamos los datos de cada área para usarlos luego en el cálculo y visualización
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

        st.markdown("#### Datos de campana y ducto")

        hood_length = st.number_input(
            "Largo campana (mm)",
            min_value=1000,
            max_value=8000,
            value=3000,
            step=100,
            key=f"hood_length_{area_idx}",
            help="Largo total de la campana visto en planta.",
        )
        hood_depth = st.number_input(
            "Fondo campana (mm)",
            min_value=600,
            max_value=2000,
            value=1200,
            step=50,
            key=f"hood_depth_{area_idx}",
            help="Profundidad de la campana medida desde el muro.",
        )
        hood_height = st.number_input(
            "Altura desde piso a la campana (mm)",
            min_value=1800,
            max_value=3000,
            value=2100,
            step=50,
            key=f"hood_height_{area_idx}",
            help="Altura del borde inferior de la campana respecto del piso.",
        )

        filtro_tipo = st.selectbox(
            "Tipo de filtro de campana",
            options=list(HoodFilterType),
            format_func=lambda x: x.value.capitalize(),
            key=f"filtro_{area_idx}",
            help="Selecciona el tipo de filtro / plenum que tiene esta campana.",
        )

        num_ducts = st.number_input(
            "Número de ductos",
            min_value=0,
            max_value=5,
            value=1,
            step=1,
            key=f"num_ducts_{area_idx}",
            help="Cantidad de ductos conectados a esta campana.",
        )

        duct_perimeter = st.number_input(
            "Perímetro de cada ducto (mm)",
            min_value=0,
            max_value=4000,
            value=1200,
            step=50,
            key=f"duct_perimeter_{area_idx}",
            help="Perímetro del ducto (2·ancho + 2·alto). Usa 0 si aún no está definido.",
        )

        st.markdown("#### Equipos bajo esta campana")
        st.markdown(
            "Incluye solo los equipos que están **directamente bajo esta campana**.\n\n"
            "- La posición se mide a lo largo del frente de la campana, desde el borde izquierdo.\n"
            "- 0 mm = equipo pegado al borde izquierdo de la campana."
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
                        help="Altura aproximada de la plancha / quemadores / cuba respecto del piso.",
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
                            "desde el borde izquierdo hasta el INICIO del equipo.\n"
                            "Ej: 0 mm = pegado al borde izquierdo."
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
                            "Si no conoces la altura exacta, deja 'Automática (recomendada)'.\n"
                            "Usará un valor estándar (~1100 mm sobre la superficie)."
                        ),
                    )
                    if alt_mode.startswith("Auto"):
                        altura_boq = 1100.0  # valor típico recomendado dentro del rango R-102
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

        # Guardamos todo lo necesario de esta campana
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

if st.button("Calcular sistema R-102 para todo el proyecto", type="primary"):
    try:
        # Construimos las hazard areas (DesignInput) desde areas_data
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

        # -------------------------
        # Detalle por campana / área
        # -------------------------
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
        # BOM y totales globales del proyecto
        # -------------------------
        st.divider()
        st.markdown("## BOM y costos globales del proyecto")

        global_quote = project_result.quote_global

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
            "En la siguiente etapa podremos conectarlo con CRM y listas de precios oficiales."
        )

    except Exception as e:
        st.error(f"Error en el cálculo: {e}")

else:
    st.info(
        "Configura las campanas (hazard areas) y sus equipos, luego presiona "
        "**Calcular sistema R-102 para todo el proyecto**."
    )
