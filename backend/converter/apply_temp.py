import re
import os

pdf_edit_path = r"c:\Users\Paradox-Labs\Documents\Projects\Writing_Tools\backend\converter\pdf_edit.py"

with open(pdf_edit_path, "r", encoding="utf-8") as f:
    content = f.read()

# We want to replace everything from `    for edit in edits_list:` 
# down to `    # ── Subset embedded fonts to keep file size reasonable ──`
# Which is approximately line 240 to 577.

new_logic = """    from collections import defaultdict
    edits_by_page = defaultdict(list)
    for edit in edits_list:
        edits_by_page[edit["pageNum"]].append(edit)

    for page_num, page_edits in edits_by_page.items():
        page = doc[page_num - 1]
        
        # Ensure page content stream is balanced before drawing
        if not page.is_wrapped:
            page.wrap_contents()

        edit_plans = []

        # ── Phase 1: Measure everything BEFORE any mutations ──
        for edit in page_edits:
            orig_text = edit.get("origStr", "")
            new_text = edit.get("newStr", "")
            # Enforce sanitization of HTML non-breaking spaces injected by contenteditable
            new_text = new_text.replace("\\u00A0", " ").replace("&nbsp;", " ")
            new_text = _expand_ligatures(new_text)

            # ── Coordinates (all in MuPDF space via Util.transform at scale=1) ──
            x0       = edit["rect"]["x"]
            y0       = edit["rect"]["y"]
            x1_frontend = x0 + edit["rect"]["w"]  # frontend-derived (fallback)
            y1       = y0 + edit["rect"]["h"]
            origin_y = edit.get("origin_y", y1 - 2)
            fontsize = edit.get("origFontSize", 11) + edit.get("fontSizeAdj", 0)
            fontsize = max(4.0, fontsize)  # MuPDF minimum

            # ── Backend-authoritative width measurement from rawdict ──────────
            measured_w, matched_span = _measure_span_width(page, x0, origin_y)
            if measured_w and measured_w > 0:
                x1 = x0 + measured_w
                logger.info(f"Using backend-measured width: {measured_w:.2f} (frontend was {edit['rect']['w']:.2f})")
            else:
                x1 = x1_frontend
                logger.info(f"Backend width measurement failed, using frontend width: {edit['rect']['w']:.2f}")

            # ── Font resolution ──────────────────────────────────────────────────
            edit["fontName"] = _resolve_font_name(page, edit, x0, y0, x1_frontend, y1)
            font_result = get_font_for_edit(doc, page, edit)

            if font_result.fallback_used:
                warning_entry = {
                    "pageNum":  edit["pageNum"],
                    "origStr":  orig_text,
                    "reason":   font_result.fallback_reason,
                }
                if font_result.missing_glyphs:
                    warning_entry["missingGlyphs"] = font_result.missing_glyphs
                warnings.append(warning_entry)
                logger.warning(
                    f"Page {edit['pageNum']}: font fallback used. "
                    f"Reason: {font_result.fallback_reason}"
                )

            # Register the font with this page so insert_text can find it
            if font_result.font_buffer:
                page.insert_font(
                    fontname=font_result.fontname,
                    fontbuffer=font_result.font_buffer,
                )

            # ── Determine insert color ───────────────────────────────────────────
            insert_color = _resolve_color(page, edit, x0, y0, x1_frontend, y1)

            # ── Prepare font measurement ─────────────────────────────────────────
            try:
                if font_result.font_buffer:
                    measure_font = fitz.Font(fontbuffer=font_result.font_buffer)
                    has_space = measure_font.has_glyph(32)
                else:
                    measure_font = fitz.Font(fontname=font_result.fontname)
                    has_space = measure_font.has_glyph(32)
                space_width = measure_font.text_length(" ", fontsize=fontsize)
            except Exception:
                space_width = 0.0
                has_space = False
                measure_font = None

            # ── Erase metrics ────────────────────────────────────────────────────
            ascender_h  = edit.get("ascender_h",  fontsize * 0.8)
            descender_h = edit.get("descender_h", fontsize * 0.2)
            erase_y0 = origin_y - ascender_h
            erase_y1 = origin_y + descender_h

            plan = {
                "erase_rects": [],
                "insert_chars": []
            }

            # ── MINIMAL-DIFF EDITING ─────────────────────────────────────────────
            rawdict_chars = matched_span.get("chars", []) if matched_span else []
            raw_text = "".join(ch.get("c", "") for ch in rawdict_chars)
            used_minimal_diff = False

            if raw_text and rawdict_chars:
                prefix_len, raw_end, new_end = _find_change_range(raw_text, new_text)
                changed_orig = raw_text[prefix_len:raw_end]
                changed_new = new_text[prefix_len:new_end]

                if prefix_len < raw_end or prefix_len < new_end:
                    if prefix_len < len(rawdict_chars) and raw_end <= len(rawdict_chars):
                        erase_x0 = rawdict_chars[prefix_len]["bbox"][0]
                        erase_x1 = rawdict_chars[raw_end - 1]["bbox"][2]
                        change_origin_y = rawdict_chars[prefix_len]["origin"][1]
                        erase_w = erase_x1 - erase_x0

                        logger.info(
                            f"MINIMAL DIFF: '{changed_orig}' → '{changed_new}' "
                            f"at chars[{prefix_len}:{raw_end}], "
                            f"erase_x=[{erase_x0:.1f}, {erase_x1:.1f}] (width={erase_w:.1f})"
                        )

                        if not changed_new and changed_orig.strip() == "":
                            logger.info("MINIMAL DIFF: whitespace-only removal — skipping erase")
                            used_minimal_diff = True
                        else:
                            left_margin = fontsize * 0.15 if not changed_new else 0
                            erase_rect = fitz.Rect(
                                erase_x0 + left_margin, erase_y0 - 1,
                                erase_x1 + 1, erase_y1 + 1
                            )
                            plan["erase_rects"].append(erase_rect)

                        if changed_new:
                            advance_table = _build_advance_table(rawdict_chars, fontsize)
                            letter_advs = [v for k, v in advance_table.items() if k != " "]
                            avg_letter_adv = sum(letter_advs) / len(letter_advs) if letter_advs else fontsize * 0.5
                            space_adv = advance_table.get(" ", None)
                            if space_adv is None or space_adv < fontsize * 0.05:
                                space_adv = _get_space_width(
                                    page, erase_x0, change_origin_y, fontsize
                                )

                            change_at_end = (raw_end >= len(rawdict_chars) - 1)

                            if change_at_end:
                                est_new_w = 0
                                for ch in changed_new:
                                    if ch == " ":
                                        est_new_w += space_adv
                                    else:
                                        est_new_w += advance_table.get(ch, avg_letter_adv)
                                if est_new_w > erase_w:
                                    extra_rect = fitz.Rect(
                                        erase_x1, erase_y0 - 1,
                                        erase_x0 + est_new_w + 2, erase_y1 + 1
                                    )
                                    plan["erase_rects"].append(extra_rect)
                                    logger.info(
                                        f"End-of-span: extended erase by "
                                        f"{est_new_w - erase_w:.1f}pt"
                                    )

                            cursor_x = erase_x0

                            for ch in changed_new:
                                if ch == " ":
                                    cursor_x += space_adv
                                else:
                                    plan["insert_chars"].append({
                                        "pos": fitz.Point(cursor_x, change_origin_y),
                                        "text": ch,
                                        "fontname": font_result.fontname,
                                        "fontsize": fontsize,
                                        "color": insert_color,
                                        "morph": None
                                    })
                                    if ch in advance_table:
                                        cursor_x += advance_table[ch]
                                    elif measure_font:
                                        try:
                                            cursor_x += measure_font.text_length(
                                                ch, fontsize=fontsize
                                            )
                                        except Exception:
                                            cursor_x += avg_letter_adv
                                    else:
                                        cursor_x += avg_letter_adv

                        used_minimal_diff = True
                else:
                    logger.info("MINIMAL DIFF: no change between rawdict text and newStr — skipping")
                    used_minimal_diff = True

            # ── FALLBACK: Per-character reconstruction ───────────────────────────
            if not used_minimal_diff:
                logger.info(
                    f"PER-CHAR RECONSTRUCTION: rawdict_chars={len(rawdict_chars)}, "
                    f"origStr_len={len(orig_text)}"
                )

                erase_rect = fitz.Rect(x0 - 1, erase_y0 - 1, x1 + 1, erase_y1 + 1)
                plan["erase_rects"].append(erase_rect)

                if rawdict_chars:
                    raw_text_fb = "".join(ch.get("c", "") for ch in rawdict_chars)
                    prefix_len, raw_end, new_end = _find_change_range(raw_text_fb, new_text)
                    changed_new = new_text[prefix_len:new_end]

                    for i in range(prefix_len):
                        ch = rawdict_chars[i]
                        plan["insert_chars"].append({
                            "pos": fitz.Point(ch["origin"][0], ch["origin"][1]),
                            "text": ch["c"],
                            "fontname": font_result.fontname,
                            "fontsize": fontsize,
                            "color": insert_color,
                            "morph": None
                        })

                    if changed_new:
                        if raw_end > prefix_len and raw_end <= len(rawdict_chars):
                            ins_x = rawdict_chars[prefix_len]["bbox"][0]
                            ins_y = rawdict_chars[prefix_len]["origin"][1]
                            erase_w = rawdict_chars[raw_end - 1]["bbox"][2] - ins_x
                        else:
                            ins_x = rawdict_chars[-1]["bbox"][2] if rawdict_chars else x0
                            ins_y = origin_y
                            erase_w = 0

                        insert_pt = fitz.Point(ins_x, ins_y)
                        morph = None
                        if measure_font and erase_w > 0:
                            try:
                                new_w = measure_font.text_length(changed_new, fontsize=fontsize)
                                if new_w > 0:
                                    scale_x = erase_w / new_w
                                    if 0.5 <= scale_x <= 2.0:
                                        morph = (insert_pt, fitz.Matrix(scale_x, 1))
                                        logger.info(f"reconstruction morph scale_x={scale_x:.3f}")
                            except Exception:
                                pass

                        if " " in changed_new and (not has_space or space_width < fontsize * 0.1):
                            space_w = _get_space_width(page, ins_x, ins_y, fontsize)
                            cursor_x = ins_x
                            for word in changed_new.split(" "):
                                if word:
                                    plan["insert_chars"].append({
                                        "pos": fitz.Point(cursor_x, ins_y),
                                        "text": word,
                                        "fontname": font_result.fontname,
                                        "fontsize": fontsize,
                                        "color": insert_color,
                                        "morph": None
                                    })
                                    try:
                                        cursor_x += measure_font.text_length(word, fontsize=fontsize)
                                    except Exception:
                                        cursor_x += len(word) * (fontsize * 0.5)
                                cursor_x += space_w
                        else:
                            plan["insert_chars"].append({
                                "pos": insert_pt,
                                "text": changed_new,
                                "fontname": font_result.fontname,
                                "fontsize": fontsize,
                                "color": insert_color,
                                "morph": morph
                            })

                    for i in range(raw_end, len(rawdict_chars)):
                        ch = rawdict_chars[i]
                        plan["insert_chars"].append({
                            "pos": fitz.Point(ch["origin"][0], ch["origin"][1]),
                            "text": ch["c"],
                            "fontname": font_result.fontname,
                            "fontsize": fontsize,
                            "color": insert_color,
                            "morph": None
                        })

                else:
                    plan["insert_chars"].append({
                        "pos": fitz.Point(x0, origin_y),
                        "text": new_text,
                        "fontname": font_result.fontname,
                        "fontsize": fontsize,
                        "color": insert_color,
                        "morph": None
                    })

            edit_plans.append(plan)

        # ── Phase 2: Redact all erase regions at once ──
        for plan in edit_plans:
            for rect in plan["erase_rects"]:
                page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=0)

        # ── Phase 3: Insert all new text ──
        for plan in edit_plans:
            for char_op in plan["insert_chars"]:
                page.insert_text(
                    char_op["pos"],
                    char_op["text"],
                    fontname=char_op["fontname"],
                    fontsize=char_op["fontsize"],
                    color=char_op["color"],
                    morph=char_op["morph"]
                )
"""

start_marker = "    for edit in edits_list:"
end_marker = "    # ── Subset embedded fonts to keep file size reasonable ──────────────────"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + new_logic + "\\n" + content[end_idx:]
    with open(pdf_edit_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Successfully rewritten pdf_edit.py")
else:
    print("Marks not found!")

