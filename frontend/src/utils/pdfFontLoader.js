/**
 * Loads embedded PDF fonts into the browser via @font-face.
 * 
 * These font-faces use the font's PostScript name (without subset tag),
 * so CSS `font-family: "MetaProLight-Regular"` resolves correctly.
 * 
 * Fonts are installed globally (into document.head). They remain available
 * for the session; unloadPDFFonts() cleans them up when a new PDF loads.
 */

const installedStyleElements = new Set();
const loadedFontNames = new Set();

export async function loadPDFFonts(fontsData) {
  // fontsData shape: { "NBUDXT+MetaProLight-Regular": { data, format, postscript_name, subset_tag } }
  
  for (const [basename, meta] of Object.entries(fontsData)) {
    const psName = meta.postscript_name || basename;
    
    // Skip if already loaded (can happen with multi-page PDFs referencing same font)
    if (loadedFontNames.has(psName)) continue;
    loadedFontNames.add(psName);
    
    const mimeFormat = {
      'otf': 'opentype',
      'ttf': 'truetype',
      'woff': 'woff',
      'woff2': 'woff2',
    }[meta.format] || 'opentype';
    
    // Register with both PostScript name and subset-prefixed name so CSS
    // font-family lookup succeeds regardless of which form it was given.
    const familyNames = [psName];
    if (basename !== psName) familyNames.push(basename);
    
    // Use the FontFace API for reliable async loading & readiness detection.
    const src = `url(data:font/${meta.format};base64,${meta.data}) format('${mimeFormat}')`;
    
    try {
      for (const familyName of familyNames) {
        const fontFace = new FontFace(familyName, src);
        const loaded = await fontFace.load();
        document.fonts.add(loaded);
      }
      console.log(`[pdfFontLoader] Loaded font: ${psName}`);
    } catch (e) {
      console.warn(`[pdfFontLoader] Failed to load ${psName}:`, e);
    }
  }
}

export function unloadPDFFonts() {
  // Remove all @font-face style elements we installed.
  for (const el of installedStyleElements) {
    if (el.parentNode) el.parentNode.removeChild(el);
  }
  installedStyleElements.clear();
  loadedFontNames.clear();
  // Note: document.fonts entries added via .add() remain. Calling
  // document.fonts.delete(fontFace) would require tracking each FontFace.
  // In practice, loading a new PDF's fonts overwrites by family name.
}
