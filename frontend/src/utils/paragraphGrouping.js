/**
 * Groups a flat array of PDF.js text items into paragraph blocks,
 * with column-aware layout detection and column-width bounding boxes.
 *
 * Algorithm (3-phase):
 *
 *   Phase 1 — Detect column boundaries from x-coverage gaps.
 *     Build a 1pt-resolution coverage array across the page width using
 *     body-text items only (width < 0.6 × pageWidth — excludes full-width
 *     titles/abstracts that would mask the column gutter). Find contiguous
 *     zero-coverage gaps wider than 5% of page width → column separators.
 *
 *   Phase 2 — Assign each item to a column index based on which zone
 *     its pdfX falls into relative to the detected separators.
 *
 *   Phase 3 — Within each column independently:
 *     a. Compute column right edge from 90th-percentile of line right edges
 *     b. Sort by pdfY_top ascending, then pdfX ascending
 *     c. Group into lines (baseline tolerance: ±fontSize * 0.4)
 *     d. Group consecutive lines into paragraphs
 *     e. Build output blocks using column boundaries for bbox width
 *
 * @param {Array} items     - pageMetadata[pageNum].items from Viewer.jsx
 * @param {number} pageWidth - page width in PDF points (for column detection)
 * @returns {Array} paragraphBlocks
 */
export function groupItemsIntoParagraphs(items, pageWidth = 612) {
  if (!items || items.length === 0) return [];

  // Step 0: Filter (same as Viewer.jsx — exclude pure-digit superscripts)
  const filtered = items.filter(item =>
    item.str && item.str.trim() !== '' && !item.str.match(/^\d+$/)
  );

  if (filtered.length === 0) return [];

  // ─── Phase 1: Detect column boundaries from x-coverage ─────────────
  const separators = _detectColumnBoundaries(filtered, pageWidth);

  // ─── Phase 2: Assign each item to a column ─────────────────────────
  const withColumn = filtered.map(item => ({
    ...item,
    _colIdx: separators.filter(sep => item.pdfX >= sep).length
  }));

  // ─── Phase 3: Group per column, then merge all blocks ──────────────
  const numCols = separators.length + 1;
  const allBlocks = [];

  for (let col = 0; col < numCols; col++) {
    const colItems = withColumn.filter(it => it._colIdx === col);
    if (colItems.length === 0) continue;

    // Column left edge: either the separator midpoint or the leftmost text x
    const colLeft = col > 0
      ? separators[col - 1]
      : Math.min(...colItems.map(it => it.pdfX));

    // Column right edge: either the next separator or computed from text
    const colSepRight = col < separators.length
      ? separators[col]
      : pageWidth;

    // Compute column width for paragraph-break thresholds
    const colWidth = colSepRight - colLeft;

    const blocks = _groupColumnIntoParagraphs(colItems, colWidth, colLeft, colSepRight);
    allBlocks.push(...blocks);
  }

  // Sort final blocks top-to-bottom, left-to-right so the UI index order
  // is visually consistent (top-left block = index 0)
  allBlocks.sort((a, b) => a.bbox.y - b.bbox.y || a.bbox.x - b.bbox.x);

  return allBlocks;
}


// ═══════════════════════════════════════════════════════════════════════
// Phase 1 internals
// ═══════════════════════════════════════════════════════════════════════

/**
 * Detect column separator positions by finding tall vertical whitespace
 * gaps in the x-coverage of body-text items.
 *
 * Only items narrower than 60% of page width are used for coverage, so
 * full-width headings/abstracts don't fill in the column gutter.
 *
 * @returns {number[]} sorted array of x-positions marking column splits
 *                     (e.g. [306] for a two-column page split at x=306)
 */
