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


@dataclass
class Appliance:
    tipo: ApplianceType
    nombre: str
    ancho_mm: float
    fondo_mm: float
    altura_superficie_mm: float  # altura de la superficie del equipo desde el piso
    altura_boquilla_sobre_superficie_mm: float  # boquilla sobre la superficie
    num_vats: int = 1  # solo aplica a freidoras (1 o 2 bateas)


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


# -------------------------
# Reglas simplificadas por tipo de equipo
# -------------------------

def design_fryer_nozzles(app: Appliance) -> Dict[str, int]:
    """
    Freidora:
    - Boquilla 3N (código 439841).
    - Área total = ancho x fondo x nº de bateas.
    - Reglas simplificadas basadas en área y lado máximo.
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
# Motor principal de diseño
# -------------------------

@dataclass
class DesignInput:
    hood: Hood
    duct: Duct
    appliances: List[Appliance]
    incluir_servicio_montaje: bool = True
    incluir_extintor_k: bool = False
    cantidad_extintores_k: int = 1


@dataclass
class DesignOutput:
    quote: QuoteResult
    total_flow_number: float
    nozzle_breakdown: Dict[str, int]
    cylinder_config: CylinderConfig
    warnings: List[str] = field(default_factory=list)


def design_r102_system(design_input: DesignInput, iva_rate: float = 0.19) -> DesignOutput:
    bom: List[BOMItem] = []
    nozzle_counts: Dict[str, int] = {}
    warnings: List[str] = []

    hood = design_input.hood
    duct = design_input.duct

    # 1) Boquillas por equipo + validaciones de altura
    for app in design_input.appliances:
        # Validación simple de altura de boquilla sobre superficie
        if not (800 <= app.altura_boquilla_sobre_superficie_mm <= 1500):
            warnings.append(
                f"Altura de boquilla fuera de rango razonable para '{app.nombre}' "
                f"({app.altura_boquilla_sobre_superficie_mm} mm sobre la superficie)."
            )

        # Altura libre entre superficie del equipo y campana
        clearance = hood.altura_suelo_mm - app.altura_superficie_mm
        if clearance < 400 or clearance > 1500:
            warnings.append(
                f"Distancia campana-equipo para '{app.nombre}' es atípica: "
                f"{clearance} mm (revisar configuración en terreno)."
            )

        # Reglas por tipo de equipo
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

    # 2) Boquillas para ducto (simplificado, multiplicado por nº de ductos)
    if duct.perimetro_mm > 0 and duct.cantidad > 0:
        perim = duct.perimetro_mm
        if perim <= 1270:
            nozzle_counts["439839"] = nozzle_counts.get("439839", 0) + duct.cantidad
        elif perim <= 2540:
            nozzle_counts["439840"] = nozzle_counts.get("439840", 0) + duct.cantidad
        else:
            raise ValueError("Perímetro de ducto fuera de rango para esta versión simplificada")

    # 3) Boquillas para campana/pleno (1N cada 3 m de largo + ajuste por filtro en V)
    hood_length_m = hood.largo_mm / 1000.0
    num_hood_nozzles = max(1, ceil(hood_length_m / 3.0))

    # Ajuste simple si el filtro es en V (puede requerir más cobertura)
    if hood.filtro == HoodFilterType.V_BANK:
        num_hood_nozzles += 1

    nozzle_counts["439838"] = nozzle_counts.get("439838", 0) + num_hood_nozzles

    # 4) Número de caudal total
    total_flow = 0.0
    for code, qty in nozzle_counts.items():
        flow = NOZZLE_FLOW_NUMBER.get(code)
        if flow is None:
            raise ValueError(f"No hay número de caudal definido para boquilla {code}")
        total_flow += flow * qty

    # 5) Selección de cilindros y cartucho
    cyl_cfg = select_cylinders_and_cartridge(total_flow)

    # 6) Construir BOM: boquillas
    for code, qty in nozzle_counts.items():
        add_bom_item(bom, code, qty)

    # 7) Cilindros y agente
    if cyl_cfg.num_cylinders_15:
        add_bom_item(bom, "429864", cyl_cfg.num_cylinders_15)
        add_bom_item(bom, "79694", cyl_cfg.num_cylinders_15)

    if cyl_cfg.num_cylinders_30:
        add_bom_item(bom, "429862", cyl_cfg.num_cylinders_30)
        add_bom_item(bom, "79372", cyl_cfg.num_cylinders_30)

    # 8) Cartucho de gas
    add_bom_item(bom, cyl_cfg.cartridge_code, 1)

    # 9) Servicio de montaje
    if design_input.incluir_servicio_montaje:
        add_bom_item(bom, "SERV-MONT-R102", 1)

    # 10) Extintor Clase K opcional
    if design_input.incluir_extintor_k and design_input.cantidad_extintores_k > 0:
        add_bom_item(bom, "KEXT-6L", design_input.cantidad_extintores_k)

    # 11) Totales
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
            num_vats=2,
        ),
        Appliance(
            tipo=ApplianceType.GRIDDLE,
            nombre="Plancha",
            ancho_mm=900,
            fondo_mm=600,
            altura_superficie_mm=900,
            altura_boquilla_sobre_superficie_mm=1100,
        ),
    ]

    di = DesignInput(
        hood=hood,
        duct=duct,
        appliances=apps,
        incluir_servicio_montaje=True,
        incluir_extintor_k=True,
        cantidad_extintores_k=1,
    )
    out = design_r102_system(di)

    print("Número de caudal total:", out.total_flow_number)
    print("Boquillas:", out.nozzle_breakdown)
    print("Warnings:")
    for w in out.warnings:
        print(" -", w)
    print("BOM:")
    for item in out.quote.bom:
        print(f"  {item.part.code} - {item.part.nombre} x {item.quantity} @ {item.part.unit_price}")
    print("Subtotal:", out.quote.subtotal, "IVA:", out.quote.iva_amount, "Total:", out.quote.total)


if __name__ == "__main__":
    demo()
