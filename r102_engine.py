from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from typing import List, Dict


# -------------------------
# Tipos de equipos y campana
# -------------------------

class ApplianceType(str, Enum):
    FRYER = "freidora"
    GRIDDLE = "plancha"
    RANGE_2B = "cocina 2 quemadores"
    RANGE_4B = "cocina 4 quemadores"


class HoodFilterType(str, Enum):
    SIMPLE = "simple"
    DOUBLE = "doble"
    V_BANK = "en V"


class DesignMode(str, Enum):
    APPLIANCE_SPECIFIC = "appliance_specific"
    OVERLAPPING = "overlapping"


@dataclass
class Appliance:
    tipo: ApplianceType
    nombre: str
    ancho_mm: float
    fondo_mm: float
    altura_superficie_mm: float  # altura de la superficie del equipo desde el piso
    altura_boquilla_sobre_superficie_mm: float  # boquilla sobre la superficie
    pos_inicio_mm: float  # posición desde el borde izquierdo de la campana
    num_vats: int = 1     # solo aplica a freidoras (1 o 2 bateas)


@dataclass
class Hood:
    largo_mm: float
    fondo_mm: float
    altura_suelo_mm: float
    filtro: HoodFilterType
    num_ductos: int = 1


@dataclass
class Duct:
    perimetro_mm: float
    cantidad: int = 1  # número de ductos con ese perímetro


@dataclass
class Part:
    code: str
    nombre: str
    unit_price: float   # precio neto (sin IVA)
    unidad: str = "u"


@dataclass
class BOMItem:
    part: Part
    quantity: int


@dataclass
class QuoteResult:
    bom: List[BOMItem] = field(default_factory=list)
    subtotal: float = 0.0
    iva_rate: float = 0.19
    iva_amount: float = 0.0
    total: float = 0.0


# -------------------------
# Catálogo básico de partes
# -------------------------

PART_CATALOG: Dict[str, Part] = {
    # Agente extintor ANSULEX (galones)
    "79694": Part("79694", "ANSULEX 1,5 gal", 250_000),
    "79372": Part("79372", "ANSULEX 3,0 gal", 420_000),

    # Cilindros de agente
    "429864": Part("429864", "Cilindro 1,5 gal R-102", 180_000),
    "429862": Part("429862", "Cilindro 3,0 gal R-102", 210_000),

    # Cartuchos de nitrógeno (disparo regulado)
    "423429": Part("423429", "Cartucho N2 LT-20-R", 90_000),
    "423435": Part("423435", "Cartucho N2 LT-30-R", 110_000),
    "423493": Part("423493", "Cartucho N2 doble cilindro", 130_000),

    # Boquillas (simplificado)
    "439841": Part("439841", "Boquilla 3N (freidora)", 65_000),
    "439845": Part("439845", "Boquilla 290 (equipo de superficie)", 55_000),
    "439838": Part("439838", "Boquilla 1N (pleno / campana)", 50_000),
    "439839": Part("439839", "Boquilla 1W (conducto pequeño)", 50_000),
    "439840": Part("439840", "Boquilla 2W (conducto grande)", 55_000),

    # Extintor Clase K (inventado)
    "KEXT-6L": Part("KEXT-6L", "Extintor Clase K 6 Lts", 180_000),

    # Servicio de montaje (inventado)
    "SERV-MONT-R102": Part("SERV-MONT-R102", "Servicio montaje sistema R-102", 350_000, unidad="servicio"),
}

# Números de caudal por boquilla (flow number)
NOZZLE_FLOW_NUMBER: Dict[str, float] = {
    "439839": 1.0,   # 1W
    "439838": 1.0,   # 1N
    "439840": 2.0,   # 2W
    "439845": 2.0,   # 290
    "439841": 3.0,   # 3N
}


# -------------------------
# Helpers para el BOM
# -------------------------

def add_bom_item(bom: List[BOMItem], part_code: str, qty: int) -> None:
    """Agrega un ítem al BOM (o acumula si ya existe)."""
    if qty <= 0:
        return

    part = PART_CATALOG.get(part_code)
    if not part:
        raise ValueError(f"Código de parte no encontrado en catálogo: {part_code}")

    for item in bom:
        if item.part.code == part_code:
            item.quantity += qty
            return

    bom.append(BOMItem(part=part, quantity=qty))