function _detectColumnBoundaries(items, pageWidth) {
  // Use only body-text-width items for gap detection
  const bodyItems = items.filter(it => (it.pdfW || 0) < pageWidth * 0.6);
  if (bodyItems.length < 2) return [];

  // Build 1pt-resolution x-coverage array
  const coverageLen = Math.ceil(pageWidth) + 1;
  const coverage = new Uint8Array(coverageLen);

  for (const item of bodyItems) {
    const x0 = Math.max(0, Math.floor(item.pdfX));
    const x1 = Math.min(coverageLen - 1, Math.ceil(item.pdfX + (item.pdfW || 0)));
    for (let x = x0; x <= x1; x++) coverage[x] = 1;
  }

  // Find contiguous zero-coverage gaps ≥ 5% of page width
  const minGapWidth = pageWidth * 0.05;
  const separators = [];
  let gapStart = -1;

  // Skip the margins: start scanning from the leftmost coverage and stop
  // at the rightmost, so page margins don't produce false column splits.
  let scanLeft = 0;
  let scanRight = coverageLen - 1;
  while (scanLeft < coverageLen && coverage[scanLeft] === 0) scanLeft++;
  while (scanRight > 0 && coverage[scanRight] === 0) scanRight--;

  for (let x = scanLeft; x <= scanRight + 1; x++) {
    const val = x <= scanRight ? coverage[x] : 1; // sentinel at end
    if (val === 0 && gapStart === -1) {
      gapStart = x;
    } else if (val === 1 && gapStart !== -1) {
      const gapWidth = x - gapStart;
      if (gapWidth >= minGapWidth) {
        separators.push(gapStart + gapWidth / 2); // midpoint of gap
      }
      gapStart = -1;
    }
  }

  return separators;
}


// ═══════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════

/**
 * Compute the Nth-percentile right edge from an array of line groups.
 * Each "line" is an array of items. The right edge of a line is
 * max(item.pdfX + item.pdfW) across that line's items.
 *
 * Used to find the true column margin from justified text:
 * 90th percentile ignores short last-lines and indented block quotes
 * without being fooled by outliers.
 *
 * @param {Array[]} lines - array of line arrays (each line = array of items)
 * @param {number} pct - percentile as a fraction (0.0–1.0), default 0.9
 * @returns {number} the right-edge x-coordinate at the given percentile
 */
function _percentileRightEdge(lines, pct = 0.9) {
  if (!lines || lines.length === 0) return 0;

  const rights = lines.map(line =>
    Math.max(...line.map(i => i.pdfX + (i.pdfW || 0)))
  );
  rights.sort((a, b) => a - b);

  const idx = Math.min(Math.floor(rights.length * pct), rights.length - 1);
  return rights[idx];
}


// ═══════════════════════════════════════════════════════════════════════
// Phase 3 internals — runs independently per column
// ═══════════════════════════════════════════════════════════════════════

/**
 * Given items that all belong to a single column, group them into
 * lines and then paragraphs.
 *
 * @param {Array} colItems - all items in this column
 * @param {number} colWidth - column width for paragraph-break thresholds
 * @param {number} colLeft - left edge of the column (x coordinate)
 * @param {number} colSepRight - right separator boundary (may be pageWidth)
 */
function _groupColumnIntoParagraphs(colItems, colWidth, colLeft, colSepRight) {
  // Sort by Y then X within this column
  const sorted = [...colItems].sort((a, b) =>
    a.pdfY_top - b.pdfY_top || a.pdfX - b.pdfX
  );

  // ─── Group into lines ──────────────────────────────────────────────
  // Items within ±fontSize * 0.4 of each other's Y-top are on the same line
  const lines = [];
  let currentLine = [sorted[0]];

  for (let i = 1; i < sorted.length; i++) {
    const prev = currentLine[0]; // anchor to first item in current line
    const curr = sorted[i];
    const tolerance = (prev.fontSize || 12) * 0.4;

    if (Math.abs(curr.pdfY_top - prev.pdfY_top) <= tolerance) {
      currentLine.push(curr);
    } else {
      lines.push(currentLine);
      currentLine = [curr];
    }
  }
  lines.push(currentLine);

  // Sort items within each line by x position (left to right)
  for (const line of lines) {
    line.sort((a, b) => a.pdfX - b.pdfX);
  }

  // ─── Compute the column's true right edge ──────────────────────────
  // Use the 90th-percentile right edge of column-only lines.
  // IMPORTANT: Full-width items (titles, abstracts) get assigned to col 0
  // based on their pdfX, but their right edge extends past the separator
  // into the adjacent column. We MUST filter these out before computing
  // the percentile, otherwise they inflate colRight to the full page width.
  const columnOnlyLines = lines.filter(line => {
    const maxRight = Math.max(...line.map(i => i.pdfX + (i.pdfW || 0)));
    return maxRight <= colSepRight + 5; // 5pt tolerance for rounding
  });
  const textRightEdge = _percentileRightEdge(
    columnOnlyLines.length > 0 ? columnOnlyLines : lines,
    0.9
  );
  const colRight = Math.min(textRightEdge, colSepRight);

  // ─── Group lines into paragraph blocks ─────────────────────────────
  // New paragraph when:
  //   - Vertical gap > 1.5× lineHeight
  //   - OR x-start differs from current block's left edge by > 20% of
  //     column width (indent-based break, e.g. block quote)
  const blocks = [];
  let currentBlock = [lines[0]];

  for (let i = 1; i < lines.length; i++) {
    const prevLine = currentBlock[currentBlock.length - 1];
    const currLine = lines[i];

    const prevY = Math.min(...prevLine.map(it => it.pdfY_top));
    const currY = Math.min(...currLine.map(it => it.pdfY_top));
    const prevFontSize = prevLine[0].fontSize || 12;
    const lineHeight = prevFontSize * 1.2;
    const verticalGap = currY - prevY;

    // Current block's left edge (anchored to block, not global)
    const blockLeftEdge = Math.min(
      ...currentBlock.flat().map(it => it.pdfX)
    );
    const currLineLeft = Math.min(...currLine.map(it => it.pdfX));
    const columnThreshold = colWidth * 0.20;
    const isColumnBreak = Math.abs(currLineLeft - blockLeftEdge) > columnThreshold;

    const isLargeGap = verticalGap > lineHeight * 1.5;

    if (isLargeGap || isColumnBreak) {
      blocks.push(_buildBlock(currentBlock, colLeft, colRight));
      currentBlock = [currLine];
    } else {
      currentBlock.push(currLine);
    }
  }
  blocks.push(_buildBlock(currentBlock, colLeft, colRight));

  return blocks;
}


