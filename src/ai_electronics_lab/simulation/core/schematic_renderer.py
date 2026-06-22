from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from xml.sax.saxutils import escape

from .schematic_layout import (
    SchematicComponentLayout,
    SchematicLayout,
    SchematicPortLayout,
    SchematicTextLabel,
    SchematicWireSegment,
)

__all__ = ["render_schematic_svg", "render_engineering_schematic_svg", "build_engineering_schematic_svg"]


def render_schematic_svg(layout: SchematicLayout) -> str:
    width = 1180
    height = 470
    layout_strategy = str(layout.metadata.get("layout_strategy", "deterministic_layout_ir"))
    title_text = "RC low-pass schematic" if layout.source_circuit_graph_id == "rc_low_pass" else "Schematic layout"
    subtitle_text = (
        f"Layout IR {layout.layout_id} · source graph {layout.source_circuit_graph_id} · {layout_strategy}"
    )

    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" class="schematic-canvas" role="img" aria-label="{escape(title_text)}" data-layout-id="{escape(layout.layout_id)}" data-source-graph-id="{escape(layout.source_circuit_graph_id)}" data-layout-strategy="{escape(layout_strategy)}">',
        "<defs>",
        "<linearGradient id='layoutBg' x1='0' x2='1'><stop offset='0%' stop-color='#0f172a'/><stop offset='100%' stop-color='#111827'/></linearGradient>",
        "<marker id='arrowHead' markerWidth='10' markerHeight='8' refX='8' refY='4' orient='auto'><path d='M 0 0 L 8 4 L 0 8 z' fill='#64748b'/></marker>",
        "</defs>",
        f"<metadata id='schematic-layout-metadata'>{escape(_layout_metadata_json(layout))}</metadata>",
        "<rect x='0' y='0' width='100%' height='100%' rx='20' fill='url(#layoutBg)'/>",
        f"<text x='34' y='48' fill='#f8fafc' font-size='30' font-family='system-ui, sans-serif' paint-order='stroke fill' stroke='#08101f' stroke-width='3'>{escape(title_text)}</text>",
        f"<text x='34' y='82' fill='#cbd5e1' font-size='17' font-family='system-ui, sans-serif' paint-order='stroke fill' stroke='#08101f' stroke-width='3'>{escape(subtitle_text)}</text>",
    ]

    for wire in sorted(layout.wires, key=lambda item: item.wire_id):
        body.append(_render_wire_segment(wire))

    for component in sorted(layout.component_instances, key=lambda item: item.refdes):
        body.extend(_render_component(component))

    for port in sorted(layout.ports, key=_port_sort_key):
        body.extend(_render_port(port))

    for node in sorted(layout.nodes, key=lambda item: item.node_id):
        body.append(
            f"<circle cx='{node.x:.1f}' cy='{node.y:.1f}' r='5.5' fill='#f8fafc' stroke='#f8fafc' stroke-width='1.0' class='node-dot' data-net='{escape(node.net)}' data-node-id='{escape(node.node_id)}'/>"
        )

    for label in sorted(layout.labels, key=_label_sort_key):
        body.append(_render_label(label))

    body.append("<line x1='34' y1='396' x2='1146' y2='396' stroke='#1f2937' stroke-width='1.4' class='info-separator'/>")
    body.append(
        f"<text x='34' y='428' fill='#e2e8f0' font-size='15' font-family='monospace' paint-order='stroke fill' stroke='#08101f' stroke-width='3'>Layout checks: {escape(_summarize_checks(layout))}</text>"
    )
    body.append(
        f"<text x='34' y='452' fill='#94a3b8' font-size='14' font-family='monospace' paint-order='stroke fill' stroke='#08101f' stroke-width='3'>Topological source graph: {escape(layout.source_circuit_graph_id)} · deterministic layout IR</text>"
    )
    body.append("</svg>")
    return "\n".join(body)


def _render_wire_segment(wire: SchematicWireSegment) -> str:
    stroke = "#f8fafc" if wire.role != "reference" else "#cbd5e1"
    dash = "" if wire.role != "reference" else " stroke-dasharray='6 5'"
    return (
        f"<line class=\"wire\" data-net='{escape(wire.net)}' data-wire-id='{escape(wire.wire_id)}' "
        f"x1='{wire.x1:.1f}' y1='{wire.y1:.1f}' x2='{wire.x2:.1f}' y2='{wire.y2:.1f}' stroke='{stroke}' stroke-width='4' stroke-linecap='round'{dash}/>"
    )


def _render_port(port: SchematicPortLayout) -> list[str]:
    if port.role == "ground" or port.side == "bottom":
        return _render_ground_symbol(
            x=port.x,
            y=port.y,
            label=f"{port.name}",
            class_name="ground-symbol",
            data_name=port.name,
        )
    if port.role == "probe" or port.side == "probe":
        return _render_probe_symbol(port.x, port.y, port.name)
    if port.side == "left":
        return [
            f"<circle class=\"input-port-symbol\" cx='{port.x:.1f}' cy='{port.y:.1f}' r='18' fill='none' stroke='#f8fafc' stroke-width='4' data-port='{escape(port.name)}'/>"
        ]
    if port.side == "right":
        return [
            f"<circle class=\"output-port-symbol\" cx='{port.x:.1f}' cy='{port.y:.1f}' r='5.5' fill='#f8fafc' stroke='#f8fafc' stroke-width='1.0' data-port='{escape(port.name)}'/>"
        ]
    return [
        f"<circle class=\"output-port-symbol\" cx='{port.x:.1f}' cy='{port.y:.1f}' r='5.5' fill='#f8fafc' stroke='#f8fafc' stroke-width='1.0' data-port='{escape(port.name)}'/>"
    ]


