package com.example.tiendas3b

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TextQualityTest {
    @Test fun labelNeedsWordsAndPrice() {
        assertTrue(textWarnings(PhotoType.LABEL, "").size == 2)
        assertFalse(textWarnings(PhotoType.LABEL, "ARROZ SOS $30").isNotEmpty())
    }

    @Test fun barcodeAloneDoesNotCountAsPrice() {
        assertTrue(textWarnings(PhotoType.LABEL, "ARROZ 7501372812565").any { it.contains("precio") })
    }

    @Test fun productAndStoreNeedVisibleWords() {
        assertTrue(textWarnings(PhotoType.PRODUCT, "").isNotEmpty())
        assertTrue(textWarnings(PhotoType.STORE, "123").isNotEmpty())
        assertTrue(textWarnings(PhotoType.STORE, "Walmart").isEmpty())
    }
}