def merge_boms(boms: List[List[BOMItem]]) -> List[BOMItem]:
    """NUEVO: fusiona varios BOM en uno solo (por proyecto)."""
    merged: Dict[str, BOMItem] = {}
    for bom in boms:
        for item in bom:
            code = item.part.code
            if code in merged:
                merged[code].quantity += item.quantity
            else:
                merged[code] = BOMItem(part=item.part, quantity=item.quantity)
    return list(merged.values())


# -------------------------
# Reglas simplificadas por tipo de equipo
# -------------------------

def design_fryer_nozzles(app: Appliance) -> Dict[str, int]:
    """
    Freidora:
    - Boquilla 3N (código 439841).
    - Área total = ancho x fondo x nº de bateas.
    """
    x = app.ancho_mm / 1000.0  # m
    y = app.fondo_mm / 1000.0  # m
    area = x * y * max(1, app.num_vats)
    max_area_3n = 0.239
    max_lado_3n = 0.644
    lado_mas_largo = max(x, y)

    base_nozzles = ceil(area / max_area_3n)

    if lado_mas_largo > max_lado_3n:
        base_nozzles *= 2

    return {"439841": base_nozzles}


def design_griddle_nozzles(app: Appliance) -> Dict[str, int]:
    """
    Plancha:
    - Boquilla 290 (439845).
    - 1 boquilla ~0.36 m² de plancha (simplificado).
    """
    x = app.ancho_mm / 1000.0
    y = app.fondo_mm / 1000.0
    area = x * y
    max_area = 0.36
    base_nozzles = ceil(area / max_area)
    return {"439845": base_nozzles}


def design_range_nozzles(app: Appliance) -> Dict[str, int]:
    """
    Cocinas (open burners), reglas simplificadas:
    - 2 quemadores → 1 boquilla 290.
    - 4 quemadores → 2 boquillas 290.
    """
    if app.tipo == ApplianceType.RANGE_2B:
        return {"439845": 1}
    elif app.tipo == ApplianceType.RANGE_4B:
        return {"439845": 2}
    return {}


# -------------------------
# Selección de cilindros según número de caudal
# -------------------------

@dataclass
class CylinderConfig:
    num_cylinders_15: int
    num_cylinders_30: int
    cartridge_code: str


def select_cylinders_and_cartridge(total_flow_number: float) -> CylinderConfig:
    """
    Selección simplificada según nº de caudal total:
    - 1–5:    1 x 1.5 gal (cartucho LT-20-R)
    - 6–11:   1 x 3.0 gal (cartucho LT-30-R)
    - 11–16:  1 x 1.5 + 1 x 3.0 (cartucho doble)
    - 16–22:  2 x 3.0 (cartucho doble)
    """
    if 1 <= total_flow_number <= 5:
        return CylinderConfig(num_cylinders_15=1, num_cylinders_30=0, cartridge_code="423429")

    if 6 <= total_flow_number <= 11:
        return CylinderConfig(num_cylinders_15=0, num_cylinders_30=1, cartridge_code="423435")

    if 11 < total_flow_number <= 16:
        return CylinderConfig(num_cylinders_15=1, num_cylinders_30=1, cartridge_code="423493")

    if 16 < total_flow_number <= 22:
        return CylinderConfig(num_cylinders_15=0, num_cylinders_30=2, cartridge_code="423493")

    raise ValueError(f"Número de caudal fuera de rango para esta versión: {total_flow_number}")


# -------------------------
# Motor principal de diseño (por HAZARD AREA)
# -------------------------

@dataclass
class DesignInput:
    hood: Hood
    duct: Duct
    appliances: List[Appliance]
    incluir_servicio_montaje: bool = True
    incluir_extintor_k: bool = False
    cantidad_extintores_k: int = 1
    design_mode: DesignMode = DesignMode.APPLIANCE_SPECIFIC
    nombre_area: str = ""       # NUEVO: nombre de la hazard area (ej. "Campana 1")


@dataclass
class DesignOutput:
    quote: QuoteResult
    total_flow_number: float
    nozzle_breakdown: Dict[str, int]
    cylinder_config: CylinderConfig
    warnings: List[str] = field(default_factory=list)
    nombre_area: str = ""       # NUEVO: se copia desde el input