def _render_component(component: SchematicComponentLayout) -> list[str]:
    symbol = component.symbol.lower()
    if symbol == "resistor":
        return _render_resistor(component)
    if symbol == "capacitor":
        return _render_capacitor(component)
    if symbol in {"voltage_source", "vsource", "voltage-source"}:
        return _render_voltage_source(component)
    if symbol in {"ground", "reference"}:
        return _render_ground_component(component)
    if symbol == "probe":
        return _render_probe_symbol(component.x + component.width / 2.0, component.y + component.height / 2.0, component.refdes)
    return [
        f"<rect x='{component.x:.1f}' y='{component.y:.1f}' width='{component.width:.1f}' height='{component.height:.1f}' fill='none' opacity='0' data-refdes='{escape(component.refdes)}' data-symbol='{escape(component.symbol)}' data-kind='{escape(component.kind)}'/>",
    ]


def _render_resistor(component: SchematicComponentLayout) -> list[str]:
    if len(component.terminals) < 2:
        return [
            f"<rect x='{component.x:.1f}' y='{component.y:.1f}' width='{component.width:.1f}' height='{component.height:.1f}' fill='none' opacity='0' data-refdes='{escape(component.refdes)}' data-symbol='resistor'/>"
        ]
    left, right = component.terminals[0], component.terminals[1]
    points = _zigzag_points((left.x, left.y), (right.x, right.y), segments=6, amplitude=14.0)
    body = [
        f"<polyline class=\"resistor-symbol\" points='{_format_points(points)}' fill='none' stroke='#f8fafc' stroke-width='4' paint-order='stroke fill' data-refdes='{escape(component.refdes)}' data-symbol='resistor'/>",
        f"<line class=\"resistor-symbol\" x1='{left.x:.1f}' y1='{left.y:.1f}' x2='{points[0][0]:.1f}' y2='{points[0][1]:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
        f"<line class=\"resistor-symbol\" x1='{points[-1][0]:.1f}' y1='{points[-1][1]:.1f}' x2='{right.x:.1f}' y2='{right.y:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
    ]
    body.append(
        f"<rect x='{component.x:.1f}' y='{component.y:.1f}' width='{component.width:.1f}' height='{component.height:.1f}' fill='none' opacity='0' data-refdes='{escape(component.refdes)}' data-kind='{escape(component.kind)}'/>"
    )
    return body


def _render_capacitor(component: SchematicComponentLayout) -> list[str]:
    if len(component.terminals) < 2:
        return [
            f"<rect x='{component.x:.1f}' y='{component.y:.1f}' width='{component.width:.1f}' height='{component.height:.1f}' fill='none' opacity='0' data-refdes='{escape(component.refdes)}' data-symbol='capacitor'/>"
        ]
    t1, t2 = component.terminals[0], component.terminals[1]
    vertical = abs(t1.y - t2.y) >= abs(t1.x - t2.x)
    body: list[str] = []
    if vertical:
        top, bottom = (t1, t2) if t1.y <= t2.y else (t2, t1)
        center_x = (t1.x + t2.x) / 2.0
        plate_top_y = top.y + max(10.0, (bottom.y - top.y) * 0.25)
        plate_bottom_y = bottom.y - max(10.0, (bottom.y - top.y) * 0.25)
        plate_half_width = 26.0
        body.extend(
            [
                f"<line class=\"capacitor-symbol\" x1='{top.x:.1f}' y1='{top.y:.1f}' x2='{top.x:.1f}' y2='{plate_top_y:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
                f"<line class=\"capacitor-symbol\" x1='{center_x - plate_half_width:.1f}' y1='{plate_top_y:.1f}' x2='{center_x + plate_half_width:.1f}' y2='{plate_top_y:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
                f"<line class=\"capacitor-symbol\" x1='{center_x - plate_half_width:.1f}' y1='{plate_bottom_y:.1f}' x2='{center_x + plate_half_width:.1f}' y2='{plate_bottom_y:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
                f"<line class=\"capacitor-symbol\" x1='{bottom.x:.1f}' y1='{plate_bottom_y:.1f}' x2='{bottom.x:.1f}' y2='{bottom.y:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
            ]
        )
    else:
        left, right = (t1, t2) if t1.x <= t2.x else (t2, t1)
        center_y = (t1.y + t2.y) / 2.0
        plate_left_x = left.x + max(10.0, (right.x - left.x) * 0.25)
        plate_right_x = right.x - max(10.0, (right.x - left.x) * 0.25)
        plate_half_height = 26.0
        body.extend(
            [
                f"<line class=\"capacitor-symbol\" x1='{left.x:.1f}' y1='{left.y:.1f}' x2='{plate_left_x:.1f}' y2='{left.y:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
                f"<line class=\"capacitor-symbol\" x1='{plate_left_x:.1f}' y1='{center_y - plate_half_height:.1f}' x2='{plate_left_x:.1f}' y2='{center_y + plate_half_height:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
                f"<line class=\"capacitor-symbol\" x1='{plate_right_x:.1f}' y1='{center_y - plate_half_height:.1f}' x2='{plate_right_x:.1f}' y2='{center_y + plate_half_height:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
                f"<line class=\"capacitor-symbol\" x1='{plate_right_x:.1f}' y1='{right.y:.1f}' x2='{right.x:.1f}' y2='{right.y:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
            ]
        )
    body.append(
        f"<rect x='{component.x:.1f}' y='{component.y:.1f}' width='{component.width:.1f}' height='{component.height:.1f}' fill='none' opacity='0' data-refdes='{escape(component.refdes)}' data-kind='{escape(component.kind)}' data-symbol='capacitor'/>"
    )
    return body


