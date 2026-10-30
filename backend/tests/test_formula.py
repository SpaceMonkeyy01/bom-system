import math

import pytest

from app.engine.formula import (
    FormulaError,
    LineSpec,
    ParamSpec,
    calculate,
    check_formula,
    cost_tags_used,
    evaluate,
    is_cost_formula,
    norm_tag,
    order_vars,
    parse,
    qty_tags_used,
    variables_used,
)


def ev(src, **vars):
    return evaluate(parse(src), {k.lower(): v for k, v in vars.items()})


# ---------------------------------------------------------------- language


def test_arithmetic_and_precedence():
    assert ev("1 + 2 * 3") == 7
    assert ev("(1 + 2) * 3") == 9
    assert ev("10 / 4") == 2.5
    assert ev("-3 + 5") == 2
    assert ev("2 * -3") == -6
    assert ev("+4") == 4


def test_leading_equals_and_blank():
    assert ev("= 2 + 2") == 4
    assert ev("") == 0
    assert ev(None) == 0


def test_variables_case_insensitive():
    assert ev("Crunched_Area_SS_ft2 * 1.2", Crunched_Area_SS_ft2=10) == 12
    assert ev("crunched_area_ss_FT2 * 1.2", Crunched_Area_SS_ft2=10) == 12
    with pytest.raises(FormulaError, match="Unknown input"):
        ev("Missing * 2")


def test_python_style_ternary_with_string_compare():
    f = '22 * 0.42 if Finish == "Matt" else 0'
    assert ev(f, Finish="Matt") == pytest.approx(9.24)
    assert ev(f, Finish="matt") == pytest.approx(9.24)  # text compares ignore case
    assert ev(f, Finish="Gloss") == 0


def test_smart_quotes_and_single_quotes():
    assert ev("1 if Finish == “Satin” else 2", Finish="Satin") == 1
    assert ev("1 if Finish == 'Satin' else 2", Finish="Gloss") == 2


def test_nested_ternary_is_right_associative():
    f = "1 if x == 1 else 2 if x == 2 else 3"
    assert ev(f, x=1) == 1 and ev(f, x=2) == 2 and ev(f, x=9) == 3


def test_if_function_and_comparisons():
    assert ev("IF(n > 8, 2, 1)", n=9) == 2
    assert ev("IF(n > 8, 2, 1)", n=8) == 1
    assert ev("IF(n >= 8, 2, 1)", n=8) == 2
    assert ev("IF(a <> b, 1, 0)", a=1, b=2) == 1
    assert ev("IF(a = b, 1, 0)", a=2, b=2) == 1  # single = is equality


def test_boolean_keywords():
    assert ev("1 if a > 1 and b > 1 else 0", a=2, b=2) == 1
    assert ev("1 if a > 1 or b > 1 else 0", a=0, b=2) == 1
    assert ev("1 if not a > 1 else 0", a=0) == 1


def test_math_functions():
    assert ev("MIN(3, 1, 2)") == 1
    assert ev("MAX(3, 1, 2)") == 3
    assert ev("ROUND(2.5)") == 3
    assert ev("ROUND(2.345, 2)") == pytest.approx(2.35)
    assert ev("ROUNDUP(2.01)") == 3
    assert ev("ROUNDUP(2.001, 2)") == pytest.approx(2.01)
    assert ev("CEILING(2.0000000001)") == 2  # tolerance keeps float noise from rounding up
    assert ev("CEILING(2.1)") == 3
    assert ev("FLOOR(2.9)") == 2
    assert ev("ABS(-4)") == 4


def test_errors():
    with pytest.raises(FormulaError, match="Division by zero"):
        ev("1 / 0")
    with pytest.raises(FormulaError, match="wrong number"):
        ev("IF(1, 2)")
    with pytest.raises(FormulaError, match="Unknown function"):
        ev("FOO(1)")
    with pytest.raises(FormulaError, match="closing quote"):
        ev('"abc')
    with pytest.raises(FormulaError, match="matching"):
        ev("1 if x == 1", x=1)
    with pytest.raises(FormulaError, match="missing"):
        ev("2 3")
    with pytest.raises(FormulaError, match="Text"):
        ev('"a" + 1')


def test_if_as_function_name_not_keyword():
    # `if(` is the function; `x if c else y` is the keyword form; both in one formula
    assert ev("IF(x > 1, 10, 20) if y == 1 else 0", x=2, y=1) == 10


# ---------------------------------------------------------------- static analysis


def test_static_helpers():
    ast = parse('QTY("Power Supplies") * 1.5 + COST("Paint") * 0.1 + Surface_Area')
    assert variables_used(ast) == {"Surface_Area"}
    assert qty_tags_used(ast) == {"power supply"}
    assert cost_tags_used(ast) == {"paint"}
    assert norm_tag("Wires") == norm_tag("Wire") == "wire"
    assert norm_tag("  Power   Supplies ") == "power supply"
    assert is_cost_formula('=COST("Paint") * 0.2')
    assert not is_cost_formula("1,009")
    assert not is_cost_formula(77)
    assert not is_cost_formula(None)


