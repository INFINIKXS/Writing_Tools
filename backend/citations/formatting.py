"""
Reference formatting: italic application and multi-style reference string generation.
"""
import re

from utils.text_utils import make_sentence_case, condense_pages, classify_source_type


def apply_italic_formatting(ref_text: str) -> str:
    """
    Apply <i> tags to parts of a reference that should be italicized
    per academic conventions (Harvard, APA). Uses regex pattern matching.
    """
    import html as html_mod
    ref = html_mod.escape(ref_text)
    
    def get_year_dot_pos():
        m = re.search(r'\)\.\s', ref)
        return m.start() + 1 if m else -1
    
    # === 1. JOURNAL / PERIODICAL ===
    vol_issue = re.search(r',\s*\d{1,4}\s*\(\d{1,4}\)', ref)
    page_range = re.search(r',\s*\d+\s*[-\u2013]\s*\d+', ref)
    periodical_marker = vol_issue or page_range
    if periodical_marker:
        before = ref[:periodical_marker.start()]
        last_dot = before.rfind('. ')
        if last_dot >= 0:
            journal_name = before[last_dot + 2:].rstrip(', ')
            year_dot_pos = get_year_dot_pos()
            if last_dot > year_dot_pos and len(journal_name) > 2 and not journal_name.startswith('http'):
                pos = last_dot + 2
                return ref[:pos] + '<i>' + journal_name + '</i>' + ref[pos + len(journal_name):]
        pass
    
    # === 1b. NON-STANDARD JOURNAL FORMAT ===
    in_vol_match = re.search(r'\.\s+In\s+(.+?)\s*\(Vol\.\s*\d+', ref)
    if in_vol_match:
        journal_name = in_vol_match.group(1).rstrip(', ')
        if len(journal_name) > 2:
            start = in_vol_match.start(1)
            end = start + len(in_vol_match.group(1))
            return ref[:start] + '<i>' + journal_name + '</i>' + ref[end:]
    
    # === 1c. CONFERENCE PROCEEDINGS ===
    proc_match = re.search(r'\.\s+In\s+(Proceedings\s+of\s+.+?)(?:\s*\(pp?\.|\.\s*,\s*\d)', ref)
    if proc_match:
        proc_title = proc_match.group(1).rstrip('. ,')
        start = proc_match.start(1)
        end = start + len(proc_match.group(1))
        return ref[:start] + '<i>' + proc_title + '</i>' + ref[end:]
    
    # === 1d. NEWSPAPER/MAGAZINE ===
    section_page = re.search(r',\s*([A-Z]\d{1,3})\s*\.', ref)
    if section_page:
        before = ref[:section_page.start()]
        last_dot = before.rfind('. ')
        if last_dot >= 0:
            source_name = before[last_dot + 2:].rstrip(', ')
            year_dot_pos = get_year_dot_pos()
            if last_dot > year_dot_pos and len(source_name) > 2 and not source_name.startswith('http'):
                pos = last_dot + 2
                return ref[:pos] + '<i>' + source_name + '</i>' + ref[pos + len(source_name):]
    
    # === 2. EDITED CHAPTER ===
    ed_match = re.search(r'\bIn\s+.*?\(Eds?\.\)[,.]?\s*', ref)
    if ed_match:
        title_start = ed_match.end()
        rest = ref[title_start:]
        title_end = re.search(r'(?:\.|\s\(pp?\.|\s\(\d)', rest)
        if title_end:
            title = rest[:title_end.start()]
            if len(title) > 2:
                return ref[:title_start] + '<i>' + title + '</i>' + ref[title_start + len(title):]
        return ref
    
    # === 2b. MEDIA with bracket type ===
    media_bracket = re.search(
        r'\[(Film|Video|Motion picture|TV series|TV series episode|'
        r'Webinar|Audio podcast episode|Podcast episode|Song|Album|'
        r'Radio broadcast|Infographic|PowerPoint slides?|Data set|Map|'
        r'Unpublished manuscript|Software|App)\]',
        ref, re.IGNORECASE
    )
    if media_bracket:
        bracket_pos = media_bracket.start()
        before_bracket = ref[:bracket_pos].rstrip()
        title_start_match = re.search(r'\)\.\s+', before_bracket)
        if title_start_match:
            last_paren_dot = None
            for m in re.finditer(r'\)\.\s+', before_bracket):
                last_paren_dot = m
            if last_paren_dot:
                title = before_bracket[last_paren_dot.end():].strip()
                if len(title) > 2:
                    start = last_paren_dot.end()
                    return ref[:start] + '<i>' + title + '</i>' + ref[start + len(title):]
    
    # === 2c. DISSERTATION / THESIS ===
    diss_match = re.search(
        r'\)\.\s+(.+?)(?:\s*\(Publication No\.|\s*\[(Doctoral|Master|PhD)\s+(dissertation|thesis))',
        ref, re.IGNORECASE
    )
    if diss_match:
        title = diss_match.group(1).rstrip('. ,')
        if len(title) > 2:
            start = diss_match.start(1)
            end = start + len(diss_match.group(1))
            return ref[:start] + '<i>' + title + '</i>' + ref[end:]
    
    # === 1f. ADVANCE ONLINE PUBLICATION ===
    year = re.search(r'\((?:\d{4}[a-z]?(?:,\s+\w+(?:\s+\d{1,2})?(?:[\u2013\-]\d{1,2})?)?|n\.d\.)\)\.?\s*', ref)
    if year:
        after_year = ref[year.end():]
        aop_in_after = re.search(r'^.+?\.\s+(.+?)\.\s+Advance\s+online\s+publication', after_year)
        if aop_in_after:
            journal_name = aop_in_after.group(1).strip()
            if len(journal_name) > 2:
                start = year.end() + aop_in_after.start(1)
                end = start + len(aop_in_after.group(1))
                return ref[:start] + '<i>' + journal_name + '</i>' + ref[end:]
    
    # === 1e. ONLINE PERIODICAL ===
    year = re.search(r'\((?:\d{4}[a-z]?(?:,\s+\w+(?:\s+\d{1,2})?(?:[\u2013\-]\d{1,2})?)?|n\.d\.)\)\.?\s*', ref)
    if year:
        after_year = ref[year.end():]
        online_match = re.search(
            r'^(.+?)\.\s+([A-Z][^.]{2,80}?)\.\s+(https?://|Retrieved\s)',
            after_year
        )
        if online_match:
            source_name = online_match.group(2).strip()
            source_words = source_name.split()
            if 1 <= len(source_words) <= 6:
                start = year.end() + online_match.start(2)
                end = start + len(online_match.group(2))
                return ref[:start] + '<i>' + source_name + '</i>' + ref[end:]
    
    # === 3. BOOK / REPORT / OTHER (default) ===
    if year:
        after_year = ref[year.end():]
        segments = re.split(r'(?<=\.)\s+(?=[A-Z])', after_year, maxsplit=3)
        
        if len(segments) >= 2:
            first = segments[0].rstrip('.')
            if len(first) > 2:
                pos = year.end()
                return ref[:pos] + '<i>' + first + '</i>' + ref[pos + len(first):]
        elif len(segments) == 1:
            title = segments[0].rstrip('.')
            if len(title) > 2:
                pos = year.end()
                return ref[:pos] + '<i>' + title + '</i>' + ref[pos + len(title):]
    
    return ref