def _render_voltage_source(component: SchematicComponentLayout) -> list[str]:
    if len(component.terminals) < 2:
        return [
            f"<rect x='{component.x:.1f}' y='{component.y:.1f}' width='{component.width:.1f}' height='{component.height:.1f}' fill='none' opacity='0' data-refdes='{escape(component.refdes)}' data-symbol='voltage_source'/>"
        ]
    t1, t2 = component.terminals[0], component.terminals[1]
    vertical = abs(t1.y - t2.y) >= abs(t1.x - t2.x)
    body: list[str] = []
    if vertical:
        top, bottom = (t1, t2) if t1.y <= t2.y else (t2, t1)
        center_x = (t1.x + t2.x) / 2.0
        center_y = (top.y + bottom.y) / 2.0
        radius = min(28.0, max(18.0, abs(bottom.y - top.y) / 4.0))
        body.extend(
            [
                f"<line class=\"voltage-source-symbol\" x1='{center_x:.1f}' y1='{top.y:.1f}' x2='{center_x:.1f}' y2='{center_y - radius:.1f}' stroke='#cbd5e1' stroke-width='4' stroke-linecap='round'/>",
                f"<circle class=\"voltage-source-symbol\" cx='{center_x:.1f}' cy='{center_y:.1f}' r='{radius:.1f}' fill='none' stroke='#cbd5e1' stroke-width='4'/>",
                f"<line class=\"voltage-source-symbol\" x1='{center_x:.1f}' y1='{center_y + radius:.1f}' x2='{center_x:.1f}' y2='{bottom.y:.1f}' stroke='#cbd5e1' stroke-width='4' stroke-linecap='round'/>",
                f"<line class=\"voltage-source-symbol\" x1='{center_x - 8:.1f}' y1='{center_y - 14:.1f}' x2='{center_x + 8:.1f}' y2='{center_y - 14:.1f}' stroke='#cbd5e1' stroke-width='3' stroke-linecap='round'/>",
                f"<line class=\"voltage-source-symbol\" x1='{center_x:.1f}' y1='{center_y - 22:.1f}' x2='{center_x:.1f}' y2='{center_y - 6:.1f}' stroke='#cbd5e1' stroke-width='3' stroke-linecap='round'/>",
                f"<line class=\"voltage-source-symbol\" x1='{center_x - 8:.1f}' y1='{center_y + 14:.1f}' x2='{center_x + 8:.1f}' y2='{center_y + 14:.1f}' stroke='#cbd5e1' stroke-width='3' stroke-linecap='round'/>",
            ]
        )
    else:
        left, right = (t1, t2) if t1.x <= t2.x else (t2, t1)
        center_x = (left.x + right.x) / 2.0
        center_y = (t1.y + t2.y) / 2.0
        radius = min(28.0, max(18.0, abs(right.x - left.x) / 4.0))
        body.extend(
            [
                f"<line class=\"voltage-source-symbol\" x1='{left.x:.1f}' y1='{center_y:.1f}' x2='{center_x - radius:.1f}' y2='{center_y:.1f}' stroke='#cbd5e1' stroke-width='4' stroke-linecap='round'/>",
                f"<circle class=\"voltage-source-symbol\" cx='{center_x:.1f}' cy='{center_y:.1f}' r='{radius:.1f}' fill='none' stroke='#cbd5e1' stroke-width='4'/>",
                f"<line class=\"voltage-source-symbol\" x1='{center_x + radius:.1f}' y1='{center_y:.1f}' x2='{right.x:.1f}' y2='{center_y:.1f}' stroke='#cbd5e1' stroke-width='4' stroke-linecap='round'/>",
                f"<line class=\"voltage-source-symbol\" x1='{center_x - 14:.1f}' y1='{center_y - 8:.1f}' x2='{center_x - 14:.1f}' y2='{center_y + 8:.1f}' stroke='#cbd5e1' stroke-width='3' stroke-linecap='round'/>",
                f"<line class=\"voltage-source-symbol\" x1='{center_x - 22:.1f}' y1='{center_y:.1f}' x2='{center_x - 6:.1f}' y2='{center_y:.1f}' stroke='#cbd5e1' stroke-width='3' stroke-linecap='round'/>",
                f"<line class=\"voltage-source-symbol\" x1='{center_x + 6:.1f}' y1='{center_y - 8:.1f}' x2='{center_x + 22:.1f}' y2='{center_y - 8:.1f}' stroke='#cbd5e1' stroke-width='3' stroke-linecap='round'/>",
                f"<line class=\"voltage-source-symbol\" x1='{center_x + 6:.1f}' y1='{center_y + 8:.1f}' x2='{center_x + 22:.1f}' y2='{center_y + 8:.1f}' stroke='#cbd5e1' stroke-width='3' stroke-linecap='round'/>",
            ]
        )
    body.append(
        f"<rect x='{component.x:.1f}' y='{component.y:.1f}' width='{component.width:.1f}' height='{component.height:.1f}' fill='none' opacity='0' data-refdes='{escape(component.refdes)}' data-kind='{escape(component.kind)}' data-symbol='voltage_source'/>"
    )
    return body


