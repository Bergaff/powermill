"""
Режимы резания для PowerMill: /cutting — детерминированный расчёт (БЕЗ LLM).

Зачем без LLM: числа не должны «фантазироваться». Здесь всё считается
по формулам из справочников режимов резания:

    n  = 1000 · Vc / (π · D)                  [об/мин]  — число оборотов
    Vf = fz · z · n                            [мм/мин]  — минутная подача
    Pc = ae · ap · Vf · kc / (60 · 10^6)       [кВт]     — мощность резания

где Vc — скорость резания (м/мин), fz — подача на зуб, z — число зубьев,
ap — глубина резания, ae — ширина, kc — удельная сила резания (Н/мм²).

Значения Vc/fz/kc — РЕФЕРЕНСНЫЕ (типовые для группы материалов); они дают
безопасный «нулевой меридиан». Точные значения берутся из каталога
производителя инструмента (Sandvik Coromant, Iscar, Kennametal, Seco…).

CLI:  python -m src.cutting "Сталь 40Х, фреза D16 Sandvik, черновая"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Справочные данные
# --------------------------------------------------------------------------
# kc — удельная сила резания, Н/мм²  (используется для расчёта мощности)
# vc — диапазон скорости резания твёрдосплавом, м/мин
@dataclass(frozen=True)
class Material:
    key: str
    name: str
    group: str
    kc: float
    vc_tc: tuple[float, float]      # твёрдый сплав (carbide)
    vc_hss: tuple[float, float]     # быстрорез HSS
    hardness: str = ""
    aliases: tuple[str, ...] = ()
    is_generic: bool = False       # «любой алюминий» — берётся последним


MATERIALS: tuple[Material, ...] = (
    Material("st20", "Сталь 20", "steel_low", 1600, (130, 190), (30, 45), "~170 HB",
             ("сталь 20", "ст20", "20 сталь")),
    Material("st45", "Сталь 45", "steel_mid", 1750, (110, 160), (25, 35), "~200 HB",
             ("сталь 45", "ст45", "45 сталь")),
    Material("st3", "Ст3", "steel_low", 1500, (140, 200), (30, 45), "~130 HB",
             ("ст3", "ст.3", "сталь ст3")),
    Material("40x", "Сталь 40Х", "steel_mid", 1800, (130, 170), (25, 35), "~217 HB",
             ("сталь 40х", "40х", "40x", "сталь 40x")),
    Material("45x", "Сталь 45Х", "steel_mid", 1850, (120, 160), (22, 32), "~230 HB",
             ("45х", "сталь 45х")),
    Material("35xgsa", "Сталь 35ХГСА", "steel_mid", 1900, (100, 140), (20, 28), "~250 HB",
             ("35хгса", "сталь 35хгса")),
    Material("65g", "Сталь 65Г", "steel_mid", 1850, (110, 150), (22, 30), "~250 HB",
             ("65г", "сталь 65г")),
    Material("shx15", "ШХ15", "steel_hard", 2000, (90, 130), (18, 25), "~200 HB (HRC 60 после ЗК)",
             ("шх15", "шх-15")),
    Material("x12m", "Х12МФ", "steel_hard", 2100, (80, 120), (16, 22), "~230 HB",
             ("х12мф", "х12м")),
    Material("12x18n10t", "12Х18Н10Т (нерж.)", "stainless", 2100, (60, 100), (14, 22), "~180 HB",
             ("12х18н10т", "нержавейка", "нерж", "12x18n10t")),
    Material("08x18n10", "08Х18Н10 (нерж.)", "stainless", 2050, (65, 105), (15, 22),
             ("08х18н10", "08x18n10")),
    Material("sch20", "Чугун СЧ20", "cast_iron", 1100, (130, 200), (28, 40), "~170 HB",
             ("сч20", "чугун сч20", "чугун")),
    Material("vch50", "Чугун ВЧ50", "cast_iron", 1300, (100, 150), (22, 32), "~190 HB",
             ("вч50", "высокопрочный чугун")),
    Material("d16t", "Алюминий Д16Т", "aluminium", 700, (250, 500), (60, 120), "~110 HB",
             ("д16т", "д16", "алюминий д16")),
    Material("ad31", "Алюминий АД31/6063", "aluminium", 600, (300, 600), (80, 150), "~70 HB",
             ("ад31", "алюминий ад31", "6063")),
    Material("al_generic", "Алюминиевый сплав", "aluminium", 650, (300, 600), (80, 150),
             "", ("алюминий", "алюминев", "алюмишк", "ал"), is_generic=True),
    Material("ls59", "Латунь ЛС59-1", "brass", 900, (200, 350), (50, 90), "~130 HB",
             ("лс59", "латунь", "лс59-1")),
    Material("bronze", "Бронза БрАЖ9-4", "brass", 1000, (150, 300), (40, 70), "~120 HB",
             ("бронза", "браж")),
    Material("vt6", "Титан ВТ6", "titanium", 2200, (40, 70), (10, 15), "~270 HB",
             ("вт6", "титан вт6", "титан")),
    Material("vt1", "Титан ВТ1-0", "titanium", 1500, (60, 90), (14, 20), "~150 HB",
             ("вт1-0", "вт1")),
    Material("pom", "Полиамид/капролон (POM)", "plastic", 250, (300, 700), (100, 200),
             "", ("полиамид", "капролон", "пom", "пом", "pom", "фторопласт")),
    Material("pvc", "ПВХ/пластик", "plastic", 200, (300, 800), (100, 250), "",
             ("пвх", "пластик", "полиэтилен")),
    Material("plexiglass", "Оргстекло", "plastic", 180, (300, 800), (100, 250), "",
             ("оргстекло", "акрил")),
    Material("textolite", "Текстолит", "plastic", 350, (200, 500), (70, 150), "",
             ("текстолит", "гетинакс")),
)

GROUP_DEFAULTS = {
    "steel_low": ("Сталь (низкоуглеродистая)", 1600, (130, 190)),
    "steel_mid": ("Сталь (среднеуглеродистая/легированная)", 1800, (110, 160)),
    "steel_hard": ("Сталь (закалённая/высоколегированная)", 2100, (80, 120)),
    "stainless": ("Нержавеющая сталь", 2100, (60, 100)),
    "cast_iron": ("Чугун", 1150, (120, 190)),
    "aluminium": ("Алюминиевый сплав", 650, (300, 600)),
    "brass": ("Латунь/бронза", 950, (180, 320)),
    "titanium": ("Титан", 2100, (40, 70)),
    "plastic": ("Пластик", 250, (300, 800)),
}

# базовая подача на зуб при D=10 мм, мм/зуб (твёрдый сплав)
FZ_BASE_BY_GROUP = {
    "steel_low": 0.070,
    "steel_mid": 0.060,
    "steel_hard": 0.045,
    "stainless": 0.050,
    "cast_iron": 0.080,
    "aluminium": 0.100,
    "brass": 0.090,
    "titanium": 0.040,
    "plastic": 0.140,
}

# множитель подачи на зуб по типу операции
OP_FZ_FACTOR = {"roughing": 1.0, "hsm": 1.15, "semi": 0.8, "finishing": 0.5, "drilling": 1.0}
# Множители ap/ae относительно «чернового» режима инструмента
OP_AP_SCALE = {"roughing": 1.0, "hsm": 1.5, "semi": 0.55, "finishing": 0.25, "drilling": 1.0}
OP_AE_SCALE = {"roughing": 1.0, "hsm": 0.28, "semi": 0.7, "finishing": 0.4, "drilling": 1.0}
# Базовые ap/ae для ЧЕРНОВОЙ как доли диаметра: (ap, ae)
#  • концевая   — классика: ap 0.7D, ae 0.45D
#  • торцевая   — широкий захват, малая глубина (глубина обычно 1–5 мм)
#  • сферическая— малый шаг по строке, ap по толщине слоя
#  • радиусная  — промежуточный вариант
#  • сверло     — ap = глубина отверстия (задаётся), ae = D
TOOL_AP_AE = {
    "end": (0.70, 0.45),
    "face": (0.06, 0.70),
    "ball": (0.30, 0.08),
    "toroidal": (0.50, 0.25),
    "drill": (2.00, 1.00),
}
# Абсолютные ограничения ap, мм (глубина резания торцевой фрезы физически мала).
# Диаметр для остальных типов учитывается коэффициентами выше.
ABS_AP_CAP_MM = {"face": 6.0}

OP_NAMES = {
    "roughing": "черновая",
    "hsm": "черновая HSM (динамическая)",
    "semi": "получистовая",
    "finishing": "чистовая",
    "drilling": "сверление",
}

# стратегия PowerMill под операцию (для /cutting и /ask)
OP_STRATEGY = {
    "roughing": "Offset Area Clearance (2.5D) или Model Area Clearance (3D)",
    "hsm": "Vortex Area Clearance / Adaptive (постоянный угол контакта)",
    "semi": "Raster / Offset (получистовая) + Pencil для углов",
    "finishing": "Steep and Shallow, Constant Z или Raster Finishing",
    "drilling": "Hole Feature Set / Drilling (сверление по отверстиям)",
}

TOOL_TYPES = {
    "end": ("концевая (плоская)", 4),
    "ball": ("сферическая", 2),
    "toroidal": ("радиусная (тороидная)", 4),
    "drill": ("сверло", 2),
    "face": ("торцевая", 5),
}

COATING_FACTOR = {
    "tialn": 1.15, "altin": 1.2, "ticn": 1.05, "tin": 1.0, "dlc": 1.1,
    "": 1.0, "none": 1.0,
}

BRANDS = ("sandvik", "iscar", "kennametal", "seco", "walter", "митсубиси", "mitsubishi",
          "taegutec", "коромант", "coromant", "zcc", "haimer", "dgih", "gmf")


# --------------------------------------------------------------------------
# Разбор запроса технолога
# --------------------------------------------------------------------------
def _normalize(text: str) -> str:
    """Текст -> « пробелы вокруг слов », чтобы ловить слова, а не подстроки."""
    low = text.lower().replace(",", " ").replace(";", " ").replace("(", " ").replace(")", " ")
    return " " + " ".join(low.split()) + " "


def _alias_matches(alias: str, padded: str) -> bool:
    """Совпадение алиаса как отдельного слова (с учётом слитных марок «D16»)."""
    a = alias.strip().lower()
    if not a:
        return False
    if f" {a} " in padded:
        return True
    if a[0].isdigit() and f"{a} " in padded:      # «12Х18Н10Т фреза»
        return True
    if a[-1].isdigit() and f" {a}" in padded:     # «фреза D16», «D8.5»
        return True
    return False


def find_material(text: str) -> Material | None:
    """Ищет материал: сначала конкретные марки, потом «просто алюминий/сталь».

    Так «алюминий Д16Т» даёт Д16Т, а не обобщённый алюминий.
    """
    padded = _normalize(text)
    for generic_pass in (False, True):
        best: tuple[int, Material] | None = None
        for mat in MATERIALS:
            if mat.is_generic != generic_pass:
                continue
            for alias in mat.aliases:
                if _alias_matches(alias, padded):
                    score = len(alias)
                    if best is None or score > best[0]:
                        best = (score, mat)
        if best is not None:
            return best[1]
    return None


def parse_request(text: str) -> dict:
    """«Сталь 40Х, фреза D16 Sandvik, черновая» -> структурированные параметры."""
    low = text.lower()
    req: dict = {"raw": text, "warnings": []}

    mat = find_material(text)
    req["material"] = mat
    if mat is None:
        req["warnings"].append(
            "Материал не распознан — считаю по «сталь среднеуглеродистая» (1800 Н/мм²). "
            "Укажи материал явно, например: «сталь 40Х», «12Х18Н10Т», «Д16Т»."
        )

    m = re.search(r"\b[dDфФ]\s*[-=]?\s*(\d{1,3}(?:[.,]\d)?)\b", text)
    if not m:
        m = re.search(r"(\d{1,3}(?:[.,]\d)?)\s*(?:мм)?\s*(?:фрез|сверл|концев|сфер)", low)
    if not m:
        m = re.search(r"\b(\d{1,3}(?:[.,]\d)?)\s*мм\b", low)
    req["diameter"] = float(m.group(1).replace(",", ".")) if m else 12.0
    if not m:
        req["warnings"].append("Диаметр инструмента не указан — принял D=12 мм.")

    z = re.search(r"\bz\s*=?\s*(\d{1,2})\b", low) or re.search(r"(\d{1,2})\s*[- ]?зуб", low)
    req["flutes"] = int(z.group(1)) if z else None

    if re.search(r"сфер|ball|шар", low):
        req["tool"] = "ball"
    elif re.search(r"радиусн|тороид|toroid|bull|r\d+\.?\d*\b.*фрез", low):
        req["tool"] = "toroidal"
    elif re.search(r"сверл|drill|отверст", low):
        req["tool"] = "drill"
    elif re.search(r"торцев|face mill|фреза.?торц", low):
        req["tool"] = "face"
    else:
        req["tool"] = "end"

    if re.search(r"hsm|динамич|высокоскорост|vortex|адаптив|adaptive", low):
        req["op"] = "hsm"
    elif re.search(r"получист|semi", low):
        req["op"] = "semi"
    elif re.search(r"чистов|finish|финиш", low):
        req["op"] = "finishing"
    elif re.search(r"сверл|drill", low) and req["tool"] == "drill":
        req["op"] = "drilling"
    else:
        req["op"] = "roughing"

    req["tool_material"] = "hss" if re.search(r"\bhss\b|р6м5|быстрореж|hss-", low) else "carbide"
    coating = ""
    for c in COATING_FACTOR:
        if c and c in low:
            coating = c
            break
    req["coating"] = coating
    req["brand"] = next((b for b in BRANDS if b in low), "")

    depth = re.search(r"глуб[а-яё]*\s*(\d{1,3}(?:[.,]\d)?)", low)
    req["depth"] = float(depth.group(1).replace(",", ".")) if depth else None
    machine_rpm = re.search(r"(?:макс[^0-9]{0,12}|шпиндел[^0-9]{0,12})(\d{3,5})\s*(?:об|rpm)?", low)
    req["max_rpm"] = int(machine_rpm.group(1)) if machine_rpm else None
    power = re.search(r"(\d{1,2}(?:[.,]\d)?)\s*к?вт", low)
    req["machine_kw"] = float(power.group(1).replace(",", ".")) if power else None
    return req


# --------------------------------------------------------------------------
# Расчёт
# --------------------------------------------------------------------------
@dataclass
class CuttingResult:
    material_name: str
    material_group: str
    tool_name: str
    op_name: str
    diameter: float
    flutes: int
    vc: float
    rpm: int
    fz: float
    feed: int
    ap: float
    ae: float
    power_kw: float
    strategy: str
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    vc_range: tuple[float, float] = (0.0, 0.0)

    def as_dict(self) -> dict:
        return {
            "material": self.material_name, "op": self.op_name, "tool": self.tool_name,
            "D": self.diameter, "z": self.flutes,
            "S_rpm": self.rpm, "F_mm_min": self.feed, "ap": self.ap, "ae": self.ae,
            "Vc": self.vc, "fz": self.fz, "Pc_kW": self.power_kw,
            "strategy": self.strategy, "warnings": self.warnings,
        }


def calculate(req: dict) -> CuttingResult:
    """Считает S, F, ap, ae по разобранному запросу."""
    mat: Material | None = req.get("material")
    if mat is not None:
        group = mat.group
        vc_lo, vc_hi = (mat.vc_tc if req["tool_material"] == "carbide" else mat.vc_hss)
        mat_name, kc = mat.name, mat.kc
    else:
        group = "steel_mid"
        mat_name, kc, (vc_lo, vc_hi) = GROUP_DEFAULTS[group]

    diameter = max(0.5, float(req.get("diameter") or 12.0))
    op = req.get("op", "roughing")
    tool_key = req.get("tool", "end")
    tool_name, default_flutes = TOOL_TYPES[tool_key]
    flutes = int(req.get("flutes") or default_flutes)
    coating = COATING_FACTOR.get(req.get("coating", ""), 1.0)

    # Vc: середина диапазона; для HSM и чистовых можно смелее, для сверления ниже
    vc = (vc_lo + vc_hi) / 2 * coating
    if op == "finishing":
        vc *= 1.1
    if op == "hsm":
        vc *= 1.05
    if tool_key == "ball":
        vc *= 0.9        # у сферических скорость на вершине ниже
    if tool_key == "drill":
        vc *= 0.7

    rpm = 1000 * vc / (3.141592653589793 * diameter)
    warnings: list[str] = []
    max_rpm = req.get("max_rpm")
    if max_rpm and rpm > max_rpm:
        rpm = float(max_rpm)
        vc = rpm * 3.141592653589793 * diameter / 1000
        warnings.append(
            f"Ограничение шпинделя {max_rpm} об/мин: фактическая Vc снижена до "
            f"{vc:.0f} м/мин (проверь, что этого достаточно для стружкоотвода)."
        )
    rpm = int(round(rpm / 10.0) * 10)  # в PowerMill шаг оборотов обычно 10

    # fz: базовое значение масштабируется от диаметра (степень 0.6)
    fz0 = FZ_BASE_BY_GROUP.get(group, 0.06)
    fz = fz0 * (diameter / 10.0) ** 0.6
    fz *= OP_FZ_FACTOR.get(op, 1.0)
    if req["tool_material"] == "hss":
        fz *= 0.6
    if tool_key == "ball":
        fz *= 0.8
    if tool_key == "drill":
        fz *= 0.5
    fz = max(0.01, min(fz, 0.35))

    feed = int(round(fz * flutes * rpm / 10.0) * 10)

    ap0, ae0 = TOOL_AP_AE.get(tool_key, (0.7, 0.45))
    ap = ap0 * diameter * OP_AP_SCALE.get(op, 1.0)
    ae = ae0 * diameter * OP_AE_SCALE.get(op, 1.0)

    cap = ABS_AP_CAP_MM.get(tool_key)
    if cap:
        ap = min(ap, cap)
    if op != "drilling":
        ap = max(ap, 0.05)      # чистовые проходы не бывают «нулевыми»
    if op == "drilling":
        ap = float(req.get("depth") or 2 * diameter)
        ae = diameter
    ap = round(ap, 1)
    ae = round(ae, 1)

    # при сверлении материал снимается половиной диаметра, не всей шириной
    eff_ae = ae * 0.5 if op == "drilling" else ae
    power = eff_ae * ap * feed * kc / (60 * 10 ** 6)
    machine_kw = req.get("machine_kw")
    if machine_kw and power > machine_kw * 0.8:
        warnings.append(
            f"Расчётная мощность резания {power:.1f} кВт близка к мощности шпинделя "
            f"({machine_kw:.1f} кВт) — уменьши ae/ap или подачу."
        )
    if ae < 0.05 * diameter:
        warnings.append("ae меньше 5% диаметра: инструмент будет тереться (риск износа и наклёпа).")

    result = CuttingResult(
        material_name=mat_name,
        material_group=GROUP_DEFAULTS.get(group, ("", 0, (0, 0)))[0],
        tool_name=tool_name,
        op_name=OP_NAMES.get(op, op),
        diameter=diameter,
        flutes=flutes,
        vc=vc,
        rpm=rpm,
        fz=fz,
        feed=feed,
        ap=ap,
        ae=ae,
        power_kw=power,
        strategy=OP_STRATEGY.get(op, ""),
        warnings=warnings,
        vc_range=(vc_lo, vc_hi),
    )
    result.notes.append(
        f"kc={kc:.0f} Н/мм², Vc диапазон для группы: {vc_lo:.0f}–{vc_hi:.0f} м/мин"
        + (f", покрытие {req['coating'].upper()} (коэффициент {coating})" if req.get("coating") else "")
    )
    if req.get("brand"):
        result.notes.append(
            f"Инструмент указан как «{req['brand']}»: точные Vc/fz бери из каталога "
            "производителя — здесь референсные значения."
        )
    if op == "drilling":
        result.notes.append("Для сверления ap = глубина отверстия, ae = D; подача на оборот ≈ fz·z.")
    return result


def format_report(req: dict, res: CuttingResult) -> str:
    """Текст для чата/Telegram."""
    lines = [
        f"⚙️ Режимы резания: {res.material_name} · {res.tool_name} "
        f"D{res.diameter:g} z{res.flutes} · {res.op_name}",
        "",
        f"  S (об/мин)   : {res.rpm}",
        f"  F (мм/мин)   : {res.feed}",
        f"  ap (мм)      : {res.ap}",
        f"  ae (мм)      : {res.ae}",
        f"  Vc факт      : {res.vc:.0f} м/мин (диапазон группы {res.vc_range[0]:.0f}–{res.vc_range[1]:.0f})",
        f"  fz           : {res.fz:.3f} мм/зуб",
        f"  Pc расчётная : {res.power_kw:.1f} кВт",
        "",
        f"🎯 Стратегия PowerMill: {res.strategy}",
    ]
    if res.notes:
        lines += ["", "ℹ️ " + "\nℹ️ ".join(res.notes)]
    if res.warnings:
        lines += ["", "⚠️ " + "\n⚠️ ".join(res.warnings)]
    lines += [
        "",
        "📌 Что проверить перед запуском:",
        "  1) Жёсткость системы станок-деталь-инструмент (вылет!) — при вылете >3D",
        "     снизь fz на 20–30%, а ap — на 30%.",
        "  2) Первый проход — «воздух» или смещение заготовки +0.2 мм на черновую.",
        "  3) Стружкоотвод и СОЖ: для 12Х18Н10Т и титана — обильная подача СОЖ,",
        "     для алюминия — исключить налипание (большие Vc, полировка).",
        "  4) Проверь врезание: ramp 2–3° вместо вертикального плунжера.",
    ]
    return "\n".join(lines)


def answer(text: str) -> tuple[str, dict]:
    """Полный ответ по свободному тексту запроса: (текст, структура)."""
    req = parse_request(text)
    res = calculate(req)
    out = format_report(req, res)
    if req["warnings"]:
        out += "\n\n❓ " + "\n❓ ".join(req["warnings"])
    return out, res.as_dict()


def interactive() -> None:
    """Мастер расчёта: спрашивает материал/инструмент/операцию по-русски."""
    print("=" * 58)
    print("  КАЛЬКУЛЯТОР РЕЖИМОВ РЕЗАНИЯ PowerMill")
    print("  S — обороты, F — минутная подача, ap/ae — глубины")
    print("=" * 58)
    print("  Enter без ввода = значение по умолчанию (сталь 40Х, D16, черновая)")
    print("  Вместо ответа можно написать q — выход\n")

    while True:
        try:
            material = input("Материал   (Сталь 40Х / 12Х18Н10Т / Д16Т / СЧ20): ").strip()
            tool = input("Инструмент (фреза D16 z4 / сферическая D8 / торцевая D63): ").strip()
            op = input("Операция   (черновая / получистовая / чистовая / hsm): ").strip()
            limits = input("Ограничения (макс. обороты, кВт — можно пусто): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            return

        if any(v.lower() in {"q", "й", "quit", "exit", "выход"}
               for v in (material, tool, op, limits)):
            print("Выход.")
            return

        query = ", ".join(p for p in (material, tool, op, limits) if p)
        if not query:
            query = "Сталь 40Х, фреза D16, черновая"

        print()
        print(answer(query)[0])
        print()
        try:
            again = input("Ещё расчёт? [Enter — да, q — выход]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            return
        print()
        if again in {"q", "й", "quit", "exit", "н", "no", "n"}:
            print("Выход.")
            return


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        print(answer(" ".join(sys.argv[1:]))[0])
    else:
        interactive()