def design_r102_system(design_input: DesignInput, iva_rate: float = 0.19) -> DesignOutput:
    """
    Calcula el diseño para UNA hazard area (campana + ducto + equipos).
    """
    bom: List[BOMItem] = []
    nozzle_counts: Dict[str, int] = {}
    warnings: List[str] = []

    hood = design_input.hood
    duct = design_input.duct

    # 1) Validaciones geométricas y de altura
    for app in design_input.appliances:
        # Altura boquilla sobre superficie
        if not (800 <= app.altura_boquilla_sobre_superficie_mm <= 1500):
            warnings.append(
                f"Altura de boquilla fuera de rango razonable para '{app.nombre}' "
                f"({app.altura_boquilla_sobre_superficie_mm} mm sobre la superficie)."
            )

        # Distancia campana - superficie equipo
        clearance = hood.altura_suelo_mm - app.altura_superficie_mm
        if clearance < 400 or clearance > 1500:
            warnings.append(
                f"Distancia campana-equipo para '{app.nombre}' es atípica: "
                f"{clearance} mm (revisar en terreno)."
            )

        # Verificar que el equipo esté bajo la campana
        fin_equipo = app.pos_inicio_mm + app.ancho_mm
        if app.pos_inicio_mm < 0 or fin_equipo > hood.largo_mm:
            warnings.append(
                f"El equipo '{app.nombre}' queda parcial o totalmente fuera de la campana "
                f"(inicio={app.pos_inicio_mm} mm, ancho={app.ancho_mm} mm, campana={hood.largo_mm} mm)."
            )

    # 2) Boquillas por equipos según modo
    if design_input.design_mode == DesignMode.APPLIANCE_SPECIFIC:
        for app in design_input.appliances:
            if app.tipo == ApplianceType.FRYER:
                noz = design_fryer_nozzles(app)
            elif app.tipo == ApplianceType.GRIDDLE:
                noz = design_griddle_nozzles(app)
            elif app.tipo in (ApplianceType.RANGE_2B, ApplianceType.RANGE_4B):
                noz = design_range_nozzles(app)
            else:
                noz = {}

            for code, qty in noz.items():
                nozzle_counts[code] = nozzle_counts.get(code, 0) + qty
    else:
        # OVERLAPPING: boquillas de superficie 290 distribuidas a lo largo de la campana
        hood_length_m = hood.largo_mm / 1000.0
        paso = 0.6  # separación estándar entre boquillas (m)
        num_surface_nozzles = max(1, ceil(hood_length_m / paso))
        nozzle_counts["439845"] = nozzle_counts.get("439845", 0) + num_surface_nozzles

    # 3) Boquillas para ducto (simplificado, multiplicado por nº de ductos)
    if duct.perimetro_mm > 0 and duct.cantidad > 0:
        perim = duct.perimetro_mm
        if perim <= 1270:
            nozzle_counts["439839"] = nozzle_counts.get("439839", 0) + duct.cantidad
        elif perim <= 2540:
            nozzle_counts["439840"] = nozzle_counts.get("439840", 0) + duct.cantidad
        else:
            raise ValueError("Perímetro de ducto fuera de rango para esta versión simplificada")

    # 4) Boquillas para campana/pleno (1N cada 3 m + ajuste por filtro en V)
    hood_length_m = hood.largo_mm / 1000.0
    num_hood_nozzles = max(1, ceil(hood_length_m / 3.0))
    if hood.filtro == HoodFilterType.V_BANK:
        num_hood_nozzles += 1

    nozzle_counts["439838"] = nozzle_counts.get("439838", 0) + num_hood_nozzles

    # 5) Número de caudal total
    total_flow = 0.0
    for code, qty in nozzle_counts.items():
        flow = NOZZLE_FLOW_NUMBER.get(code)
        if flow is None:
            raise ValueError(f"No hay número de caudal definido para boquilla {code}")
        total_flow += flow * qty

    # 6) Selección de cilindros y cartucho
    cyl_cfg = select_cylinders_and_cartridge(total_flow)

    # 7) Construir BOM: boquillas
    for code, qty in nozzle_counts.items():
        add_bom_item(bom, code, qty)

    # 8) Cilindros y agente
    if cyl_cfg.num_cylinders_15:
        add_bom_item(bom, "429864", cyl_cfg.num_cylinders_15)
        add_bom_item(bom, "79694", cyl_cfg.num_cylinders_15)

    if cyl_cfg.num_cylinders_30:
        add_bom_item(bom, "429862", cyl_cfg.num_cylinders_30)
        add_bom_item(bom, "79372", cyl_cfg.num_cylinders_30)

    # 9) Cartucho de gas
    add_bom_item(bom, cyl_cfg.cartridge_code, 1)

    # 10) Servicio de montaje
    if design_input.incluir_servicio_montaje:
        add_bom_item(bom, "SERV-MONT-R102", 1)

    # 11) Extintor Clase K opcional
    if design_input.incluir_extintor_k and design_input.cantidad_extintores_k > 0:
        add_bom_item(bom, "KEXT-6L", design_input.cantidad_extintores_k)

    # 12) Totales
    subtotal = sum(item.part.unit_price * item.quantity for item in bom)
    iva_amount = round(subtotal * iva_rate, 0)
    total = subtotal + iva_amount

    quote = QuoteResult(
        bom=bom,
        subtotal=subtotal,
        iva_rate=iva_rate,
        iva_amount=iva_amount,
        total=total,
    )

    return DesignOutput(
        quote=quote,
        total_flow_number=total_flow,
        nozzle_breakdown=nozzle_counts,
        cylinder_config=cyl_cfg,
        warnings=warnings,
        nombre_area=design_input.nombre_area,
    )