def _render_ground_component(component: SchematicComponentLayout) -> list[str]:
    if not component.terminals:
        return [
            f"<rect x='{component.x:.1f}' y='{component.y:.1f}' width='{component.width:.1f}' height='{component.height:.1f}' fill='none' opacity='0' data-refdes='{escape(component.refdes)}' data-symbol='ground'/>"
        ]
    terminal = component.terminals[0]
    return _render_ground_symbol(
        x=terminal.x,
        y=terminal.y,
        label=component.refdes,
        class_name="ground-symbol",
        data_name=component.refdes,
    )


def _render_ground_symbol(*, x: float, y: float, label: str, class_name: str, data_name: str) -> list[str]:
    return [
        f"<g class=\"{class_name}\" data-name='{escape(data_name)}'>",
        f"<line x1='{x:.1f}' y1='{y:.1f}' x2='{x:.1f}' y2='{y + 14:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
        f"<line x1='{x - 16:.1f}' y1='{y + 16:.1f}' x2='{x + 16:.1f}' y2='{y + 16:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
        f"<line x1='{x - 11:.1f}' y1='{y + 24:.1f}' x2='{x + 11:.1f}' y2='{y + 24:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
        f"<line x1='{x - 6:.1f}' y1='{y + 32:.1f}' x2='{x + 6:.1f}' y2='{y + 32:.1f}' stroke='#f8fafc' stroke-width='4' stroke-linecap='round'/>",
        f"<circle cx='{x:.1f}' cy='{y:.1f}' r='5.5' fill='#f8fafc' stroke='#f8fafc' stroke-width='1.0'/>",
        f"</g>",
    ]


def _render_probe_symbol(x: float, y: float, label: str) -> list[str]:
    return [
        f"<g class=\"probe-symbol\" data-name='{escape(label)}'>",
        f"<circle cx='{x:.1f}' cy='{y:.1f}' r='12' fill='none' stroke='#f8fafc' stroke-width='3'/>",
        f"<path d='M {x - 5:.1f} {y:.1f} L {x + 7:.1f} {y:.1f} M {x + 2:.1f} {y - 5:.1f} L {x + 7:.1f} {y:.1f} L {x + 2:.1f} {y + 5:.1f}' fill='none' stroke='#f8fafc' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/>",
        f"</g>",
    ]


def _label_sort_key(label: SchematicTextLabel) -> tuple[int, str, str]:
    return (_label_role_rank(label.role), label.anchor, label.text)


def _label_role_rank(role: str) -> int:
    ordering = {
        "port-label": 0,
        "designator": 1,
        "value": 2,
        "note": 3,
        "annotation": 4,
    }
    return ordering.get(role, 5)


def _port_sort_key(port: SchematicPortLayout) -> tuple[int, str]:
    ordering = {
        "left": 0,
        "top": 1,
        "right": 2,
        "bottom": 3,
        "probe": 4,
    }
    return (ordering.get(port.side, 9), port.name)


def _render_label(label: SchematicTextLabel) -> str:
    anchor = escape(label.anchor)
    fill = "#f8fafc" if label.role in {"designator", "port-label", "note"} else "#cbd5e1"
    font_size = 15 if label.role in {"designator", "port-label"} else (14 if label.role == "note" else 11)
    text = escape(label.text)
    estimated_width = max(72.0, len(label.text) * (font_size * 0.56) + 18.0)
    estimated_height = 22.0 if label.role in {"designator", "port-label"} else 20.0
    if label.anchor == "end":
        box_x = label.x - estimated_width
        text_x = label.x
        leader_x = label.x - 10.0
    elif label.anchor == "middle":
        box_x = label.x - estimated_width / 2.0
        text_x = label.x
        leader_x = label.x
    else:
        box_x = label.x - 8.0
        text_x = label.x
        leader_x = label.x + 10.0
    box_y = label.y - estimated_height + 4.0
    leader_y = label.y - 7.0
    css_class = _label_css_class(label)
    leader = ""
    if label.role != "note":
        leader = (
            f"<line class=\"annotation-leader\" x1='{leader_x:.1f}' y1='{leader_y:.1f}' x2='{label.x:.1f}' y2='{label.y:.1f}' stroke='#64748b' stroke-width='1.6' stroke-linecap='round'/>"
        )
    return (
        f"<g class=\"label-group\" data-label-role=\"{escape(label.role)}\">"
        f"{leader}"
        f"<rect class=\"annotation-box\" x='{box_x:.1f}' y='{box_y:.1f}' width='{estimated_width:.1f}' height='{estimated_height:.1f}' rx='8' ry='8' fill='#0f172a' fill-opacity='0.82' stroke='#334155' stroke-width='1.2'/>"
        f"<text class=\"{escape(css_class)}\" x=\"{text_x:.1f}\" y=\"{label.y:.1f}\" fill=\"{fill}\" font-size=\"{font_size}\" font-family=\"monospace\" text-anchor=\"{anchor}\" paint-order='stroke fill' stroke='#08101f' stroke-width='3' stroke-linejoin='round'>{text}</text>"
        f"</g>"
    )


