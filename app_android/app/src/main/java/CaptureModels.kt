package com.example.tiendas3b

/**
 * Una captura agrupa las tres evidencias con los datos disponibles en campo.
 * Los códigos se conservan como texto para no perder ceros iniciales.
 */
data class CaptureRecord(
    val captureId: String,
    val storeName: String,
    val capturedAt: String,
    val capturedBarcode: String?,
    val capturedPrice: String?,
    val expectedProductId: String?,
    val facadeImage: String?,
    val productImage: String?,
    val shelfImage: String?
)

/** Un catálogo aporta datos de referencia, no una decisión sobre la captura. */
data class ProductReference(
    val id: String,
    val name: String,
    val barcode: String?,
    val unit: String?,
    val quantity: String?
)

/** La falta de evidencia se conserva como incertidumbre. */
enum class EvidenceStatus {
    MATCH, MISMATCH, UNKNOWN
}

data class CaptureEvidence(
    val store: EvidenceStatus = EvidenceStatus.UNKNOWN,
    val product: EvidenceStatus = EvidenceStatus.UNKNOWN,
    val barcode: EvidenceStatus = EvidenceStatus.UNKNOWN,
    val price: EvidenceStatus = EvidenceStatus.UNKNOWN,
    val detectedPrice: String? = null,
    val detectedBarcode: String? = null
)
