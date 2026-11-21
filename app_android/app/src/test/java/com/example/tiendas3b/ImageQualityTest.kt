package com.example.tiendas3b

import org.junit.Assert.assertTrue
import org.junit.Test

class ImageQualityTest {
    @Test fun darkAndUniformImageRequestsMoreLightAndFocus() {
        val result = assessLuminance(IntArray(400) { 10 }, 20, 20)
        assertTrue(result.messages.any { it.contains("poca luz") })
        assertTrue(result.messages.any { it.contains("borrosa") })
    }

    @Test fun brightImageRequestsLessLight() {
        val result = assessLuminance(IntArray(400) { 250 }, 20, 20)
        assertTrue(result.messages.any { it.contains("demasiada luz") })
    }

    @Test fun detailedBackgroundDoesNotHideBlurredCenter() {
        val values = IntArray(40 * 40) { i ->
            val x = i % 40
            val y = i / 40
            if (x in 10 until 30 && y in 10 until 30) 128
            else if ((x / 2) % 2 == 0) 40 else 210
        }
        assertTrue(assessLuminance(values, 40, 40).messages.any { it.contains("borrosa") })
    }

    @Test fun invalidImageCannotPass() {
        assertTrue(assessLuminance(intArrayOf(), 0, 0).messages.isNotEmpty())
    }
}