def _label_css_class(label: SchematicTextLabel) -> str:
    if label.role == "port-label":
        port_name = str(label.metadata.get("port", "")).lower()
        if port_name == "vin":
            return "input-port-label"
        if port_name == "vout":
            return "output-port-label"
        if port_name in {"0", "gnd", "ground"}:
            return "ground-label"
        return "port-label"
    if label.role == "designator":
        if label.text.startswith("R"):
            return "resistor-label"
        if label.text.startswith("C"):
            return "capacitor-label"
        return "designator"
    if label.role == "note":
        return "note-label"
    return label.role


def _summarize_checks(layout: SchematicLayout) -> str:
    passed = sum(1 for check in layout.checks if check.passed)
    total = len(layout.checks)
    failures = [check.name for check in layout.checks if not check.passed]
    if failures:
        return f"{passed}/{total} passed; failed: {', '.join(failures)}"
    return f"{passed}/{total} passed"


def _layout_metadata_json(layout: SchematicLayout) -> str:
    payload = {
        "layout_id": layout.layout_id,
        "source_circuit_graph_id": layout.source_circuit_graph_id,
        "layout_strategy": layout.metadata.get("layout_strategy"),
        "metadata": _sorted_mapping(layout.metadata),
        "checks": [check.to_dict() for check in layout.checks],
    }
    return _json_dumps(payload)


def _json_dumps(payload: Any) -> str:
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sorted_mapping(mapping: Any) -> Any:
    if isinstance(mapping, Mapping):
        return {key: _sorted_mapping(mapping[key]) for key in sorted(mapping)}
    if isinstance(mapping, list):
        return [_sorted_mapping(item) for item in mapping]
    if isinstance(mapping, tuple):
        return [_sorted_mapping(item) for item in mapping]
    return mapping


def _zigzag_points(start: tuple[float, float], end: tuple[float, float], *, segments: int, amplitude: float) -> list[tuple[float, float]]:
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    points: list[tuple[float, float]] = [(x1, y1)]
    if abs(dx) >= abs(dy):
        step = dx / (segments + 1)
        direction = 1.0
        for index in range(1, segments + 1):
            x = x1 + step * index
            y = y1 + (amplitude if index % 2 else -amplitude) * direction
            points.append((x, y))
        points.append((x2, y2))
    else:
        step = dy / (segments + 1)
        direction = 1.0
        for index in range(1, segments + 1):
            y = y1 + step * index
            x = x1 + (amplitude if index % 2 else -amplitude) * direction
            points.append((x, y))
        points.append((x2, y2))
    return points


