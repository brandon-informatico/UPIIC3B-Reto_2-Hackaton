package com.example.tiendas3b

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class FacadeQualityTest {
    @Test fun mapsTextBoundsToPreview() {
        val text = FacadeText(100, 200, 500, 400, 7)
        assertEquals(FacadeRegion(25, 50, 125, 100), facadeRegion(text, 800, 800, 200, 200))
    }

    @Test fun rejectsTextTooSmallForFocusCheck() {
        val text = FacadeText(100, 100, 130, 130, 4)
        assertNull(facadeRegion(text, 800, 800, 200, 200))
    }

    @Test fun rejectsInvalidImageDimensions() {
        assertNull(facadeRegion(FacadeText(0, 0, 50, 50, 5), 0, 100, 100, 100))
    }
}