def test_check_formula_messages():
    assert check_formula("Surface_Area * 2", ["Surface_Area"]) is None
    assert check_formula("Surface_Area * 2", ["Other"]) == "Unknown input “Surface_Area”"
    assert "QTY needs" in check_formula("QTY(Power)", [])
    assert "closing quote" in check_formula('"x', [])


# ---------------------------------------------------------------- template calculation


METAL_WITH_BACKLIT_PARAMS = [
    ParamSpec("Crunched_Area_Aluminum_ft2"),
    ParamSpec("Crunched_Area_SS_ft2"),
    ParamSpec("Returns_Alu_in"),
    ParamSpec("Returns_SS_in"),
    ParamSpec("LOC_of_Alu_Ft"),
    ParamSpec("LOC_of_SS_Ft"),
    ParamSpec("Surface_Area"),
    ParamSpec("Number_of_Connections"),
    ParamSpec("Finish", "select", ["Matt", "Gloss", "Satin"]),
]

P = "((Surface_Area * 2) + (((LOC_of_Alu_Ft * Returns_Alu_in / 12) + (LOC_of_SS_Ft * Returns_SS_in / 12)) * 2))"


def metal_lines():
    L = LineSpec
    return [
        L(1, "SS Metal 14g", "Crunched_Area_SS_ft2 * 1.2", 77, "Metal"),
        L(2, "SS Metal 26g Silver Brushed", "(Returns_SS_in * LOC_of_SS_Ft * 1.2) / 12", 260, "Metal"),
        L(3, "Aluminium 2.5mm 1100 grade", "Crunched_Area_Aluminum_ft2 * 1.2", 1030, "Metal"),
        L(4, "Aluminium 1.5mm", "(LOC_of_Alu_Ft * Returns_Alu_in * 1.2) / 12", 631, "Metal"),
        L(5, "Acrylic White 8mm Matt", "(Crunched_Area_SS_ft2 * 1.2) + (Crunched_Area_Aluminum_ft2 * 1.2)", 1009, "Acrylic"),
        L(6, "Tanka Nozzle", "(LOC_of_SS_Ft * 7) / 1000", 8000, "Misc"),
        L(7, "Led Strips UL 6500k China", "(LOC_of_Alu_Ft + LOC_of_SS_Ft) * 1.2 / 3.4", 362, "LEDs"),
        L(8, "JUL Power Supply 120W", "1", 7000, "Power Supply"),
        L(9, "Wire UL 18 Gauge", "Number_of_Connections * 1.5", 151, "Wire"),
        L(10, "Epoxy Aster Gray Colour", P + " * 40.49 * 0.71", 2, "Paint"),
        L(11, "Master Thinner", P + " * 40.49 * 0.15", 1, "Paint"),
        L(12, "Nexa Hardner 922", P + " * 40.49 * 0.14", 4, "Paint"),
        L(13, "Nexa 2k HS Jet Black", P + ' * 22 * 0.42 if Finish == "Matt" else 0', 8, "Paint"),
        L(21, "Nexa 2k HS Jet Black", P + ' * 22 * 0.45 if Finish == "Satin" else 0', 8, "Paint"),
        L(22, "Nexa 2K Matting Agent", P + ' * 22 * 0.14 if Finish == "Satin" else 0', 5, "Paint"),
        L(23, "Nexa 2k Adjuster", P + ' * 22 * 0.09 if Finish == "Satin" else 0', 8, "Paint"),
        L(24, "Nexa Hardner 922", P + ' * 22 * 0.23 if Finish == "Satin" else 0', 7, "Paint"),
        L(25, "Nexa 2k Thinner Fast", P + ' * 22 * 0.09 if Finish == "Satin" else 0', 2, "Paint"),
    ]


def test_metal_with_backlit_matches_bom_check_cached_values():
    """Inputs are the ones sitting in BOM_Check.xlsx '01 - Metal - With Backlit' (all 1, Alu area blank, Satin).
    Expected numbers are the sheet's cached cell values."""
    raw = {
        "Crunched_Area_Aluminum_ft2": "",
        "Crunched_Area_SS_ft2": 1,
        "Returns_Alu_in": 1,
        "Returns_SS_in": 1,
        "LOC_of_Alu_Ft": 1,
        "LOC_of_SS_Ft": 1,
        "Surface_Area": 1,
        "Number_of_Connections": 1,
        "Finish": "Satin",
    }
    r = calculate(METAL_WITH_BACKLIT_PARAMS, metal_lines(), raw)
    assert not r.has_errors
    q = {ln.key: ln.qty_final for ln in r.lines}
    assert q[2] == pytest.approx(0.1)
    assert q[3] == 0
    assert q[4] == pytest.approx(0.1)
    assert q[5] == pytest.approx(1.2)
    assert q[6] == pytest.approx(0.007)
    assert q[7] == pytest.approx(0.7058823529)
    assert q[9] == pytest.approx(1.5)
    assert q[10] == pytest.approx(67.07843333, rel=1e-6)
    assert q[11] == pytest.approx(14.1715, rel=1e-6)
    assert q[12] == pytest.approx(13.22673333, rel=1e-6)
    assert q[13] == 0  # Matt line off when Satin
    assert q[21] == pytest.approx(23.1, rel=1e-6)
    assert q[22] == pytest.approx(7.186666667, rel=1e-6)
    assert q[23] == pytest.approx(4.62, rel=1e-6)
    assert q[24] == pytest.approx(11.80666667, rel=1e-6)
    assert q[25] == pytest.approx(4.62, rel=1e-6)
    assert r.by_tag["Power Supply"] == 7000