def _format_points(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _freeze_mapping(mapping: Any) -> dict[str, Any]:
    if isinstance(mapping, dict):
        return {key: mapping[key] for key in sorted(mapping)}
    return dict(mapping)


# ═══════════════════════════════════════════════════════════════════════════════
# Engineering-style schematic renderer (monochrome, no decorative elements)
# ═══════════════════════════════════════════════════════════════════════════════

_ENG_WIDTH = 800
_ENG_HEIGHT = 360
_ENG_MARGIN_L = 60
_ENG_MARGIN_R = 60
_ENG_MARGIN_T = 60
_ENG_MARGIN_B = 60
_ENG_STROKE = "#1a1a2e"
_ENG_STROKE_W = 3
_ENG_FILL = "#ffffff"
_ENG_TEXT = "#1a1a2e"
_ENG_LABEL_FILL = "#334155"


def render_engineering_schematic_svg(
    topology_id: str,
    components: dict[str, float],
    *,
    width: int = _ENG_WIDTH,
    height: int = _ENG_HEIGHT,
) -> str:
    """Render an engineering-style monochrome schematic SVG for passive topologies.

    Produces a clean, monochrome schematic with standard electrical symbols
    (zigzag resistor, parallel-plate capacitor, ground symbol), orthogonal
    wires, explicit port labels, and visible component values.

    Args:
        topology_id: One of ``rc_low_pass``, ``rc_high_pass``, ``resistive_divider``.
        components: Flat component map (e.g. ``{"R1_ohm": 1000.0, "C1_farad": 1e-6}``).
        width: SVG canvas width (default 800).
        height: SVG canvas height (default 360).
    """
    if topology_id == "rc_low_pass":
        return _render_rc_low_pass(components, width, height)
    if topology_id == "rc_high_pass":
        return _render_rc_high_pass(components, width, height)
    if topology_id == "resistive_divider":
        return _render_resistive_divider(components, width, height)
    raise ValueError(f"Unsupported topology for engineering schematic: {topology_id!r}")


def build_engineering_schematic_svg(
    topology_id: str,
    components: dict[str, float],
    *,
    width: int = _ENG_WIDTH,
    height: int = _ENG_HEIGHT,
) -> str:
    """Convenience alias for :func:`render_engineering_schematic_svg`."""
    return render_engineering_schematic_svg(topology_id, components, width=width, height=height)


# ── Topology-specific renderers ──────────────────────────────────────────────

def _render_rc_low_pass(components: dict[str, float], width: int, height: int) -> str:
    r_ohm = components.get("R1_ohm", 0.0)
    c_farad = components.get("C1_farad", 0.0)
    r_label = _eng_format_resistance(r_ohm)
    c_label = _eng_format_capacitance(c_farad)

    # Layout coordinates (all hardcoded for determinism)
    vin_x, vin_y = 40, 180
    r_left_x, r_right_x = 140, 340
    mid_x, mid_y = 420, 180
    vout_x = 700
    c_top_y, c_bottom_y = 180, 290
    gnd_x, gnd_y = 420, 310

    parts: list[str] = []
    parts.append(_eng_svg_open(width, height, "RC Low-Pass Filter"))
    parts.append(_eng_rect_bg(width, height))

    # Wires — orthogonal only
    parts.append(_eng_wire(vin_x, vin_y, r_left_x, vin_y))           # VIN → R1 left
    parts.append(_eng_wire(r_right_x, vin_y, vout_x, vin_y))         # R1 right → VOUT
    parts.append(_eng_wire(mid_x, mid_y, mid_x, c_top_y))            # Junction → C1 top
    parts.append(_eng_wire(mid_x, c_bottom_y, mid_x, gnd_y))         # C1 bottom → GND

    # Resistor R1 (zigzag)
    parts.extend(_eng_resistor(r_left_x, vin_y, r_right_x, vin_y, "R1", r_label))

    # Capacitor C1 (parallel plates)
    parts.extend(_eng_capacitor(mid_x, c_top_y, mid_x, c_bottom_y, "C1", c_label))

    # Ground symbol
    parts.append(_eng_ground(gnd_x, gnd_y, "GND"))

    # Junction dot (at the R1/C1/VOUT node)
    parts.append(_eng_junction_dot(mid_x, mid_y))

    # Port labels
    parts.append(_eng_label_left(vin_x, vin_y - 24, "VIN", "input"))
    parts.append(_eng_label_right(vout_x, vin_y - 24, "VOUT", "output"))

    # Title block
    parts.append(_eng_title_block(width, height, "RC Low-Pass Filter"))

    parts.append("</svg>")
    return "\n".join(parts)


def _render_rc_high_pass(components: dict[str, float], width: int, height: int) -> str:
    r_ohm = components.get("R1_ohm", 0.0)
    c_farad = components.get("C1_farad", 0.0)
    r_label = _eng_format_resistance(r_ohm)
    c_label = _eng_format_capacitance(c_farad)

    vin_x, vin_y = 40, 180
    c_left_x, c_right_x = 140, 280
    mid_x, mid_y = 340, 180
    vout_x = 700
    r_bottom_y = 290
    gnd_x, gnd_y = 340, 310

    parts: list[str] = []
    parts.append(_eng_svg_open(width, height, "RC High-Pass Filter"))
    parts.append(_eng_rect_bg(width, height))

    # Wires
    parts.append(_eng_wire(vin_x, vin_y, c_left_x, vin_y))           # VIN → C1 left
    parts.append(_eng_wire(c_right_x, vin_y, vout_x, vin_y))         # C1 right → VOUT
    parts.append(_eng_wire(mid_x, mid_y, mid_x, r_bottom_y - 60))    # Junction → R1 top

    # Capacitor C1 (series — first component)
    parts.extend(_eng_capacitor(c_left_x, vin_y, c_right_x, vin_y, "C1", c_label))

    # Resistor R1 (shunt to ground)
    parts.extend(_eng_resistor(gnd_x, r_bottom_y, gnd_x, mid_y, "R1", r_label, vertical=True))

    # Ground symbol
    parts.append(_eng_ground(gnd_x, gnd_y, "GND"))

    # Junction dot
    parts.append(_eng_junction_dot(mid_x, mid_y))

    # Port labels
    parts.append(_eng_label_left(vin_x, vin_y - 24, "VIN", "input"))
    parts.append(_eng_label_right(vout_x, vin_y - 24, "VOUT", "output"))

    parts.append(_eng_title_block(width, height, "RC High-Pass Filter"))
    parts.append("</svg>")
    return "\n".join(parts)


def _render_resistive_divider(components: dict[str, float], width: int, height: int) -> str:
    r1_ohm = components.get("R1_ohm", 0.0)
    r2_ohm = components.get("R2_ohm", 0.0)
    r1_label = _eng_format_resistance(r1_ohm)
    r2_label = _eng_format_resistance(r2_ohm)

    vin_x, vin_y = 40, 240
    r1_left_x, r1_right_x = 140, 290
    # Junction = VOUT tap point
    jn_x, jn_y = 360, 240
    vout_x = 700
    # R2 goes vertical from junction down to ground
    r2_bottom_y = 340
    gnd_x, gnd_y = 360, 360

    parts: list[str] = []
    parts.append(_eng_svg_open(width, height, "Resistive Voltage Divider"))
    parts.append(_eng_rect_bg(width, height))

    # Wires — conventional: VIN → R1 → VOUT, R2 vertical from VOUT down to GND
    parts.append(_eng_wire(vin_x, vin_y, r1_left_x, vin_y))           # VIN → R1 left
    parts.append(_eng_wire(r1_right_x, vin_y, vout_x, vin_y))         # R1 right → VOUT
    parts.append(_eng_wire(jn_x, jn_y, jn_x, r2_bottom_y - 60))      # Junction → R2 top

    # Resistor R1 (zigzag, horizontal — series element)
    parts.extend(_eng_resistor(r1_left_x, vin_y, r1_right_x, vin_y, "R1", r1_label))

    # Resistor R2 (zigzag, vertical — from VOUT down to ground)
    parts.extend(_eng_resistor(gnd_x, r2_bottom_y, gnd_x, jn_y, "R2", r2_label, vertical=True))

    # Ground symbol
    parts.append(_eng_ground(gnd_x, gnd_y, "GND"))

    # Junction dot (at R1/R2/VOUT node)
    parts.append(_eng_junction_dot(jn_x, jn_y))

    # Port labels
    parts.append(_eng_label_left(vin_x, vin_y - 24, "VIN", "input"))
    parts.append(_eng_label_right(vout_x, vin_y - 24, "VOUT", "output"))

    parts.append(_eng_title_block(width, height, "Resistive Divider"))
    parts.append("</svg>")
    return "\n".join(parts)


# ── SVG primitive helpers ────────────────────────────────────────────────────

def _eng_svg_open(width: int, height: int, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">'
    )


def _eng_rect_bg(width: int, height: int) -> str:
    return f'<rect x="0" y="0" width="{width}" height="{height}" fill="{_ENG_FILL}" stroke="none"/>'


def _eng_wire(x1: float, y1: float, x2: float, y2: float, *, stroke: str = _ENG_STROKE) -> str:
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{stroke}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>'
    )


