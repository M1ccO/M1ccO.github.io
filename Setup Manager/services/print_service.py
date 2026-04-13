from datetime import datetime
from pathlib import Path
import textwrap

from config import DEFAULT_TOOL_ICON, TOOL_ICONS_DIR, TOOL_LIBRARY_TOOL_ICONS_DIR, TOOL_TYPE_TO_ICON


class PrintService:
    _TOOL_CARD_HEIGHT = 22
    _TOOL_CARD_GAP = 4
    _SETUP_AXIS_RGB = {
        "Z": (30 / 255.0, 90 / 255.0, 168 / 255.0),   # #1E5AA8
        "X": (58 / 255.0, 73 / 255.0, 90 / 255.0),    # #3A495A
        "Y": (58 / 255.0, 110 / 255.0, 69 / 255.0),   # #3A6E45
        "C": (201 / 255.0, 106 / 255.0, 18 / 255.0),  # #C96A12
    }
    
    # Monthly color palette - moderate saturation. Each month gets a color for gradient effects.
    _MONTH_COLORS_HEX = [
        "#5B7BA8",  # January - muted blue
        "#8B6B8F",  # February - muted purple
        "#7A9B6B",  # March - muted green
        "#6B8FA8",  # April - muted cyan-blue
        "#A89B6B",  # May - muted gold
        "#9B8B6B",  # June - muted warm brown
        "#6B8FA8",  # July - muted blue-cyan
        "#8A7B9B",  # August - muted purple-blue
        "#8B9B6B",  # September - muted olive
        "#A87B6B",  # October - muted rust
        "#7B8BA8",  # November - muted slate
        "#8B7B6B",  # December - muted brown
    ]
    
    # Header color - light blue
    _LOGBOOK_HEADER_COLOR = "#C5D9F1"  # Light blue for header section

    def __init__(self, app_title="Setup Manager"):
        self.app_title = app_title
        self.reference_service = None
        self._translate = lambda _key, default=None, **_kwargs: default or ''

    def set_reference_service(self, reference_service):
        """Inject draw/reference service for tool+jaw lookups used in PDFs."""
        self.reference_service = reference_service

    def set_translator(self, translate):
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    @staticmethod
    def _row(label, value):
        return [label, value if value not in (None, "") else "-"]

    @staticmethod
    def _safe(value):
        text = "" if value is None else str(value).strip()
        return text if text else "-"

    @staticmethod
    def _to_text(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    @staticmethod
    def _coord_z(coord, z_value):
        coord = PrintService._to_text(coord)
        z_value = PrintService._to_text(z_value)
        if coord and z_value:
            return f"{coord} | {z_value}"
        if z_value:
            return z_value
        if coord:
            return coord
        return "-"

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
        """Convert hex color (#RRGGBB) to RGB tuple with values 0-1."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
        return (r, g, b)

    @staticmethod
    def _blend_rgb(rgb1: tuple[float, float, float], rgb2: tuple[float, float, float], ratio: float) -> tuple[float, float, float]:
        """Blend two RGB colors. ratio=0 gives rgb1, ratio=1 gives rgb2."""
        r = rgb1[0] + (rgb2[0] - rgb1[0]) * ratio
        g = rgb1[1] + (rgb2[1] - rgb1[1]) * ratio
        b = rgb1[2] + (rgb2[2] - rgb1[2]) * ratio
        return (r, g, b)

    @classmethod
    def _get_logbook_color_for_date(cls, date_str: str) -> tuple[float, float, float]:
        """
        Get RGB color for a logbook entry based on the date.
        Gradient: 1st of month (saturated) to last day of month (desaturated).
        """
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            month = date_obj.month - 1  # 0-11
            day = date_obj.day
            
            # Calculate days in the month
            if month == 11:  # December
                next_month = datetime(date_obj.year + 1, 1, 1)
            else:
                next_month = datetime(date_obj.year, month + 2, 1)
            days_in_month = (next_month - datetime(date_obj.year, month + 1, 1)).days
            
            # Base color for the month
            month_color_hex = cls._MONTH_COLORS_HEX[month]
            month_rgb = cls._hex_to_rgb(month_color_hex)
            
            # White color for desaturation
            white_rgb = (1.0, 1.0, 1.0)
            
            # Calculate saturation level: 1st day = 0 (full saturation), last day = 1 (full desaturation)
            saturation_ratio = (day - 1) / max(1, days_in_month - 1)
            
            # Blend from saturated color to white
            result_rgb = cls._blend_rgb(month_rgb, white_rgb, saturation_ratio)
            return result_rgb
        except Exception:
            # Fallback color if date parsing fails
            return cls._hex_to_rgb("#8B8B8B")  # Gray

    def _tool_data(self, tool_id, tool_uid=None):
        tool_id = self._to_text(tool_id)
        if not tool_id:
            return None

        result = {"id": tool_id, "description": "", "tool_type": "", "radius": "", "nose_corner_radius": ""}
        service = self.reference_service
        if service is None:
            return result

        if tool_uid is not None:
            try:
                full_by_uid = service.get_full_tool_by_uid(tool_uid)
            except Exception:
                full_by_uid = None
            if isinstance(full_by_uid, dict):
                result.update(full_by_uid)
                return result

        try:
            full = service.get_full_tool(tool_id)
        except Exception:
            full = None
        if isinstance(full, dict):
            result.update(full)
            return result

        try:
            ref = service.get_tool_ref(tool_id)
        except Exception:
            ref = None
        if isinstance(ref, dict):
            result.update(ref)
        return result

    def _tool_entry_data(self, assignment):
        if not isinstance(assignment, dict):
            tool_id = self._to_text(assignment)
            tool_uid = None
            spindle = "main"
            comment = ""
            pot = ""
            override_id = ""
            override_description = ""
        else:
            tool_id = self._to_text(assignment.get("tool_id") or assignment.get("id"))
            raw_uid = assignment.get("tool_uid", assignment.get("uid"))
            try:
                tool_uid = int(raw_uid) if raw_uid is not None and str(raw_uid).strip() else None
            except Exception:
                tool_uid = None
            spindle = self._to_text(assignment.get("spindle")).lower() or "main"
            comment = self._to_text(assignment.get("comment"))
            pot = self._to_text(assignment.get("pot"))
            override_id = self._to_text(assignment.get("override_id"))
            override_description = self._to_text(assignment.get("override_description"))
        if not tool_id:
            return None

        tool = self._tool_data(tool_id, tool_uid=tool_uid)
        if not tool:
            # Deleted tool – still include it with a placeholder description
            tool = {
                "id": tool_id,
                "description": self._t("work_editor.tools.deleted_tool", "DELETED TOOL"),
                "tool_type": "",
            }
        # Apply overrides
        if override_id:
            tool["id"] = override_id
        if override_description:
            tool["description"] = override_description
        tool["spindle"] = spindle if spindle in {"main", "sub"} else "main"
        tool["comment"] = comment
        tool["pot"] = pot
        return tool

    def _tool_sections_for_head(self, assignments):
        grouped = {"main": [], "sub": []}
        for assignment in assignments or []:
            tool = self._tool_entry_data(assignment)
            if not tool:
                continue
            grouped[tool.get("spindle", "main")].append(tool)

        sections = []
        for spindle_key, title in (
            ("main", self._t("print.setup_card.section.sp1_tools", "SP1 Tools")),
            ("sub", self._t("print.setup_card.section.sp2_tools", "SP2 Tools")),
        ):
            tools = grouped.get(spindle_key) or []
            if tools:
                sections.append({"title": title, "tools": tools})
        return sections

    def _tool_lists_for_head(self, assignments):
        """Return (main_tools, sub_tools) for a head's tool assignments."""
        main_tools, sub_tools = [], []
        for assignment in assignments or []:
            tool = self._tool_entry_data(assignment)
            if not tool:
                continue
            if tool.get("spindle") == "sub":
                sub_tools.append(tool)
            else:
                main_tools.append(tool)
        return main_tools, sub_tools

    def _jaw_details(self, jaw_id):
        jaw_id = self._to_text(jaw_id)
        if not jaw_id or self.reference_service is None:
            return {}
        try:
            full = self.reference_service.get_full_jaw(jaw_id)
        except Exception:
            full = None
        if not isinstance(full, dict):
            return {}
        return {
            "jaw_type": self._to_text(full.get("jaw_type")),
            "turning_washer": self._to_text(full.get("turning_washer")),
            "last_modified": self._to_text(full.get("last_modified")),
        }

    def _jaw_summary(self, jaw_id):
        jaw_id = self._to_text(jaw_id)
        if not jaw_id:
            return self._t("setup_page.field.not_specified", "Not specified")
        return jaw_id

    @staticmethod
    def _wrap_lines(text, width_chars):
        clean = str(text or "").strip()
        if not clean:
            return ["-"]
        wrapped = []
        for raw_line in clean.splitlines() or [clean]:
            line = raw_line.strip()
            if not line:
                wrapped.append("")
                continue
            wrapped.extend(textwrap.wrap(line, width=width_chars) or [line])
        return wrapped or ["-"]

    @staticmethod
    def _is_axis_marker(text: str, index: int) -> bool:
        if index < 0 or index >= len(text):
            return False
        axis = text[index].upper()
        if axis not in PrintService._SETUP_AXIS_RGB:
            return False
        if index + 1 >= len(text):
            return False
        next_char = text[index + 1]
        if not (next_char.isdigit() or next_char in "+-."):
            return False
        prev_char = text[index - 1] if index > 0 else " "
        return not prev_char.isalpha()

    def _draw_text_with_axis_colors(self, canvas, x, y, text, *, font_name, font_size):
        base_rgb = (0.14, 0.18, 0.22)
        content = str(text or "")
        cursor = x
        start = 0
        index = 0

        canvas.setFillColorRGB(*base_rgb)
        canvas.setFont(font_name, font_size)

        while index < len(content):
            if self._is_axis_marker(content, index):
                if index > start:
                    chunk = content[start:index]
                    canvas.drawString(cursor, y, chunk)
                    cursor += canvas.stringWidth(chunk, font_name, font_size)

                axis = content[index].upper()
                r, g, b = self._SETUP_AXIS_RGB[axis]
                canvas.setFillColorRGB(r, g, b)
                canvas.setFont("Helvetica-Bold", font_size)
                canvas.drawString(cursor, y, axis)
                cursor += canvas.stringWidth(axis, "Helvetica-Bold", font_size)

                canvas.setFillColorRGB(*base_rgb)
                canvas.setFont(font_name, font_size)
                index += 1
                start = index
                continue
            index += 1

        if start < len(content):
            chunk = content[start:]
            canvas.drawString(cursor, y, chunk)

    def _draw_label_value_line(
        self,
        canvas,
        x,
        y,
        line,
        *,
        label_font_name,
        label_font_size,
        value_font_name,
        value_font_size,
        colorize_axis_letters=False,
    ):
        base_rgb = (0.14, 0.18, 0.22)
        text = str(line or "")
        if ":" not in text:
            canvas.setFillColorRGB(*base_rgb)
            canvas.setFont(label_font_name, label_font_size)
            canvas.drawString(x, y, text)
            return

        label_raw, value_raw = text.split(":", 1)
        label_part = f"{label_raw.strip()}: "
        value_part = value_raw.strip()

        canvas.setFillColorRGB(*base_rgb)
        canvas.setFont(label_font_name, label_font_size)
        canvas.drawString(x, y, label_part)
        cursor = x + canvas.stringWidth(label_part, label_font_name, label_font_size)

        if not value_part:
            return

        if colorize_axis_letters:
            self._draw_text_with_axis_colors(
                canvas,
                cursor,
                y,
                value_part,
                font_name=value_font_name,
                font_size=value_font_size,
            )
            return

        canvas.setFillColorRGB(*base_rgb)
        canvas.setFont(value_font_name, value_font_size)
        canvas.drawString(cursor, y, value_part)

    def _draw_box(
        self,
        canvas,
        x,
        top_y,
        width,
        title,
        lines,
        *,
        body_font=12.0,
        body_font_name="Helvetica",
        colorize_axis_letters=False,
        bold_value_after_colon=False,
    ):
        title_h = 22
        pad_x = 12
        pad_y = 10
        line_h = body_font + 5.0
        wrapped = []
        wrap_chars = max(18, int((width - (pad_x * 2)) / 5.0))
        for line in lines or ["-"]:
            wrapped.extend(self._wrap_lines(line, wrap_chars))
        body_h = (len(wrapped) * line_h) + (pad_y * 2)
        total_h = title_h + body_h
        bottom_y = top_y - total_h

        canvas.setStrokeColorRGB(0.78, 0.83, 0.89)
        # Keep the blue frame/header language, but make the inner content surface white.
        canvas.setFillColorRGB(1.0, 1.0, 1.0)
        canvas.roundRect(x, bottom_y, width, total_h, 4, stroke=1, fill=1)

        canvas.setFillColorRGB(0.90, 0.94, 0.98)
        canvas.roundRect(x, top_y - title_h, width, title_h, 4, stroke=0, fill=1)
        canvas.setFillColorRGB(0.10, 0.20, 0.30)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(x + 8, top_y - 14, title)

        canvas.setFillColorRGB(0.14, 0.18, 0.22)
        canvas.setFont(body_font_name, body_font)
        text_y = top_y - title_h - pad_y - body_font
        for index, line in enumerate(wrapped):
            is_zero_row = " zero:" in line.lower()
            if bold_value_after_colon and ":" in line:
                self._draw_label_value_line(
                    canvas,
                    x + pad_x,
                    text_y,
                    line,
                    label_font_name=body_font_name,
                    label_font_size=body_font,
                    value_font_name="Helvetica-Bold",
                    value_font_size=body_font,
                    colorize_axis_letters=colorize_axis_letters and is_zero_row,
                )
            elif colorize_axis_letters and is_zero_row:
                self._draw_text_with_axis_colors(
                    canvas,
                    x + pad_x,
                    text_y,
                    line,
                    font_name=body_font_name,
                    font_size=body_font,
                )
            else:
                canvas.drawString(x + pad_x, text_y, line)
            if index < len(wrapped) - 1:
                separator_y = text_y - 5.0
                line_inset = 8
                canvas.setStrokeColorRGB(0.78, 0.82, 0.87)
                canvas.setLineWidth(0.6)
                canvas.line(x + pad_x + line_inset, separator_y, x + width - pad_x - line_inset, separator_y)
                canvas.setFillColorRGB(0.14, 0.18, 0.22)
                canvas.setFont(body_font_name, body_font)
            text_y -= line_h

        canvas.setStrokeColorRGB(0.85, 0.88, 0.92)
        canvas.setLineWidth(0.5)
        canvas.line(x, bottom_y - 4, x + width, bottom_y - 4)

        return bottom_y - 8

    @staticmethod
    def _tool_icon_path(tool_type) -> Path | None:
        icon_name = TOOL_TYPE_TO_ICON.get(PrintService._to_text(tool_type), DEFAULT_TOOL_ICON)
        for base_dir in (TOOL_LIBRARY_TOOL_ICONS_DIR, TOOL_ICONS_DIR):
            candidate = base_dir / icon_name
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _is_turning_tool_type(tool_type) -> bool:
        tool = PrintService._to_text(tool_type)
        return tool in {
            "O.D Turning",
            "I.D Turning",
            "O.D Groove",
            "I.D Groove",
            "Face Groove",
            "O.D Thread",
            "I.D Thread",
            "Turn Thread",
            "Turn Drill",
            "Turn Spot Drill",
        }

    def _tool_comment_lines(self, tool, width):
        comment = self._to_text(tool.get("comment"))
        if not comment:
            return []
        wrap_chars = max(20, int((width - 40) / 4.8))
        return self._wrap_lines(comment, wrap_chars)

    def _tool_card_height(self, tool, width):
        comment_lines = self._tool_comment_lines(tool, width)
        if not comment_lines:
            return self._TOOL_CARD_HEIGHT
        # Keep cards compact and only expand for visible comment lines.
        return self._TOOL_CARD_HEIGHT + (len(comment_lines) * 4)

    def _draw_tool_card(self, canvas, x, top_y, width, tool, show_pot=False):
        card_h = self._tool_card_height(tool, width)
        bottom_y = top_y - card_h

        canvas.setStrokeColorRGB(0.55, 0.66, 0.77)
        canvas.setFillColorRGB(1.0, 1.0, 1.0)
        canvas.roundRect(x, bottom_y, width, card_h, 5, stroke=1, fill=1)

        icon_path = self._tool_icon_path(tool.get("tool_type", ""))
        icon_x = x + 8
        icon_size = 14
        icon_y = top_y - ((card_h + icon_size) / 2)
        is_sub_turning = (
            self._to_text(tool.get("spindle")).lower() == "sub"
            and self._is_turning_tool_type(tool.get("tool_type", ""))
        )
        if icon_path is not None:
            try:
                if is_sub_turning:
                    canvas.saveState()
                    canvas.scale(-1, 1)
                    canvas.drawImage(
                        str(icon_path),
                        -icon_x - icon_size,
                        icon_y,
                        width=icon_size,
                        height=icon_size,
                        preserveAspectRatio=True,
                        mask='auto',
                    )
                    canvas.restoreState()
                else:
                    canvas.drawImage(str(icon_path), icon_x, icon_y, width=icon_size, height=icon_size, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        pot = self._to_text(tool.get("pot")) if show_pot else ""
        pot_width = 0
        if pot:
            canvas.setFont("Helvetica-Bold", 9)
            pot_width = canvas.stringWidth(pot, "Helvetica-Bold", 9) + 20

        tool_id = self._to_text(tool.get("id"))
        desc = self._to_text(tool.get("description")) or self._t("tool_library.common.no_description", "No description")
        title = f"{tool_id} - {desc}" if tool_id else desc
        max_title_w = max(26, int((width - 36 - pot_width) / 4.9))
        title = textwrap.shorten(title, width=max_title_w, placeholder="...")

        comment_lines = self._tool_comment_lines(tool, width)

        tx = x + 26
        card_mid = top_y - (card_h / 2)
        canvas.setFillColorRGB(0.11, 0.15, 0.20)
        canvas.setFont("Helvetica-Bold", 9.9)
        canvas.setFillColorRGB(0.11, 0.15, 0.20)
        title_y = (card_mid - 1.0) if comment_lines else (card_mid - 4.4)
        canvas.drawString(tx, title_y, title)
        if comment_lines:
            comment_y = title_y - 7.2
            canvas.setFont("Helvetica-Oblique", 8.4)
            canvas.setFillColorRGB(0.27, 0.34, 0.42)
            for line in comment_lines:
                canvas.drawString(tx, comment_y, line)
                comment_y -= 4.6

        if pot:
            canvas.setFont("Helvetica-Bold", 9)
            pot_text_w = canvas.stringWidth(pot, "Helvetica-Bold", 9)
            box_pad_x = 5
            box_w = pot_text_w + box_pad_x * 2
            box_h = 14
            box_x = x + width - box_w - 5
            box_y = card_mid - box_h / 2
            canvas.setStrokeColorRGB(0.55, 0.66, 0.77)
            canvas.roundRect(box_x, box_y, box_w, box_h, 4, stroke=1, fill=0)
            canvas.setFillColorRGB(0.17, 0.28, 0.41)
            text_x = box_x + box_w / 2 - pot_text_w / 2
            canvas.drawString(text_x, card_mid - 3.5, pot)

        return bottom_y - self._TOOL_CARD_GAP

    def _draw_tool_column_container(self, canvas, x, top_y, width, bottom_y):
        height = max(0, top_y - bottom_y)
        if height <= 0:
            return
        canvas.setStrokeColorRGB(0.79, 0.86, 0.94)
        canvas.setFillColorRGB(0.92, 0.96, 1.0)
        canvas.roundRect(x, bottom_y, width, height, 7, stroke=1, fill=1)

    def _tool_section_start_y(self, top_y: float) -> float:
        return top_y - 22

    @staticmethod
    def _tools_page_start_y(page_h: float, margin: float) -> float:
        return (page_h - margin) - 18 - 14 - 20

    def _plan_tool_section(self, tools, start_index, top_y, width, min_bottom):
        cards_top = top_y - 18
        cursor_top = cards_top - 4
        placements = []
        next_index = start_index
        while next_index < len(tools):
            tool = tools[next_index]
            card_h = self._tool_card_height(tool, width - 12)
            card_bottom = cursor_top - card_h
            if card_bottom < min_bottom + 8:
                break
            placements.append((cursor_top, tool))
            cursor_top = card_bottom - self._TOOL_CARD_GAP
            next_index += 1

        if not placements:
            return {
                "placements": [],
                "next_index": start_index,
                "container_top": cards_top,
                "container_bottom": cards_top,
                "consumed_bottom": top_y,
            }

        last_top, last_tool = placements[-1]
        last_bottom = last_top - self._tool_card_height(last_tool, width - 12)
        container_bottom = last_bottom - 6
        return {
            "placements": placements,
            "next_index": next_index,
            "container_top": cards_top,
            "container_bottom": container_bottom,
            "consumed_bottom": container_bottom,
        }

    def _draw_tool_section(self, canvas, x, top_y, width, label, plan, show_pot=False):
        canvas.setFont("Helvetica-Bold", 11.5)
        canvas.setFillColorRGB(0.17, 0.28, 0.41)
        canvas.drawString(x, top_y, label)
        if not plan.get("placements"):
            return
        self._draw_tool_column_container(canvas, x, plan["container_top"], width, plan["container_bottom"])
        for card_top, tool in plan["placements"]:
            self._draw_tool_card(canvas, x + 6, card_top, width - 12, tool, show_pot=show_pot)

    def _layout_head_groups(
        self,
        canvas,
        left_x,
        right_x,
        start_y,
        col_w,
        min_bottom,
        head_groups,
        resume_state=(0, 0, 0),
        *,
        render=False,
        show_tools_heading=False,
        show_pot=False,
    ):
        """Layout tools grouped by head: main spindle on left, sub spindle on right.
        HEAD1 is rendered first, then HEAD2 below.

        head_groups: list of {"label": str, "main": [tool, ...], "sub": [tool, ...]}
        resume_state: (head_idx, main_idx, sub_idx) — resume point for pagination
        Returns new resume_state after filling the available area.
        """
        current_y = start_y
        head_idx, main_idx, sub_idx = resume_state

        if render:
            divider_x = left_x + col_w + ((right_x - (left_x + col_w)) / 2)
            canvas.setStrokeColorRGB(0.80, 0.85, 0.91)
            canvas.setLineWidth(0.9)
            canvas.line(divider_x, current_y + 4, divider_x, min_bottom)

        while head_idx < len(head_groups):
            group = head_groups[head_idx]
            main_tools = group.get("main") or []
            sub_tools = group.get("sub") or []
            group_label = group.get("label", f"HEAD{head_idx + 1}")

            is_group_start = (main_idx == 0 and sub_idx == 0)

            main_has_remaining = main_idx < len(main_tools)
            sub_has_remaining = sub_idx < len(sub_tools)

            if not main_has_remaining and not sub_has_remaining:
                head_idx += 1
                main_idx = 0
                sub_idx = 0
                continue

            if is_group_start:
                if current_y - 18 < min_bottom + self._TOOL_CARD_HEIGHT:
                    break
                if render:
                    tools_heading = self._t("print.setup_card.tools_heading", "Tools")
                    canvas.setFont("Helvetica-Bold", 12)
                    canvas.setFillColorRGB(0.12, 0.23, 0.35)
                    canvas.drawString(left_x, current_y, f"{tools_heading} - {group_label}")
                current_y -= 18

            left_plan = self._plan_tool_section(main_tools, main_idx, current_y, col_w, min_bottom)
            right_plan = self._plan_tool_section(sub_tools, sub_idx, current_y, col_w, min_bottom)

            main_spindle = self._t("print.setup_card.spindle.main", "Main")
            sub_spindle = self._t("print.setup_card.spindle.sub", "Sub")
            main_label = main_spindle
            sub_label = sub_spindle

            if (main_has_remaining and not left_plan["placements"]) or \
               (sub_has_remaining and not right_plan["placements"]):
                break

            if render:
                if main_has_remaining:
                    self._draw_tool_section(canvas, left_x, current_y, col_w, main_label, left_plan, show_pot=show_pot)
                if sub_has_remaining:
                    self._draw_tool_section(canvas, right_x, current_y, col_w, sub_label, right_plan, show_pot=show_pot)

            consumed = [current_y]
            if main_has_remaining:
                consumed.append(left_plan["consumed_bottom"])
            if sub_has_remaining:
                consumed.append(right_plan["consumed_bottom"])
            row_bottom = min(consumed)

            main_done = not main_has_remaining or left_plan["next_index"] >= len(main_tools)
            sub_done = not sub_has_remaining or right_plan["next_index"] >= len(sub_tools)

            if main_has_remaining:
                main_idx = left_plan["next_index"]
            if sub_has_remaining:
                sub_idx = right_plan["next_index"]

            if main_done and sub_done:
                head_idx += 1
                main_idx = 0
                sub_idx = 0
                current_y = row_bottom - 24
                if render and head_idx < len(head_groups):
                    separator_y = row_bottom - 10
                    canvas.setStrokeColorRGB(0.80, 0.85, 0.91)
                    canvas.setLineWidth(0.8)
                    canvas.line(left_x, separator_y, left_x + col_w, separator_y)
                    canvas.line(right_x, separator_y, right_x + col_w, separator_y)
            else:
                break

        return (head_idx, main_idx, sub_idx)

    def _draw_tools_page_header(self, canvas, page_w, margin, top_y, work_id, drawing_id, description):
        canvas.setFont("Helvetica-Bold", 20)
        canvas.setFillColorRGB(0.10, 0.19, 0.29)
        canvas.drawString(margin, top_y, work_id)
        top_y -= 18

        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColorRGB(0.18, 0.26, 0.35)
        canvas.drawString(margin, top_y, self._t("print.setup_card.label.drawing_id", "Drawing ID: {drawing_id}", drawing_id=drawing_id))
        top_y -= 14

        canvas.setFont("Helvetica", 12)
        canvas.setFillColorRGB(0.22, 0.28, 0.34)
        canvas.drawString(margin, top_y, description)
        canvas.setFont("Helvetica", 10.5)
        canvas.setFillColorRGB(0.28, 0.34, 0.40)
        canvas.drawRightString(page_w - margin, top_y + 14, self._t("print.setup_card.tools_heading", "Tools"))
        return top_y - 20

    def _spindle_zero_text(self, coord, axis_values):
        coord_text = self._to_text(coord)
        parts = []
        for axis in ("z", "x", "y", "c"):
            value = self._to_text(axis_values.get(axis))
            if value:
                parts.append(f"{axis.upper()}{value}")
        if not parts:
            return ""
        axis_text = " | ".join(parts)
        if coord_text:
            return f"{coord_text} - {axis_text}"
        return axis_text

    def _zero_lines_for_head(self, work, prefix):
        lines = []
        for spindle_key, spindle_title in (("main", "SP1"), ("sub", "SP2")):
            coord = work.get(f"{prefix}_{spindle_key}_coord") or work.get(f"{prefix}_zero")
            values = {
                axis: work.get(f"{prefix}_{spindle_key}_{axis}")
                for axis in ("z", "x", "y", "c")
            }
            text = self._spindle_zero_text(coord, values)
            if text:
                lines.append(self._t("print.setup_card.label.zero", "{spindle} zero: {text}", spindle=spindle_title, text=text))
        return lines

    def generate_setup_card(self, work, entry, output_path):
        try:
            from reportlab.lib.pagesizes import A4  # type: ignore[import-not-found]
            from reportlab.pdfgen import canvas  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError(
                "reportlab is required for PDF generation. "
                "Install reportlab in the runtime environment or rebuild the executable "
                "with reportlab included in PyInstaller hiddenimports/datas."
            ) from exc

        pdf = canvas.Canvas(str(output_path), pagesize=A4)
        page_w, page_h = A4
        margin = 26
        content_w = page_w - (margin * 2)
        col_gap = 12
        col_w = (content_w - col_gap) / 2

        # ------------------------------------------------------------------
        # PAGE 1: Programs + zero points + jaws + notes
        # ------------------------------------------------------------------
        top_y = page_h - margin
        work_id = self._safe(work.get('work_id'))
        drawing_id = self._safe(work.get('drawing_id'))
        description = self._safe(work.get('description'))

        pdf.setFont("Helvetica-Bold", 20)
        pdf.setFillColorRGB(0.10, 0.19, 0.29)
        pdf.drawString(margin, top_y, work_id)
        top_y -= 18

        pdf.setFont("Helvetica-Bold", 12)
        pdf.setFillColorRGB(0.18, 0.26, 0.35)
        pdf.drawString(margin, top_y, self._t("print.setup_card.label.drawing_id", "Drawing ID: {drawing_id}", drawing_id=drawing_id))
        top_y -= 14

        pdf.setFont("Helvetica", 12)
        pdf.setFillColorRGB(0.22, 0.28, 0.34)
        pdf.drawString(margin, top_y, description)
        pdf.setFont("Helvetica", 10.5)
        pdf.setFillColorRGB(0.28, 0.34, 0.40)
        generated_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        pdf.drawRightString(page_w - margin, top_y + 14, self._t("print.generated_at", "Generated {ts}", ts=generated_ts))
        top_y -= 18

        left_x = margin
        right_x = margin + col_w + col_gap
        left_y = top_y
        right_y = top_y
        head1_lines = [
            self._t("print.setup_card.label.program", "Program: {value}", value=self._safe(work.get('main_program'))),
            self._t("print.setup_card.label.sub_program", "Sub program: {value}", value=self._safe(work.get('head1_sub_program'))),
        ]
        head1_lines.extend(self._zero_lines_for_head(work, "head1"))

        head2_lines = [
            self._t("print.setup_card.label.program", "Program: {value}", value=self._safe(work.get('main_program'))),
            self._t("print.setup_card.label.sub_program", "Sub program: {value}", value=self._safe(work.get('head2_sub_program'))),
        ]
        head2_lines.extend(self._zero_lines_for_head(work, "head2"))

        left_y = self._draw_box(
            pdf,
            left_x,
            left_y,
            col_w,
            self._t("print.setup_card.section.head1", "HEAD1"),
            head1_lines,
            body_font=12.0,
            body_font_name="Helvetica",
            colorize_axis_letters=True,
            bold_value_after_colon=True,
        )
        right_y = self._draw_box(
            pdf,
            right_x,
            right_y,
            col_w,
            self._t("print.setup_card.section.head2", "HEAD2"),
            head2_lines,
            body_font=12.0,
            body_font_name="Helvetica",
            colorize_axis_letters=True,
            bold_value_after_colon=True,
        )

        top_y = min(left_y, right_y)

        sp1_details = self._jaw_details(work.get("main_jaw_id"))
        sp2_details = self._jaw_details(work.get("sub_jaw_id"))
        raw_part_od = self._to_text(work.get("raw_part_od"))
        raw_part_id = self._to_text(work.get("raw_part_id"))
        raw_part_length = self._to_text(work.get("raw_part_length"))
        raw_part_line = ""
        if raw_part_od or raw_part_id or raw_part_length:
            if raw_part_od and raw_part_id and raw_part_length:
                raw_part_value = f"{raw_part_od}/{raw_part_id}*{raw_part_length}"
            elif raw_part_od and raw_part_length:
                raw_part_value = f"{raw_part_od}*{raw_part_length}"
            elif raw_part_od and raw_part_id:
                raw_part_value = f"{raw_part_od}/{raw_part_id}"
            elif raw_part_od:
                raw_part_value = raw_part_od
            elif raw_part_id and raw_part_length:
                raw_part_value = f"{raw_part_id}*{raw_part_length}"
            elif raw_part_id:
                raw_part_value = raw_part_id
            else:
                raw_part_value = raw_part_length
            raw_part_line = self._t(
                "print.setup_card.label.sp1_raw_part",
                "Aihio: {value}",
                value=raw_part_value,
            )

        sp1_is_spiked = self._to_text(sp1_details.get('jaw_type')).lower() == 'spiked jaws'
        sp1_jaw_lines = [
            self._t("print.setup_card.label.sp1_jaw", "SP1 jaw: {value}", value=self._jaw_summary(work.get('main_jaw_id'))),
        ]
        if raw_part_line and not sp1_is_spiked:
            sp1_jaw_lines.append(raw_part_line)
        sp1_turning_washer = self._to_text(sp1_details.get('turning_washer'))
        if sp1_turning_washer:
            sp1_jaw_lines.append(self._t("print.setup_card.label.sp1_turning_ring", "SP1 turning ring: {value}", value=sp1_turning_washer))
        sp1_last_modified = self._to_text(sp1_details.get('last_modified'))
        if sp1_last_modified:
            sp1_jaw_lines.append(self._t("print.setup_card.label.sp1_last_modified", "SP1 last modified: {value}", value=sp1_last_modified))
        if sp1_is_spiked:
            sp1_jaw_lines.append(self._t("print.setup_card.label.sp1_stop_screws", "SP1 stop screws: {value}", value=self._safe(work.get('main_stop_screws'))))
            if raw_part_line:
                sp1_jaw_lines.append(raw_part_line)

        sp2_jaw_lines = [
            self._t("print.setup_card.label.sp2_jaw", "SP2 jaw: {value}", value=self._jaw_summary(work.get('sub_jaw_id'))),
        ]
        if self._to_text(sp2_details.get('jaw_type')).lower() == 'spiked jaws':
            sp2_jaw_lines.append(self._t("print.setup_card.label.sp2_stop_screws", "SP2 stop screws: {value}", value=self._safe(work.get('sub_stop_screws'))))
        sp2_turning_washer = self._to_text(sp2_details.get('turning_washer'))
        if sp2_turning_washer:
            sp2_jaw_lines.insert(1, self._t("print.setup_card.label.sp2_turning_ring", "SP2 turning ring: {value}", value=sp2_turning_washer))
        sp2_last_modified = self._to_text(sp2_details.get('last_modified'))
        if sp2_last_modified:
            insert_idx = 2 if sp2_turning_washer else 1
            sp2_jaw_lines.insert(insert_idx, self._t("print.setup_card.label.sp2_last_modified", "SP2 last modified: {value}", value=sp2_last_modified))

        left_y = self._draw_box(
            pdf,
            left_x,
            top_y,
            col_w,
            self._t("print.setup_card.section.jaws_sp1", "Jaws SP1"),
            sp1_jaw_lines,
            body_font=12.0,
            bold_value_after_colon=True,
        )
        right_y = self._draw_box(
            pdf,
            right_x,
            top_y,
            col_w,
            self._t("print.setup_card.section.jaws_sp2", "Jaws SP2"),
            sp2_jaw_lines,
            body_font=12.0,
            bold_value_after_colon=True,
        )
        top_y = min(left_y, right_y)

        notes_text = self._to_text(work.get('notes'))
        has_real_notes = bool(notes_text and notes_text not in {"-", "--"})
        if has_real_notes:
            top_y = self._draw_box(pdf, margin, top_y, content_w, self._t("setup_page.section.notes", "Notes"), [notes_text], body_font=12.0)
        robot_info = self._to_text(work.get('robot_info'))
        if robot_info:
            top_y = self._draw_box(pdf, margin, top_y, content_w, self._t("print.setup_card.section.robot_notes", "Robot notes"), [robot_info], body_font=12.0)

        head1_main, head1_sub = self._tool_lists_for_head(work.get("head1_tool_assignments") or [])
        head2_main, head2_sub = self._tool_lists_for_head(work.get("head2_tool_assignments") or [])
        head_groups = []
        if head1_main or head1_sub:
            head_groups.append({
                "label": self._t("print.setup_card.section.head1", "HEAD1"),
                "main": head1_main,
                "sub": head1_sub,
            })
        if head2_main or head2_sub:
            head_groups.append({
                "label": self._t("print.setup_card.section.head2", "HEAD2"),
                "main": head2_main,
                "sub": head2_sub,
            })
        min_bottom = margin + 18
        show_pot = bool(work.get("print_pots"))

        page1_tool_start = self._tool_section_start_y(top_y)
        blank_tool_page_start = self._tools_page_start_y(page_h, margin)

        # Decide whether tools fit on page 1, on a dedicated page 2, or need multi-page spillover.
        sim_state_1 = self._layout_head_groups(
            None, left_x, right_x, page1_tool_start, col_w, min_bottom,
            head_groups, (0, 0, 0), render=False, show_tools_heading=True, show_pot=show_pot,
        )

        if sim_state_1[0] >= len(head_groups):
            self._layout_head_groups(
                pdf, left_x, right_x, page1_tool_start, col_w, min_bottom,
                head_groups, (0, 0, 0), render=True, show_tools_heading=True, show_pot=show_pot,
            )
            pdf.save()
            return output_path

        sim_state_2 = self._layout_head_groups(
            None, left_x, right_x, blank_tool_page_start, col_w, min_bottom,
            head_groups, (0, 0, 0), render=False, show_tools_heading=False, show_pot=show_pot,
        )

        if sim_state_2[0] >= len(head_groups):
            pdf.showPage()
            tool_page_start = self._draw_tools_page_header(pdf, page_w, margin, page_h - margin, work_id, drawing_id, description)
            self._layout_head_groups(
                pdf, left_x, right_x, tool_page_start, col_w, min_bottom,
                head_groups, (0, 0, 0), render=True, show_tools_heading=False, show_pot=show_pot,
            )
            pdf.save()
            return output_path

        state = self._layout_head_groups(
            pdf, left_x, right_x, page1_tool_start, col_w, min_bottom,
            head_groups, (0, 0, 0), render=True, show_tools_heading=True, show_pot=show_pot,
        )

        while state[0] < len(head_groups):
            pdf.showPage()
            tool_page_start = self._draw_tools_page_header(pdf, page_w, margin, page_h - margin, work_id, drawing_id, description)
            state = self._layout_head_groups(
                pdf, left_x, right_x, tool_page_start, col_w, min_bottom,
                head_groups, state, render=True, show_tools_heading=False, show_pot=show_pot,
            )

        pdf.save()
        return output_path

    def generate_dispatch_card(self, work, entry, output_path):
        """Generate a compact dispatch card PDF - one page summary for the shop floor."""
        try:
            from reportlab.lib import colors  # type: ignore[import-not-found]
            from reportlab.lib.pagesizes import A4  # type: ignore[import-not-found]
            from reportlab.lib.styles import getSampleStyleSheet  # type: ignore[import-not-found]
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError("reportlab is required for PDF generation") from exc

        doc = SimpleDocTemplate(
            str(output_path), pagesize=A4,
            leftMargin=28, rightMargin=28, topMargin=30, bottomMargin=30,
        )
        styles = getSampleStyleSheet()
        story = []

        title = f"{self.app_title} - {self._t('print.dispatch_card.title', 'Dispatch Card')}"
        story.append(Paragraph(title, styles["Title"]))
        story.append(
            Paragraph(
                self._t("print.generated_with_colon", "Generated: {ts}", ts=datetime.now().strftime("%Y-%m-%d %H:%M")),
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 10))

        rows = [
            self._row(self._t("setup_page.row.work_id", "Work ID"), work.get("work_id", "")),
            self._row(self._t("setup_page.field.drawing_id", "Drawing ID"), work.get("drawing_id", "")),
            self._row(self._t("setup_page.field.description", "Description"), work.get("description", "")),
            self._row(self._t("print.logbook.batch_serial", "Batch serial"), entry.get("batch_serial", "") if entry else ""),
            self._row(self._t("setup_page.log_entry.order", "Order"), entry.get("order_number", "") if entry else ""),
            self._row(self._t("setup_page.log_entry.quantity", "Quantity"), entry.get("quantity", "") if entry else ""),
            self._row(self._t("print.logbook.date", "Date"), entry.get("date", "") if entry else ""),
            self._row(self._t("print.dispatch.main_jaw", "Main jaw"), work.get("main_jaw_id", "")),
            self._row(self._t("print.dispatch.sub_jaw", "Sub jaw"), work.get("sub_jaw_id", "")),
            self._row(self._t("setup_page.field.main_program", "Main program"), work.get("main_program", "")),
            self._row(self._t("setup_page.field.sub_programs_head1", "Sub program Head 1"), work.get("head1_sub_program", "")),
        ]
        main_jaw_details = self._jaw_details(work.get("main_jaw_id"))
        sub_jaw_details = self._jaw_details(work.get("sub_jaw_id"))
        if self._to_text(main_jaw_details.get("jaw_type")).lower() == "spiked jaws" and work.get("main_stop_screws"):
            rows.append(self._row(self._t("print.dispatch.main_stop_screws", "Main stop screws"), work.get("main_stop_screws", "")))
        if self._to_text(sub_jaw_details.get("jaw_type")).lower() == "spiked jaws" and work.get("sub_stop_screws"):
            rows.append(self._row(self._t("print.dispatch.sub_stop_screws", "Sub stop screws"), work.get("sub_stop_screws", "")))
        if work.get("head2_sub_program"):
            rows.append(self._row(self._t("setup_page.field.sub_programs_head2", "Sub program Head 2"), work.get("head2_sub_program", "")))

        table = Table(rows, colWidths=[160, 350])
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CFD8DC")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F8FD")),
                ]
            )
        )
        story.append(table)

        doc.build(story)
        return output_path

    def generate_logbook_entry_card(self, work, entry, output_path):
        """Generate a vertical A4 card mirroring the Logbook Entry Details view."""
        try:
            from reportlab.lib.pagesizes import A4  # type: ignore[import-not-found]
            from reportlab.pdfgen import canvas  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError("reportlab is required for PDF generation") from exc

        pdf = canvas.Canvas(str(output_path), pagesize=A4)
        page_w, page_h = A4
        margin = 10
        content_w = page_w - (margin * 2)

        work_id = self._safe((work or {}).get("work_id"))

        generated_ts = datetime.now().strftime("%Y-%m-%d %H:%M")

        date_raw = self._to_text((entry or {}).get("date"))
        date_display = date_raw
        if date_raw:
            try:
                date_display = datetime.strptime(date_raw, "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                date_display = date_raw


        # Draw header frame only (transparent fill) using the same border tone/radius
        # as other card sections.
        pdf.setStrokeColorRGB(0.84, 0.86, 0.89)
        pdf.setLineWidth(0.9)
        pdf.roundRect(margin, page_h - 65, content_w, 55, 5, stroke=1, fill=0)

        # Card header uses fixed colors (no monthly logbook palette dependency).
        pdf.setFont("Helvetica-Bold", 37)
        pdf.setFillColorRGB(0.10, 0.19, 0.29)
        pdf.drawString(margin + 8, page_h - 48, work_id)

        # Draw timestamp with original color
        pdf.setFont("Helvetica", 13)
        pdf.setFillColorRGB(0.28, 0.34, 0.40)
        pdf.drawRightString(page_w - margin - 8, page_h - 42, self._t("print.generated_at", "Generated {ts}", ts=generated_ts))

        details_lines = [
            self._t("print.logbook.line.work_id", "Work ID: {value}", value=self._safe((entry or {}).get('work_id'))),
            self._t("print.logbook.line.order", "Order: {value}", value=self._safe((entry or {}).get('order_number'))),
            self._t("print.logbook.line.date", "Date: {value}", value=self._safe(date_display)),
            self._t("print.logbook.line.serial", "Serial: {value}", value=self._safe((entry or {}).get('batch_serial'))),
            self._t("print.logbook.line.quantity", "Quantity: {value}", value=self._safe((entry or {}).get('quantity'))),
        ]

        notes_text = self._to_text((entry or {}).get("notes")) or "-"
        note_wrap_chars = max(28, int((content_w - 28) / 9.2))
        note_lines = self._wrap_lines(notes_text, note_wrap_chars)

        box_top = page_h - 96
        box_bottom = margin
        box_h = box_top - box_bottom
        pad_x = 10

        pdf.setStrokeColorRGB(0.84, 0.86, 0.89)
        pdf.setLineWidth(0.9)
        pdf.setFillColorRGB(1.0, 1.0, 1.0)
        pdf.roundRect(margin, box_bottom, content_w, box_h, 5, stroke=1, fill=1)

        rows_top = box_top - 34
        fixed_row_gap = 58

        for index, line in enumerate(details_lines):
            y = rows_top - (index * fixed_row_gap)
            self._draw_label_value_line(
                pdf,
                margin + pad_x,
                y,
                line,
                label_font_name="Helvetica",
                label_font_size=28,
                value_font_name="Helvetica-Bold",
                value_font_size=28,
                colorize_axis_letters=False,
            )

            sep_y = y - 20
            pdf.setStrokeColorRGB(0.78, 0.82, 0.87)
            pdf.setLineWidth(0.7)
            pdf.line(margin + pad_x, sep_y, margin + content_w - pad_x, sep_y)

        notes_label_y = rows_top - (len(details_lines) * fixed_row_gap) - 8
        pdf.setFillColorRGB(0.14, 0.18, 0.22)
        pdf.setFont("Helvetica", 28)
        pdf.drawString(margin + pad_x, notes_label_y, self._t("print.logbook.notes_label", "Notes:"))

        notes_y = notes_label_y - 32
        pdf.setFont("Helvetica-Bold", 26)
        for note_line in note_lines:
            if notes_y < box_bottom + 14:
                break
            pdf.drawString(margin + pad_x, notes_y, note_line)
            notes_y -= 24

        pdf.save()
        return output_path