# -------------------------
# NUEVO: Modelo de PROYECTO con múltiples hazard areas
# -------------------------

@dataclass
class ProjectInput:
    nombre_proyecto: str
    nombre_cliente: str
    hazard_areas: List[DesignInput]
    iva_rate: float = 0.19


@dataclass
class ProjectOutput:
    nombre_proyecto: str
    nombre_cliente: str
    areas: List[DesignOutput]
    quote_global: QuoteResult


def design_project(project_input: ProjectInput) -> ProjectOutput:
    """
    Calcula todas las hazard areas y arma un BOM + totales globales.
    """
    area_results: List[DesignOutput] = []
    all_boms: List[List[BOMItem]] = []

    for area_input in project_input.hazard_areas:
        result = design_r102_system(area_input, iva_rate=project_input.iva_rate)
        area_results.append(result)
        all_boms.append(result.quote.bom)

    # Fusionar BOMs
    bom_global = merge_boms(all_boms)
    subtotal = sum(item.part.unit_price * item.quantity for item in bom_global)
    iva_amount = round(subtotal * project_input.iva_rate, 0)
    total = subtotal + iva_amount

    quote_global = QuoteResult(
        bom=bom_global,
        subtotal=subtotal,
        iva_rate=project_input.iva_rate,
        iva_amount=iva_amount,
        total=total,
    )

    return ProjectOutput(
        nombre_proyecto=project_input.nombre_proyecto,
        nombre_cliente=project_input.nombre_cliente,
        areas=area_results,
        quote_global=quote_global,
    )


# -------------------------
# Demo rápida por consola
# -------------------------

def demo():
    hood = Hood(
        largo_mm=3000,
        fondo_mm=1200,
        altura_suelo_mm=2100,
        filtro=HoodFilterType.SIMPLE,
        num_ductos=1,
    )
    duct = Duct(perimetro_mm=1200, cantidad=1)

    apps = [
        Appliance(
            tipo=ApplianceType.FRYER,
            nombre="Freidora doble",
            ancho_mm=660,
            fondo_mm=711,
            altura_superficie_mm=900,
            altura_boquilla_sobre_superficie_mm=1100,
            pos_inicio_mm=200,
            num_vats=2,
        ),
        Appliance(
            tipo=ApplianceType.GRIDDLE,
            nombre="Plancha",
            ancho_mm=900,
            fondo_mm=600,
            altura_superficie_mm=900,
            altura_boquilla_sobre_superficie_mm=1100,
            pos_inicio_mm=1000,
        ),
    ]

    di = DesignInput(
        hood=hood,
        duct=duct,
        appliances=apps,
        incluir_servicio_montaje=True,
        incluir_extintor_k=True,
        cantidad_extintores_k=1,
        design_mode=DesignMode.APPLIANCE_SPECIFIC,
        nombre_area="Campana 1",
    )

    project = ProjectInput(
        nombre_proyecto="Restaurante Demo",
        nombre_cliente="Cliente X",
        hazard_areas=[di],
        iva_rate=0.19,
    )

    out = design_project(project)

    print("Proyecto:", out.nombre_proyecto, "-", out.nombre_cliente)
    for area in out.areas:
        print(f"\nÁrea: {area.nombre_area or 'Sin nombre'}")
        print("  Número de caudal total:", area.total_flow_number)
        print("  Boquillas:", area.nozzle_breakdown)
        print("  Warnings:")
        for w in area.warnings:
            print("   -", w)

    print("\nBOM Global:")
    for item in out.quote_global.bom:
        print(f"  {item.part.code} - {item.part.nombre} x {item.quantity} @ {item.part.unit_price}")
    print("Subtotal:", out.quote_global.subtotal,
          "IVA:", out.quote_global.iva_amount,
          "Total:", out.quote_global.total)


if __name__ == "__main__":
    demo()