def _eng_resistor(
    x1: float, y1: float, x2: float, y2: float,
    refdes: str, value_label: str,
    *,
    vertical: bool = False,
) -> list[str]:
    """Render a zigzag resistor symbol with label."""
    if vertical:
        # Vertical resistor — zigzag along Y axis
        amp = 12.0
        segments = 6
        dy = y2 - y1
        step = dy / (segments + 1)
        zig_points: list[tuple[float, float]] = [(x1, y1)]
        for i in range(1, segments + 1):
            yy = y1 + step * i
            xx = x1 + (amp if i % 2 else -amp)
            zig_points.append((xx, yy))
        zig_points.append((x2, y2))
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zig_points)

        label_x = x1 + 28
        label_y = (y1 + y2) / 2.0
    else:
        # Horizontal resistor — zigzag along X axis
        amp = 12.0
        segments = 6
        dx = x2 - x1
        step = dx / (segments + 1)
        zig_points: list[tuple[float, float]] = [(x1, y1)]
        for i in range(1, segments + 1):
            xx = x1 + step * i
            yy = y1 + (amp if i % 2 else -amp)
            zig_points.append((xx, yy))
        zig_points.append((x2, y2))
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zig_points)

        label_x = (x1 + x2) / 2.0
        label_y = y1 - 26

    return [
        f'<polyline points="{pts}" fill="none" stroke="{_ENG_STROKE}" '
        f'stroke-width="{_ENG_STROKE_W}" stroke-linecap="round" stroke-linejoin="round"/>',
        f'<text x="{label_x:.1f}" y="{label_y:.1f}" fill="{_ENG_TEXT}" '
        f'font-size="15" font-family="monospace" text-anchor="middle">{escape(refdes)}</text>',
        f'<text x="{label_x:.1f}" y="{label_y + 16:.1f}" fill="{_ENG_LABEL_FILL}" '
        f'font-size="12" font-family="monospace" text-anchor="middle">{escape(value_label)}</text>',
    ]


