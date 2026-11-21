package com.example.tiendas3b

import org.junit.Assert.assertTrue
import org.junit.Test

class ProductQualityTest {
    private val product = ImageArea(20, 20, 180, 180)
    private val words = listOf(
        ReadableText(ImageArea(40, 50, 90, 65), 5),
        ReadableText(ImageArea(40, 75, 90, 90), 5)
    )

    @Test fun noObjectAsksForProduct() {
        assertTrue(productWarnings(emptyList(), emptyList(), 200, 200).any { it.contains("objeto") })
    }

    @Test fun backgroundTextDoesNotValidateProduct() {
        val background = listOf(ReadableText(ImageArea(182, 20, 198, 40), 12))
        assertTrue(productWarnings(listOf(product), background, 200, 200).any { it.contains("texto") })
    }

    @Test fun completeObjectWithSeveralWordsPassesChecks() {
        assertTrue(productWarnings(listOf(product), words, 200, 200).isEmpty())
    }

    @Test fun oneWordIsInsufficient() {
        assertTrue(productWarnings(listOf(product), words.take(1), 200, 200).any { it.contains("texto") })
    }

    @Test fun clippedObjectIsRejected() {
        val clipped = ImageArea(0, 20, 180, 180)
        assertTrue(productWarnings(listOf(clipped), words, 200, 200).any { it.contains("cortado") })
    }

    @Test fun closeFramingWithVisibleEdgesPasses() {
        val closeProduct = ImageArea(2, 2, 198, 198)
        assertTrue(productWarnings(listOf(closeProduct), words, 200, 200).isEmpty())
    }

    @Test fun smallObjectIsRejected() {
        val small = ImageArea(80, 80, 110, 110)
        assertTrue(productWarnings(listOf(small), words, 200, 200).any { it.contains("pequeño") })
    }
}
