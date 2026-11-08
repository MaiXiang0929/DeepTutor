package org.deeptutor.proximity

import android.annotation.SuppressLint
import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.os.ParcelUuid
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.util.UUID

internal object LocalToken {
  @Volatile var value: ByteArray = byteArrayOf()
  @Volatile var expiresAt: Long = 0
  fun current() = if (System.currentTimeMillis() < expiresAt) value else byteArrayOf()
}

@SuppressLint("MissingPermission")
class ProximityAdvertiserModule : Module() {
  private val serviceId = UUID.fromString("6e402810-1c65-44c7-94e7-5048e29b2210")
  private val tokenId = UUID.fromString("6e402811-1c65-44c7-94e7-5048e29b2210")
  private var gatt: BluetoothGattServer? = null
  private var advertiser: BluetoothLeAdvertiser? = null
  private val advertising = object : AdvertiseCallback() {}

  override fun definition() = ModuleDefinition {
    Name("ProximityAdvertiser")

    AsyncFunction("setToken") { token: String ->
      LocalToken.value = token.toByteArray(Charsets.UTF_8)
      LocalToken.expiresAt = System.currentTimeMillis() + 60_000
    }

    AsyncFunction("startAdvertising") {
      stopBle()
      val context = appContext.reactContext ?: error("No application context")
      val manager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
      val adapter = manager.adapter ?: error("Bluetooth is unavailable")
      advertiser = adapter.bluetoothLeAdvertiser ?: error("BLE advertising is unavailable")
      val callback = object : BluetoothGattServerCallback() {
        override fun onServiceAdded(status: Int, service: BluetoothGattService) {
          if (status != BluetoothGatt.GATT_SUCCESS || service.uuid != serviceId) return
          advertiser?.startAdvertising(
            AdvertiseSettings.Builder().setConnectable(true).setTimeout(60_000)
              .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY).build(),
            AdvertiseData.Builder().addServiceUuid(ParcelUuid(serviceId)).build(),
            advertising
          )
        }

        override fun onCharacteristicReadRequest(
          device: BluetoothDevice, requestId: Int, offset: Int, characteristic: BluetoothGattCharacteristic
        ) {
          val value = LocalToken.current()
          if (characteristic.uuid != tokenId || value.isEmpty() || offset > value.size) {
            gatt?.sendResponse(device, requestId, BluetoothGatt.GATT_INVALID_OFFSET, offset, null)
          } else {
            gatt?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, value.copyOfRange(offset, value.size))
          }
        }
      }
      gatt = manager.openGattServer(context, callback) ?: error("Cannot open GATT server")
      val service = BluetoothGattService(serviceId, BluetoothGattService.SERVICE_TYPE_PRIMARY)
      service.addCharacteristic(BluetoothGattCharacteristic(
        tokenId, BluetoothGattCharacteristic.PROPERTY_READ, BluetoothGattCharacteristic.PERMISSION_READ
      ))
      check(gatt?.addService(service) == true) { "Cannot publish trade service" }
    }

    AsyncFunction("stop") { clear() }
    OnDestroy { clear() }
  }

  private fun stopBle() {
    runCatching { advertiser?.stopAdvertising(advertising) }
    runCatching { gatt?.close() }
    advertiser = null
    gatt = null
  }

  private fun clear() {
    LocalToken.expiresAt = 0
    LocalToken.value = byteArrayOf()
    stopBle()
  }
}