def _eng_capacitor(
    x1: float, y1: float, x2: float, y2: float,
    refdes: str, value_label: str,
) -> list[str]:
    """Render a parallel-plate capacitor symbol with label."""
    vertical = abs(y2 - y1) >= abs(x2 - x1)

    if vertical:
        # Vertical capacitor
        center_x = x1
        plate_half = 28.0
        gap = 10.0
        mid_y = (y1 + y2) / 2.0
        top_plate_y = mid_y - gap / 2.0
        bot_plate_y = mid_y + gap / 2.0

        label_x = center_x + 34
        label_y = mid_y
        return [
            f'<line x1="{center_x:.1f}" y1="{y1:.1f}" x2="{center_x:.1f}" y2="{top_plate_y:.1f}" '
            f'stroke="{_ENG_STROKE}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>',
            f'<line x1="{center_x - plate_half:.1f}" y1="{top_plate_y:.1f}" '
            f'x2="{center_x + plate_half:.1f}" y2="{top_plate_y:.1f}" '
            f'stroke="{_ENG_STROKE}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>',
            f'<line x1="{center_x - plate_half:.1f}" y1="{bot_plate_y:.1f}" '
            f'x2="{center_x + plate_half:.1f}" y2="{bot_plate_y:.1f}" '
            f'stroke="{_ENG_STROKE}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>',
            f'<line x1="{center_x:.1f}" y1="{bot_plate_y:.1f}" x2="{center_x:.1f}" y2="{y2:.1f}" '
            f'stroke="{_ENG_STROKE}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>',
            f'<text x="{label_x:.1f}" y="{label_y - 4:.1f}" fill="{_ENG_TEXT}" '
            f'font-size="15" font-family="monospace">{escape(refdes)}</text>',
            f'<text x="{label_x:.1f}" y="{label_y + 14:.1f}" fill="{_ENG_LABEL_FILL}" '
            f'font-size="12" font-family="monospace">{escape(value_label)}</text>',
        ]
    else:
        # Horizontal capacitor
        center_y = y1
        plate_half = 28.0
        gap = 10.0
        mid_x = (x1 + x2) / 2.0
        left_plate_x = mid_x - gap / 2.0
        right_plate_x = mid_x + gap / 2.0

        label_x = mid_x
        label_y = center_y - 26
        return [
            f'<line x1="{x1:.1f}" y1="{center_y:.1f}" x2="{left_plate_x:.1f}" y2="{center_y:.1f}" '
            f'stroke="{_ENG_STROKE}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>',
            f'<line x1="{left_plate_x:.1f}" y1="{center_y - plate_half:.1f}" '
            f'x2="{left_plate_x:.1f}" y2="{center_y + plate_half:.1f}" '
            f'stroke="{_ENG_STROKE}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>',
            f'<line x1="{right_plate_x:.1f}" y1="{center_y - plate_half:.1f}" '
            f'x2="{right_plate_x:.1f}" y2="{center_y + plate_half:.1f}" '
            f'stroke="{_ENG_STROKE}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>',
            f'<line x1="{right_plate_x:.1f}" y1="{center_y:.1f}" x2="{x2:.1f}" y2="{center_y:.1f}" '
            f'stroke="{_ENG_STROKE}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>',
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" fill="{_ENG_TEXT}" '
            f'font-size="15" font-family="monospace" text-anchor="middle">{escape(refdes)}</text>',
            f'<text x="{label_x:.1f}" y="{label_y + 16:.1f}" fill="{_ENG_LABEL_FILL}" '
            f'font-size="12" font-family="monospace" text-anchor="middle">{escape(value_label)}</text>',
        ]


def _eng_ground(x: float, y: float, label: str) -> str:
    """Render a ground symbol (three descending horizontal lines)."""
    parts = [
        f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{y + 12:.1f}" '
        f'stroke="{_ENG_STROKE}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>',
        f'<line x1="{x - 18:.1f}" y1="{y + 14:.1f}" x2="{x + 18:.1f}" y2="{y + 14:.1f}" '
        f'stroke="{_ENG_STROKE}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>',
        f'<line x1="{x - 12:.1f}" y1="{y + 22:.1f}" x2="{x + 12:.1f}" y2="{y + 22:.1f}" '
        f'stroke="{_ENG_STROKE}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>',
        f'<line x1="{x - 6:.1f}" y1="{y + 30:.1f}" x2="{x + 6:.1f}" y2="{y + 30:.1f}" '
        f'stroke="{_ENG_STROKE}" stroke-width="{_ENG_STROKE_W}" stroke-linecap="round"/>',
        f'<text x="{x:.1f}" y="{y + 52:.1f}" fill="{_ENG_TEXT}" '
        f'font-size="14" font-family="monospace" text-anchor="middle">{escape(label)}</text>',
    ]
    return "\n".join(parts)


def _eng_junction_dot(x: float, y: float) -> str:
    """Render a junction dot (filled circle) at a real electrical junction."""
    return (
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" '
        f'fill="{_ENG_STROKE}" stroke="none"/>'
    )


def _eng_label_left(x: float, y: float, text: str, role: str) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{_ENG_TEXT}" '
        f'font-size="16" font-family="monospace" font-weight="bold" '
        f'text-anchor="start">{escape(text)}</text>'
    )


def _eng_label_right(x: float, y: float, text: str, role: str) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{_ENG_TEXT}" '
        f'font-size="16" font-family="monospace" font-weight="bold" '
        f'text-anchor="end">{escape(text)}</text>'
    )


def _eng_label_above(x: float, y: float, text: str, role: str) -> str:
    return (
        f'<text x="{x:.1f}" y="{y - 10:.1f}" fill="{_ENG_TEXT}" '
        f'font-size="16" font-family="monospace" font-weight="bold" '
        f'text-anchor="middle">{escape(text)}</text>'
    )


def _eng_title_block(width: int, height: int, topology_name: str) -> str:
    """Render a minimal title block at the bottom."""
    y = height - 18
    return (
        f'<text x="{width / 2:.0f}" y="{y:.1f}" fill="{_ENG_LABEL_FILL}" '
        f'font-size="12" font-family="monospace" text-anchor="middle">'
        f'{escape(topology_name)} — engineering schematic</text>'
    )


# ── Engineering value formatters ─────────────────────────────────────────────

def _eng_format_resistance(value: float) -> str:
    if value <= 0:
        return "n/a"
    if value >= 1_000_000:
        return f"{value / 1_000_000:g} MΩ"
    if value >= 1_000:
        return f"{value / 1_000:g} kΩ"
    return f"{value:g} Ω"


def _eng_format_capacitance(value: float) -> str:
    if value <= 0:
        return "n/a"
    if value >= 1e-6:
        return f"{value / 1e-6:g} µF"
    if value >= 1e-9:
        return f"{value / 1e-9:g} nF"
    if value >= 1e-12:
        return f"{value / 1e-12:g} pF"
    return f"{value:g} F"