def test_qty_and_cost_cross_line_dependencies():
    params = [ParamSpec("Connections")]
    lines = [
        LineSpec("ps", "Power Supply", "IF(Connections > 10, 2, 1)", 7000, "Power Supply"),
        LineSpec("cord", "Cord Wire", 'QTY("Power Supply")', 150, "Wires"),
        LineSpec("p1", "Primer", "10", 2, "Paint"),
        LineSpec("p2", "Thinner", "5", 1, "Paint"),
        # unit cost is a formula: 20% of the *other* paint lines (10*2 + 5*1 = 25) -> 5 per unit
        LineSpec("pm", "Paint Misc", "1", '=COST("Paint") * 0.2', "Paint"),
    ]
    r = calculate(params, lines, {"Connections": 12})
    assert not r.has_errors
    by = {ln.key: ln for ln in r.lines}
    assert by["ps"].qty_final == 2
    assert by["cord"].qty_final == 2  # follows the power-supply quantity
    assert by["pm"].unit_cost == pytest.approx(5.0)
    assert by["pm"].unit_cost_is_formula
    assert r.by_tag["Paint"] == pytest.approx(25 + 5)


def test_override_feeds_qty_lookup():
    params = [ParamSpec("x")]
    lines = [
        LineSpec("ps", "Power Supply", "1", 7000, "Power Supply"),
        LineSpec("cord", "Cord Wire", 'QTY("Power Supply")', 150, "Wires"),
    ]
    r = calculate(params, lines, {"x": 1}, overrides={"ps": 3})
    by = {ln.key: ln for ln in r.lines}
    assert by["ps"].qty_auto == 1 and by["ps"].qty_final == 3 and by["ps"].overridden
    assert by["cord"].qty_final == 3


def test_extra_lines_count_toward_tags():
    lines = [LineSpec("cord", "Cord Wire", 'QTY("Power Supply")', 150, "Wires")]
    r = calculate([], lines, {}, extra_lines=[("Power Supply", 2, 7000)])
    assert r.lines[0].qty_final == 2


def test_self_reference_and_cycles_are_reported_not_crashed():
    lines = [
        LineSpec("a", "A", 'QTY("B")', 1, "A"),
        LineSpec("b", "B", 'QTY("A")', 1, "B"),
        LineSpec("c", "C", 'QTY("C") + 1', 1, "C"),
    ]
    r = calculate([], lines, {})
    by = {ln.key: ln for ln in r.lines}
    assert "circle" in by["a"].error and "circle" in by["b"].error
    assert "itself" in by["c"].error


def test_input_validation():
    params = [ParamSpec("n"), ParamSpec("f", "select", ["Matt", "Gloss"])]
    r = calculate(params, [LineSpec(1, "x", "n * 2", 1, "Misc")], {"n": "abc", "f": ""})
    assert r.input_errors == {"n": "Enter a number"}
    r = calculate(params, [LineSpec(1, "x", "n * 2", 1, "Misc")], {"n": -1})
    assert r.input_errors == {"n": "Can’t be negative"}
    r = calculate(params, [LineSpec(1, "x", '1 if f == "Matt" else 0', 1, "Misc")], {"f": ""})
    assert r.lines[0].qty_final == 1  # blank select defaults to the first option


def test_order_vars_available_unless_shadowed():
    ov = order_vars(24, 12)
    assert ov["Area_sqft"] == pytest.approx(2.0)
    r = calculate([], [LineSpec(1, "x", "Area_sqft * 2", 1, "Misc")], {}, extra_vars=ov)
    assert r.lines[0].qty_final == pytest.approx(4.0)
    # a template parameter with the same name wins over the order var
    r = calculate([ParamSpec("Area_sqft")], [LineSpec(1, "x", "Area_sqft", 1, "Misc")], {"Area_sqft": 9}, extra_vars=ov)
    assert r.lines[0].qty_final == 9


def test_unit_cost_strings_with_commas():
    r = calculate([], [LineSpec(1, "x", "2", "1,009", "Acrylic")], {})
    assert r.lines[0].unit_cost == 1009 and r.lines[0].total == 2018
    assert not math.isnan(r.base_total)