// ═══════════════════════════════════════════════════════════════════════
// Block builder — uses column boundaries for x-extent
// ═══════════════════════════════════════════════════════════════════════

/**
 * Build a paragraph block object from grouped lines.
 *
 * The bbox x-extent uses column boundaries (colLeft, colRight) instead of
 * text item union, so the bounding box matches the full column width.
 * This ensures insert_htmlbox reflows text to fill the correct width.
 *
 * @param {Array[]} blockLines - array of line arrays
 * @param {number} colLeft - column left boundary
 * @param {number} colRight - column right boundary (90th-percentile)
 */
function _buildBlock(blockLines, colLeft, colRight) {
  const allItems = blockLines.flat();

  // Bounding box: column boundaries for x, text union for y
  const x = colLeft;
  const y = Math.min(...allItems.map(i => i.pdfY_top));
  const x2 = colRight;
  const y2 = Math.max(...allItems.map(i => i.pdfY_top + (i.pdfH || 0)));

  // Concatenate text: spaces within lines, \n between lines
  const text = blockLines
    .map(line => line.map(i => i.str).join(' '))
    .join('\n');

  // Dominant font/color: use the most common values
  const fontSizes = allItems.map(i => i.fontSize).filter(Boolean);
  const fontNames = allItems.map(i => i.fontName).filter(Boolean);
  const colors = allItems.map(i => i.color).filter(Boolean);

  // Compute actual line height from inter-line distances
  let computedLineHeight = (fontSizes[0] || 12) * 1.2;
  if (blockLines.length >= 2) {
    const lineYs = blockLines.map(line =>
      Math.min(...line.map(i => i.pdfY_top))
    );
    const gaps = [];
    for (let i = 1; i < lineYs.length; i++) {
      gaps.push(lineYs[i] - lineYs[i - 1]);
    }
    if (gaps.length > 0) {
      computedLineHeight = gaps.reduce((a, b) => a + b, 0) / gaps.length;
    }
  }

  // Per-line metadata for backend span-level reconstruction
  const lines = blockLines.map(lineItems => ({
    items: lineItems,
    y: Math.min(...lineItems.map(i => i.pdfY_top)),
    baseline: lineItems[0]?.pdfY_base || 0,
  }));

  return {
    items: allItems,
    bbox: { x, y, w: x2 - x, h: y2 - y },
    text,
    lines,
    fontSize: _mode(fontSizes) || 12,
    fontName: _mode(fontNames) || 'Unknown',
    color: _mode(colors) || 'black',
    lineHeight: computedLineHeight,
  };
}


/**
 * Return the most common value in an array (statistical mode).
 */
function _mode(arr) {
  if (!arr.length) return null;
  const counts = {};
  let maxVal = arr[0];
  let maxCount = 0;
  for (const v of arr) {
    counts[v] = (counts[v] || 0) + 1;
    if (counts[v] > maxCount) {
      maxCount = counts[v];
      maxVal = v;
    }
  }
  return maxVal;
}
