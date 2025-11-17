import streamlit as st
import pandas as pd

from r102_engine import (
    ApplianceType,
    HoodFilterType,
    DesignMode,
    Appliance,
    Hood,
    Duct,
    DesignInput,
    design_r102_system,
    PART_CATALOG,
    NOZZLE_FLOW_NUMBER,
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

# -------------------------
# Sidebar: datos generales
# -------------------------

with st.sidebar:
    st.header("Datos de campana y ducto")

    hood_length = st.number_input(
        "Largo campana (mm)",
        min_value=1000,
        max_value=8000,
        value=3000,
        step=100,
    )
    hood_depth = st.number_input(
        "Fondo campana (mm)",
        min_value=600,
        max_value=2000,
        value=1200,
        step=50,
    )
    hood_height = st.number_input(
        "Altura desde piso a la campana (mm)",
        min_value=1800,
        max_value=3000,
        value=2100,
        step=50,
    )

    filtro_tipo = st.selectbox(
        "Tipo de filtro de campana",
        options=list(HoodFilterType),
        format_func=lambda x: x.value.capitalize(),
    )

    num_ducts = st.number_input(
        "Número de ductos",
        min_value=0,
        max_value=5,
        value=1,
        step=1,
    )

    duct_perimeter = st.number_input(
        "Perímetro de cada ducto (mm)",
        min_value=0,
        max_value=4000,
        value=1200,
        step=50,
    )

    modo_label = st.radio(
        "Modo de diseño",
        [
            "Diseño por equipo (appliance-specific)",
            "Overlapping estándar",
        ],
    )
    design_mode = (
        DesignMode.APPLIANCE_SPECIFIC
        if "equipo" in modo_label
        else DesignMode.OVERLAPPING
    )

    include_service = st.checkbox("Incluir servicio de montaje", value=True)

    include_ext_k = st.checkbox("Incluir extintor Clase K", value=False)
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
# Equipos bajo la campana
# -------------------------

st.subheader("Equipos bajo la campana")

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
    st.markdown(f"### Equipo {i + 1}")
    cols = st.columns(7)

    with cols[0]:
        tipo_label = st.selectbox(
            "Tipo",
            options=list(tipo_options.keys()),
            key=f"tipo_{i}",
        )
        tipo = tipo_options[tipo_label]

    with cols[1]:
        nombre = st.text_input(
            "Nombre / referencia",
            value=f"{tipo_label} #{i + 1}",
            key=f"nombre_{i}",
        )

    with cols[2]:
        ancho = st.number_input(
            "Ancho (mm)",
            min_value=300,
            max_value=2000,
            value=600,
            step=50,
            key=f"ancho_{i}",
        )

    with cols[3]:
        fondo = st.number_input(
            "Fondo (mm)",
            min_value=400,
            max_value=1500,
            value=600,
            step=50,
            key=f"fondo_{i}",
        )

    with cols[4]:
        altura_sup = st.number_input(
            "Altura superficie sobre piso (mm)",
            min_value=600,
            max_value=1200,
            value=900,
            step=50,
            key=f"altsup_{i}",
        )

    with cols[5]:
        altura_boq = st.number_input(
            "Boquilla sobre superficie (mm)",
            min_value=500,
            max_value=1500,
            value=1100,
            step=50,
            key=f"altb_{i}",
        )

    with cols[6]:
        default_pos = max(0, int((hood_length - ancho) / 2))
        pos_inicio = st.number_input(
            "Posición desde borde izquierdo (mm)",
            min_value=0,
            max_value=int(hood_length),
            value=default_pos,
            step=50,
            key=f"pos_{i}",
        )

    # Nº de bateas solo si es freidora
    num_vats = 1
    if tipo == ApplianceType.FRYER:
        num_vats = st.selectbox(
            "Nº de bateas",
            options=[1, 2],
            index=1 if i == 0 else 0,
            key=f"vats_{i}",
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

        di = DesignInput(
            hood=hood,
            duct=duct,
            appliances=appliances,
            incluir_servicio_montaje=include_service,
            incluir_extintor_k=include_ext_k,
            cantidad_extintores_k=qty_ext_k,
            design_mode=design_mode,
        )

        result = design_r102_system(di, iva_rate=iva_rate / 100.0)

        col1, col2 = st.columns(2)

        # -------------------------
        # Resumen técnico
        # -------------------------
        with col1:
            st.markdown("#### Resumen técnico")

            st.metric("Número de caudal total", f"{result.total_flow_number:.1f}")

            if result.warnings:
                st.warning(
                    "Advertencias de diseño:\n\n- " +
                    "\n- ".join(result.warnings)
                )

            st.write("**Boquillas calculadas:**")
            nozzle_rows = []
            for code, qty in result.nozzle_breakdown.items():
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

            st.write("**Cilindros seleccionados:**")
            cyl = result.cylinder_config
            st.write(
                f"- Cilindros 1,5 gal: **{cyl.num_cylinders_15}**  \n"
                f"- Cilindros 3,0 gal: **{cyl.num_cylinders_30}**  \n"
                f"- Cartucho: **{cyl.cartridge_code}**"
            )

        # -------------------------
        # Cotización
        # -------------------------
        with col2:
            st.markdown("#### Cotización estimada")

            bom_rows = []
            for item in result.quote.bom:
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

            st.write("**Totales:**")
            st.write(f"- Subtotal: **${result.quote.subtotal:,.0f}**")
            st.write(
                f"- IVA ({int(result.quote.iva_rate * 100)}%): "
                f"**${result.quote.iva_amount:,.0f}**"
            )
            st.write(f"- Total: **${result.quote.total:,.0f}**")

    except Exception as e:
        st.error(f"Error en el cálculo: {e}")

else:
    st.info(
        "Configura campana, ducto y equipos, luego presiona **Calcular sistema R-102**."
    )