def format_reference(metadata: dict, style: str = "harvard") -> dict:
    """
    Format metadata into a reference string in the specified style.
    Returns { "formatted": "plain text", "formatted_html": "with <i> tags", "metadata": {...} }
    """
    authors = metadata.get("authors") or ["Unknown Author"]
    title = metadata.get("title") or "Untitled"
    year = metadata.get("year") or "n.d."
    source = metadata.get("source")
    volume = metadata.get("volume")
    issue = metadata.get("issue")
    pages = metadata.get("pages")
    doi = metadata.get("doi")
    url = metadata.get("url")
    publisher = metadata.get("publisher")
    ref_type = metadata.get("type", "Other")
    
    # Format author string
    if len(authors) == 1:
        author_str = authors[0]
    elif len(authors) == 2:
        if style == "apa":
            author_str = f"{authors[0]} & {authors[1]}"
        else:
            author_str = f"{authors[0]} and {authors[1]}"
    elif len(authors) <= 20:
        if style == "apa":
            author_str = ', '.join(authors[:-1]) + f', & {authors[-1]}'
        else:
            author_str = ', '.join(authors[:-1]) + f' and {authors[-1]}'
    else:
        author_str = ', '.join(authors[:19]) + f', ... {authors[-1]}'

    # ─── Vancouver author formatting ───
    if style == "vancouver":
        van_authors = []
        group_authors = []
        group_keywords = re.compile(
            r'\b(group|consortium|committee|collaboration|network|team|'
            r'investigators|working party|task force)\b',
            re.IGNORECASE
        )
        for a in authors:
            stripped = a.strip()
            if group_keywords.search(stripped) and ',' not in stripped and len(authors) > 1:
                group_authors.append(stripped)
                continue
            parts = stripped.split(',')
            if len(parts) >= 2:
                surname = parts[0].strip()
                initials = parts[1].strip().replace('.', '').replace(' ', '')
                van_authors.append(f"{surname} {initials}")
            else:
                van_authors.append(stripped)
        
        if len(van_authors) > 6:
            author_str = ', '.join(van_authors[:6]) + ', et al.'
        else:
            author_str = ', '.join(van_authors)
            if group_authors:
                author_str += ', ' + ', '.join(group_authors) + '.'
            else:
                author_str += '.'
            
        title = make_sentence_case(metadata.get("title") or "Untitled")
    
    # ─── Harvard author formatting ───
    author_str_html = author_str
    if style == "harvard":
        if len(authors) >= 4:
            author_str = f"{authors[0]} et al."
            author_str_html = f"{authors[0]} <i>et al.</i>"
        if year == "n.d.":
            year = "no date"
    
    # Build location string
    location_parts = []
    if volume and issue:
        location_parts.append(f"{volume}({issue})")
    elif volume:
        location_parts.append(volume)
    if pages:
        if location_parts and style == "harvard":
            location_parts.append(f", pp. {pages}")
        elif location_parts:
            location_parts.append(f", {pages}")
        else:
            location_parts.append(f"pp. {pages}")
    location = ''.join(location_parts)
    
    doi_str = f"https://doi.org/{doi}" if doi else (url or "")
    
    # For APA: prevent double period
    if style != "harvard" and author_str.endswith('.'):
        apa_author_str = author_str
    elif style != "harvard":
        apa_author_str = author_str + '.'
    
    # ─── Harvard Style ───
    if style == "harvard":
        editor = metadata.get("editor")
        edition = metadata.get("edition")
        place = metadata.get("place") or metadata.get("place_of_publication")
        accessed_date = metadata.get("accessed_date") or metadata.get("accessed")
        day_month = metadata.get("day_month")
        report_number = metadata.get("report_number")
        award = metadata.get("award")
        awarding_body = metadata.get("awarding_body")

        pub_str = f"{place}: {publisher}" if place and publisher else (publisher or place or "")

        ending = ""
        if doi:
            ending = f" doi: https://doi.org/{doi}"
        elif url:
            ending = f" Available at: {url}"
            if accessed_date:
                ending += f" (Accessed: {accessed_date})"

        if ref_type == "Journal Article" and source:
            ref_plain = f"{author_str} ({year}) '{title}', {source}"
            ref_html = f"{author_str_html} ({year}) '{title}', <i>{source}</i>"
            if location:
                ref_plain += f", {location}"
                ref_html += f", {location}"
            ref_plain += "."
            ref_html += "."
            if ending:
                ref_plain += ending
                ref_html += ending

        elif ref_type == "Book Chapter":
            ref_plain = f"{author_str} ({year}) '{title}'"
            ref_html = f"{author_str_html} ({year}) '{title}'"
            if editor:
                ref_plain += f", in {editor}"
                ref_html += f", in {editor}"
            if source:
                ref_plain += f" {source}"
                ref_html += f" <i>{source}</i>"
            if edition:
                ref_plain += f". {edition}"
                ref_html += f". {edition}"
            if pub_str:
                ref_plain += f". {pub_str}"
                ref_html += f". {pub_str}"
            if pages:
                ref_plain += f", pp. {pages}"
                ref_html += f", pp. {pages}"
            ref_plain += "."
            ref_html += "."
            if ending:
                ref_plain += ending
                ref_html += ending

        elif ref_type == "Book":
            ref_plain = f"{author_str} ({year}) {title}."
            ref_html = f"{author_str_html} ({year}) <i>{title}</i>."
            if edition:
                ref_plain += f" {edition}."
                ref_html += f" {edition}."
            if pub_str:
                ref_plain += f" {pub_str}."
                ref_html += f" {pub_str}."
            if ending:
                ref_plain += ending
                ref_html += ending

        elif ref_type == "Report":
            ref_plain = f"{author_str} ({year}) {title}."
            ref_html = f"{author_str_html} ({year}) <i>{title}</i>."
            if report_number:
                ref_plain += f" {report_number}."
                ref_html += f" {report_number}."
            if pub_str:
                ref_plain += f" {pub_str}."
                ref_html += f" {pub_str}."
            if ending:
                ref_plain += ending
                ref_html += ending

        elif ref_type == "Conference Paper":
            ref_plain = f"{author_str} ({year}) '{title}'"
            ref_html = f"{author_str_html} ({year}) '{title}'"
            if source:
                ref_plain += f", {source}"
                ref_html += f", <i>{source}</i>"
            ref_plain += "."
            ref_html += "."
            if pub_str:
                ref_plain += f" {pub_str}"
                ref_html += f" {pub_str}"
            if pages:
                ref_plain += f", pp. {pages}"
                ref_html += f", pp. {pages}"
            ref_plain += "."
            ref_html += "."
            if ending:
                ref_plain += ending
                ref_html += ending

        elif ref_type in ("Dissertation", "Thesis"):
            ref_plain = f"{author_str} ({year}) {title}."
            ref_html = f"{author_str_html} ({year}) <i>{title}</i>."
            if award:
                ref_plain += f" {award}."
                ref_html += f" {award}."
            if awarding_body:
                ref_plain += f" {awarding_body}."
                ref_html += f" {awarding_body}."
            elif publisher:
                ref_plain += f" {publisher}."
                ref_html += f" {publisher}."
            if ending:
                ref_plain += ending
                ref_html += ending

        elif ref_type == "Newspaper Article":
            ref_plain = f"{author_str} ({year}) '{title}'"
            ref_html = f"{author_str_html} ({year}) '{title}'"
            if source:
                ref_plain += f", {source}"
                ref_html += f", <i>{source}</i>"
            if day_month:
                ref_plain += f", {day_month}"
                ref_html += f", {day_month}"
            if pages:
                ref_plain += f", p. {pages}"
                ref_html += f", p. {pages}"
            ref_plain += "."
            ref_html += "."
            if ending:
                ref_plain += ending
                ref_html += ending

        elif ref_type == "Blog Post":
            ref_plain = f"{author_str} ({year}) '{title}'"
            ref_html = f"{author_str_html} ({year}) '{title}'"
            if source:
                ref_plain += f", {source}"
                ref_html += f", <i>{source}</i>"
            if day_month:
                ref_plain += f", {day_month}"
                ref_html += f", {day_month}"
            ref_plain += "."
            ref_html += "."
            if ending:
                ref_plain += ending
                ref_html += ending

        elif ref_type == "Podcast":
            ref_plain = f"{author_str} ({year}) {title} [Podcast]."
            ref_html = f"{author_str_html} ({year}) <i>{title}</i> [Podcast]."
            if day_month:
                ref_plain += f" {day_month}."
                ref_html += f" {day_month}."
            if ending:
                ref_plain += ending
                ref_html += ending

        elif ref_type == "Dataset":
            ref_plain = f"{author_str} ({year}) '{title}'."
            ref_html = f"{author_str_html} ({year}) '{title}'."
            if edition:
                ref_plain += f" {edition}."
                ref_html += f" {edition}."
            if ending:
                ref_plain += ending
                ref_html += ending

        elif ref_type == "Web Page":
            ref_plain = f"{author_str} ({year}) {title}."
            ref_html = f"{author_str_html} ({year}) <i>{title}</i>."
            if ending:
                ref_plain += ending
                ref_html += ending

        else:
            ref_plain = f"{author_str} ({year}) {title}."
            ref_html = f"{author_str_html} ({year}) <i>{title}</i>."
            if source:
                ref_plain += f" {source}."
                ref_html += f" <i>{source}</i>."
            if pub_str:
                ref_plain += f" {pub_str}."
                ref_html += f" {pub_str}."
            if ending:
                ref_plain += ending
                ref_html += ending
    
    # ─── APA 7th Style ───
    elif style == "apa":
        if ref_type == "Journal Article" and source:
            ref_plain = f"{apa_author_str} ({year}). {title}. {source}"
            ref_html = f"{apa_author_str} ({year}). {title}. <i>{source}</i>"
            if location:
                if volume:
                    ref_plain += f", {location}"
                    if volume and issue:
                        ref_html += f", <i>{volume}</i>({issue})"
                        if pages:
                            ref_html += f", {pages}"
                    elif volume:
                        ref_html += f", <i>{volume}</i>"
                        if pages:
                            ref_html += f", {pages}"
                    else:
                        ref_html += f", {location}"
                else:
                    ref_plain += f", {location}"
                    ref_html += f", {location}"
            ref_plain += "."
            ref_html += "."
            if doi_str:
                ref_plain += f" {doi_str}"
                ref_html += f" {doi_str}"
        elif ref_type in ("Book", "Book Chapter"):
            ref_plain = f"{apa_author_str} ({year}). {title}."
            ref_html = f"{apa_author_str} ({year}). <i>{title}</i>."
            if publisher:
                ref_plain += f" {publisher}."
                ref_html += f" {publisher}."
            if doi_str:
                ref_plain += f" {doi_str}"
                ref_html += f" {doi_str}"
        elif ref_type == "Web Page":
            ref_plain = f"{apa_author_str} ({year}). {title}."
            ref_html = f"{apa_author_str} ({year}). <i>{title}</i>."
            if source:
                ref_plain += f" {source}."
                ref_html += f" {source}."
            if doi_str:
                ref_plain += f" {doi_str}"
                ref_html += f" {doi_str}"
        else:
            ref_plain = f"{apa_author_str} ({year}). {title}."
            ref_html = f"{apa_author_str} ({year}). <i>{title}</i>."
            if source:
                ref_plain += f" {source}."
                ref_html += f" <i>{source}</i>."
            if doi_str:
                ref_plain += f" {doi_str}"
                ref_html += f" {doi_str}"
    
    # ─── Vancouver (NLM) Style ───
    elif style == "vancouver":
        language = metadata.get("language")
        part_name = metadata.get("part_name")
        part_title = metadata.get("part_title")
        day_month = metadata.get("day_month")
        pmid = metadata.get("pmid")
        epub_date = metadata.get("epub_date")
        
        notes = ""
        if epub_date:
            notes += f" Epub {epub_date}."
        if doi:
            clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").replace("doi:", "").strip()
            notes += f" doi:{clean_doi}."
        elif url:
            notes += f" Available from: {url}"
        if pmid:
            notes += f" Cited in: PubMed; PMID {pmid}."

        if ref_type == "Journal Article" and source:
            date_str = f"{year} {day_month}" if day_month else year
            
            van_loc_parts = []
            if volume and issue:
                van_loc_parts.append(f"{volume}({issue})")
            elif volume:
                van_loc_parts.append(volume)
            elif issue:
                if issue.lower().startswith("suppl"):
                    van_loc_parts.append(issue)
                else:
                    van_loc_parts.append(f"({issue})")
                
            condensed_pages = condense_pages(pages) if pages else ""
            
            chain = f" {date_str}"
            if van_loc_parts:
                chain += f";{''.join(van_loc_parts)}"
                if condensed_pages:
                    chain += f":{condensed_pages}."
                else:
                    chain += "."
            else:
                if condensed_pages:
                    chain += f":{condensed_pages}."
                else:
                    chain += "."
            
            vanc_source = metadata.get("source_abbreviated") or source
            
            title_clean = title.rstrip('.') if title else ""
            title_fmt = f"{title_clean}." if title_clean and not title_clean.endswith('?') else title_clean

            if language and language.lower() != "english":
                ref_plain = f"{author_str} [{title_clean}]. {vanc_source}."
                ref_html = f"{author_str} [{title_clean}]. {vanc_source}."
                ref_plain += chain + f" {language}."
                ref_html += chain + f" {language}."
            
            elif part_name and part_title and pages:
                base_chain = f" {date_str}"
                if van_loc_parts:
                    base_chain += f";{''.join(van_loc_parts)}"
                else:
                    base_chain += ":"
                base_chain += "."
                
                ref_plain = f"{author_str} {title_fmt} {vanc_source}.{base_chain} {part_name}, {part_title}; p. {pages}."
                ref_html = f"{author_str} {title_fmt} {vanc_source}.{base_chain} {part_name}, {part_title}; p. {pages}."
                
            else:
                ref_plain = f"{author_str} {title_fmt} {vanc_source}.{chain}"
                ref_html = f"{author_str} {title_fmt} {vanc_source}.{chain}"

            if notes:
                ref_plain += notes
                ref_html += notes

        elif ref_type == "Book Chapter":
            editor = metadata.get("editor")
            place = metadata.get("place") or metadata.get("place_of_publication")
            
            ref_plain = f"{author_str} {title}."
            ref_html = f"{author_str} {title}."
            
            if editor:
                ref_plain += f" In: {editor}, editors."
                ref_html += f" In: {editor}, editors."
            if source:
                ref_plain += f" {source}."
                ref_html += f" {source}."
            if place and publisher:
                ref_plain += f" {place}: {publisher};"
                ref_html += f" {place}: {publisher};"
            elif publisher:
                ref_plain += f" {publisher};"
                ref_html += f" {publisher};"
            ref_plain += f" {year}."
            ref_html += f" {year}."
            if pages:
                condensed = condense_pages(pages)
                ref_plain += f" p. {condensed}."
                ref_html += f" p. {condensed}."
            if notes:
                ref_plain += notes
                ref_html += notes

        elif ref_type == "Book":
            place = metadata.get("place") or metadata.get("place_of_publication")
            ref_plain = f"{author_str} {title}."
            ref_html = f"{author_str} {title}."
            if place and publisher:
                ref_plain += f" {place}: {publisher};"
                ref_html += f" {place}: {publisher};"
            elif publisher:
                ref_plain += f" {publisher};"
                ref_html += f" {publisher};"
            ref_plain += f" {year}."
            ref_html += f" {year}."
            if notes:
                ref_plain += notes
                ref_html += notes

        elif ref_type == "Web Page":
            place = metadata.get("place") or metadata.get("place_of_publication")
            ref_plain = f"{author_str} {title} [Internet]."
            ref_html = f"{author_str} {title} [Internet]."
            if place and publisher:
                ref_plain += f" {place}: {publisher};"
                ref_html += f" {place}: {publisher};"
            elif publisher:
                ref_plain += f" {publisher};"
                ref_html += f" {publisher};"
            ref_plain += f" {year}."
            ref_html += f" {year}."
            if notes:
                ref_plain += notes
                ref_html += notes

        elif ref_type in ("Dissertation", "Thesis"):
            place = metadata.get("place") or metadata.get("place_of_publication")
            ref_plain = f"{author_str} {title} [dissertation]."
            ref_html = f"{author_str} {title} [dissertation]."
            if place and publisher:
                ref_plain += f" {place}: {publisher};"
                ref_html += f" {place}: {publisher};"
            elif publisher:
                ref_plain += f" {publisher};"
                ref_html += f" {publisher};"
            ref_plain += f" {year}."
            ref_html += f" {year}."
            if notes:
                ref_plain += notes
                ref_html += notes

        else:
            ref_plain = f"{author_str} {title}."
            ref_html = f"{author_str} {title}."
            if source:
                ref_plain += f" {source}."
                ref_html += f" {source}."
            ref_plain += f" {year}."
            ref_html += f" {year}."
            if notes:
                ref_plain += notes
                ref_html += notes
    
    # ─── Fallback (unknown style) ───
    else:
        ref_plain = f"{author_str} ({year}) {title}."
        ref_html = f"{author_str} ({year}) <i>{title}</i>."
        if source:
            ref_plain += f" {source}."
            ref_html += f" <i>{source}</i>."
        if doi_str:
            ref_plain += f" {doi_str}"
            ref_html += f" {doi_str}"
    
    return {
        "formatted": ref_plain,
        "formatted_html": ref_html,
        "type": ref_type,
        "metadata": metadata,
    }
