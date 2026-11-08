package org.deeptutor.proximity

import android.nfc.NdefMessage
import android.nfc.NdefRecord
import android.nfc.cardemulation.HostApduService
import android.os.Bundle

/** Read-only Type 4 NDEF tag. The token never represents ownership. */
class TradeNdefService : HostApduService() {
  private val aid = byteArrayOf(0xD2.toByte(), 0x76, 0, 0, 0x85.toByte(), 1, 1)
  private val ok = byteArrayOf(0x90.toByte(), 0)
  private val missing = byteArrayOf(0x6A, 0x82.toByte())
  private val cc = byteArrayOf(0, 15, 0x20, 0, 0xF6.toByte(), 0, 0xFF.toByte(), 4, 6, 0xE1.toByte(), 4, 4, 0, 0, 0xFF.toByte())
  private var selectedApp = false
  private var file: ByteArray? = null

  override fun processCommandApdu(command: ByteArray, extras: Bundle?): ByteArray {
    val token = LocalToken.current()
    if (command.size < 5 || token.isEmpty()) return missing
    fun value(index: Int) = command[index].toInt() and 255
    return when (value(1)) {
      0xA4 -> {
        val size = value(4)
        if (command.size < 5 + size) return missing
        val selection = command.copyOfRange(5, 5 + size)
        if (value(2) == 4 && selection.contentEquals(aid)) {
          selectedApp = true
          file = null
          return ok
        }
        if (!selectedApp || size != 2 || value(5) != 0xE1) return missing
        file = when (value(6)) {
          3 -> cc
          4 -> {
            val message = NdefMessage(arrayOf(NdefRecord.createTextRecord("en", token.toString(Charsets.UTF_8)))).toByteArray()
            byteArrayOf((message.size shr 8).toByte(), message.size.toByte()) + message
          }
          else -> null
        }
        if (file != null) ok else missing
      }
      0xB0 -> {
        val data = file ?: return missing
        val offset = (value(2) shl 8) or value(3)
        if (offset > data.size) return missing
        val length = if (value(4) == 0) 256 else value(4)
        data.copyOfRange(offset, minOf(offset + length, data.size)) + ok
      }
      else -> byteArrayOf(0x6D, 0)
    }
  }

  override fun onDeactivated(reason: Int) {
    selectedApp = false
    file = null
  }
}
