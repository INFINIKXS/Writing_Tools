import sys

file_path = 'frontend/src/components/PDFEditor/Viewer.jsx'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_effect = '''  // Extract items for each page when spacingData is available.
  // This runs whenever spacingData changes (first load, or after a bake)
  // OR when a page reports its size via onLoadSuccess.
  // Only pages that have a known size AND haven't been extracted yet will
  // be processed, so this naturally handles all timing scenarios:
  //   - spacingData arrives before pages load: waits for sizes, then extracts
  //   - pages load before spacingData arrives: waits for spacingData, then extracts
  //   - both already ready (zoom change, etc.): skipped due to extraction guard
  useEffect(() => {
    if (!spacingData) return;

    Object.entries(pageMetadata).forEach(([pageNumStr, meta]) => {
      const pageNum = parseInt(pageNumStr);
      const index = pageNum - 1;
      if (!meta?.size) return;
      if (pageItemsExtracted.current[pageNum]) return;

      const pageData = spacingData.find((p) => p.page === index);
      if (!pageData || !pageData.blocks) return;

      pageItemsExtracted.current[pageNum] = true;

      // -- Step 1: Build one item per line AND index words by baseline --
      const lineItems = [];
      const allWordsByBaseline = {};

      pageData.blocks.forEach((blockData) => {
        if (!blockData.lines) return;
        blockData.lines.forEach((lineData) => {
          const words = groupCharsIntoWords(lineData);
          if (words.length === 0) return;

          const baselineKey = Math.round(words[0][0].origin_y * 2) / 2;
          if (!allWordsByBaseline[baselineKey]) allWordsByBaseline[baselineKey] = [];
          words.forEach((w) => allWordsByBaseline[baselineKey].push(w));

          const allCharsInLine = words.flat();
          const lineStr = words.map((wc) => wc.map((c) => c.c).join('')).join(' ');
          const lineX0 = allCharsInLine[0].x0;
          const lineX1 = allCharsInLine[allCharsInLine.length - 1].x1;
          const lineY_base = allCharsInLine[0].origin_y;
          const lineY_top = Math.min(...allCharsInLine.map((c) => c.y0));
          const lineH = Math.max(...allCharsInLine.map((c) => c.y1 - c.y0));
          const lineFontSize = allCharsInLine[0].size;
          const lineFontName = allCharsInLine[0].font;
          let hasSuperscript = false;
          for (const ch of allCharsInLine) {
            if (ch.is_superscript) hasSuperscript = true;
          }
          const ascenderH = Math.max(0, lineY_base - lineY_top);
          const descenderH = Math.max(0, lineY_top + lineH - lineY_base);

          lineItems.push({
            str: lineStr,
            pdfX: lineX0,
            pdfY_base: lineY_base,
            pdfY_top: lineY_top,
            pdfW: lineX1 - lineX0,
            pdfH: lineH,
            fontSize: lineFontSize,
            fontName: lineFontName,
            hasSuperscript,
            ascender_h: ascenderH,
            descender_h: descenderH,
            color: 'black',
            _baselineKey: baselineKey,
          });
        });
      });

      // -- Step 2: Find baselines that need regrouping --
      const blockCountPerBaseline = {};
      pageData.blocks.forEach((blockData, bi) => {
        if (!blockData.lines) return;
        blockData.lines.forEach((lineData) => {
          const words = groupCharsIntoWords(lineData);
          if (words.length === 0) return;
          const baselineKey = Math.round(words[0][0].origin_y * 2) / 2;
          if (!blockCountPerBaseline[baselineKey]) blockCountPerBaseline[baselineKey] = new Set();
          blockCountPerBaseline[baselineKey].add(bi);
        });
      });

      const baselinesNeedingRegroup = new Set();
      for (const [baseline, blockSet] of Object.entries(blockCountPerBaseline)) {
        if (blockSet.size > 1) baselinesNeedingRegroup.add(parseFloat(baseline));
      }

      // -- Step 3: Column index helper --
      const columns = pageData.columns || null;
      const getColumnIndex = (x) => {
        if (!columns || columns.length <= 1) return 0;
        const splitX = (columns[0][1] + columns[1][0]) / 2;
        return x < splitX ? 0 : 1;
      };

      // -- Step 4: Start with ALL line items from untouched baselines --
      const finalItems = [];
      for (const li of lineItems) {
        if (baselinesNeedingRegroup.has(li._baselineKey)) continue;
        finalItems.push(li);
      }

      // -- Step 5: Regroup only the affected baselines --
      for (const baseline of baselinesNeedingRegroup) {
        const wordsOnLine = allWordsByBaseline[baseline] || [];
        if (wordsOnLine.length === 0) continue;
        wordsOnLine.sort((a, b) => a[0].x0 - b[0].x0);

        let currentItem = null;
        let currentCol = -1;

        for (const wordChars of wordsOnLine) {
          const wordStr = wordChars.map((c) => c.c).join('');
          const wordX0 = wordChars[0].x0;
          const wordY_base = wordChars[0].origin_y;
          const wordY_top = Math.min(...wordChars.map((c) => c.y0));
          const wordW = wordChars[wordChars.length - 1].x1 - wordChars[0].x0;
          const wordH = Math.max(...wordChars.map((c) => c.y1 - c.y0));
          const wordFontSize = wordChars[0].size;
          const wordFontName = wordChars[0].font;
          let wordHasSuperscript = false;
          for (const ch of wordChars) {
            if (ch.is_superscript) wordHasSuperscript = true;
          }
          const ascenderH = Math.max(0, wordY_base - wordY_top);
          const descenderH = Math.max(0, wordY_top + wordH - wordY_base);
          const wordCol = getColumnIndex(wordX0);

          if (!currentItem) {
            currentItem = {
              str: wordStr, pdfX: wordX0, pdfY_base: wordY_base, pdfY_top: wordY_top,
              pdfW: wordW, pdfH: wordH, fontSize: wordFontSize, fontName: wordFontName,
              hasSuperscript: wordHasSuperscript, ascender_h: ascenderH, descender_h: descenderH,
              color: 'black',
            };
            currentCol = wordCol;
          } else {
            const sameColumn = wordCol === currentCol;
            const gap = wordX0 - (currentItem.pdfX + currentItem.pdfW);
            if (sameColumn && gap <= currentItem.fontSize * 1.5) {
              const needsSpace = gap > currentItem.fontSize * 0.12;
              currentItem.str += (needsSpace ? ' ' : '') + wordStr;
              currentItem.pdfW = wordX0 + wordW - currentItem.pdfX;
              currentItem.pdfH = Math.max(currentItem.pdfH, wordH);
              currentItem.pdfY_top = Math.min(currentItem.pdfY_top, wordY_top);
              if (wordHasSuperscript) currentItem.hasSuperscript = true;
              if (ascenderH > currentItem.ascender_h) currentItem.ascender_h = ascenderH;
              if (descenderH > currentItem.descender_h) currentItem.descender_h = descenderH;
            } else {
              finalItems.push(currentItem);
              currentItem = {
                str: wordStr, pdfX: wordX0, pdfY_base: wordY_base, pdfY_top: wordY_top,
                pdfW: wordW, pdfH: wordH, fontSize: wordFontSize, fontName: wordFontName,
                hasSuperscript: wordHasSuperscript, ascender_h: ascenderH, descender_h: descenderH,
                color: 'black',
              };
              currentCol = wordCol;
            }
          }
        }
        if (currentItem) finalItems.push(currentItem);
      }

      // -- Sort final items in reading order --
      finalItems.sort((a, b) => {
        const yDiff = a.pdfY_base - b.pdfY_base;
        if (Math.abs(yDiff) > 1.5) return yDiff;
        return a.pdfX - b.pdfX;
      });

      setPageMetadata((prev) => ({
        ...prev,
        [pageNum]: { ...prev[pageNum], items: finalItems },
      }));
    });
  }, [spacingData, pageMetadata]);\n'''

new_onload = '''              onLoadSuccess={(page) => {
                // Just store the page size here. Item extraction happens in a
                // separate useEffect that waits for spacingData to be available.
                // We don't extract items in this handler because onLoadSuccess
                // can fire before spacingData arrives — and we don't want to
                // produce "placeholder" items that get rendered and then have
                // to be replaced.
                const newSize = {
                  height: page.originalHeight || page.view[3],
                };
                setPageMetadata((prev) => ({
                  ...prev,
                  [index + 1]: { ...(prev[index + 1] || {}), size: newSize },
                }));
              }}
'''

# Delete lines 272 to 283 and insert new_effect
# (lines list is 0-indexed, so 272 is line 273)
del lines[272:284]
lines.insert(272, new_effect)

# Find the onLoadSuccess block
import re
content = "".join(lines)
old_onload_regex = re.compile(r'              onLoadSuccess=\{async \(page\) => \{[\s\S]*?              \}\}(?=\s*onRenderSuccess)', re.MULTILINE)

if old_onload_regex.search(content):
    content = old_onload_regex.sub(new_onload, content)
    print('Replaced onLoadSuccess successfully.')
else:
    print('Failed to find onLoadSuccess block.')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

