import io
import traceback
from fontTools.ttLib import TTFont, newTable

try:
    otf = TTFont(sfntVersion='OTTO')

    # TESTING FIXED-POINT MULTIPLIERS FOR EACH TABLE
    # 1. head (tableVersion uses fi2ve, fontRevision uses 16.16F plain multiplier?)
    head = newTable('head')
    head.tableVersion    = 0x00010000
    head.fontRevision    = 0x00010000
    head.checkSumAdjustment = 0
    head.magicNumber     = 0x5F0F3CF5
    head.flags           = 0x000B
    head.unitsPerEm      = 1000
    head.created         = head.modified = 0
    head.xMin = head.yMin = head.xMax = head.yMax = 0
    head.macStyle        = 0
    head.lowestRecPPEM   = 8
    head.fontDirectionHint = 2
    head.indexToLocFormat  = 0
    head.glyphDataFormat   = 0
    otf['head'] = head
    
    # 2. hhea
    hhea = newTable('hhea')
    hhea.tableVersion      = 0x00010000
    hhea.ascent            = 800
    hhea.descent           = -200
    hhea.lineGap           = 0
    hhea.advanceWidthMax   = 1000
    hhea.minLeftSideBearing  = 0
    hhea.minRightSideBearing = 0
    hhea.xMaxExtent        = 0
    hhea.caretSlopeRise    = 1
    hhea.caretSlopeRun     = 0
    hhea.caretOffset       = 0
    hhea.reserved0 = hhea.reserved1 = hhea.reserved2 = hhea.reserved3 = 0
    hhea.metricDataFormat  = 0
    hhea.numberOfHMetrics  = 1
    otf['hhea'] = hhea
    
    # 3. post
    post = newTable('post')
    post.formatType        = 0x00030000
    post.italicAngle       = 0
    post.underlinePosition  = -75
    post.underlineThickness = 50
    post.isFixedPitch      = 0
    post.minMemType42 = post.maxMemType42 = 0
    post.minMemType1  = post.maxMemType1  = 0
    otf['post'] = post

    print("Testing HEAD compilation with head.fontRevision = 0x00010000")
    try:
        otf.tables['head'].compile(otf)
        print("HEAD OK")
    except Exception as e:
        print(f"HEAD CRASH: {e}")

    print("Testing HHEA compilation with hhea.tableVersion = 0x00010000")
    try:
        otf.tables['hhea'].compile(otf)
        print("HHEA OK")
    except Exception as e:
        print(f"HHEA CRASH: {e}")

    print("Testing POST compilation with post.formatType = 0x00030000")
    try:
        otf.tables['post'].compile(otf)
        print("POST OK")
    except Exception as e:
        print(f"POST CRASH: {e}")

except Exception as e:
    traceback.print_exc()
