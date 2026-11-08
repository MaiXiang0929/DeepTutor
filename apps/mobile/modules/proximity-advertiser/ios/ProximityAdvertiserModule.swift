import CoreBluetooth
import ExpoModulesCore

private final class TradePeripheral: NSObject, CBPeripheralManagerDelegate {
  private let serviceId = CBUUID(string: "6e402810-1c65-44c7-94e7-5048e29b2210")
  private let tokenId = CBUUID(string: "6e402811-1c65-44c7-94e7-5048e29b2210")
  private var manager: CBPeripheralManager?
  private var token = Data()
  private var deadline = Date.distantPast

  func setToken(_ token: String) {
    self.token = Data(token.utf8)
    deadline = Date().addingTimeInterval(60)
  }

  func start() {
    if let manager {
      manager.stopAdvertising()
      manager.removeAllServices()
      publish(manager)
    } else {
      manager = CBPeripheralManager(delegate: self, queue: .main)
    }
  }

  func stop() {
    token = Data()
    manager?.stopAdvertising()
    manager?.removeAllServices()
    manager = nil
  }

  private func publish(_ peripheral: CBPeripheralManager) {
    guard peripheral.state == .poweredOn, !token.isEmpty, Date() < deadline else { return }
    let service = CBMutableService(type: serviceId, primary: true)
    service.characteristics = [
      CBMutableCharacteristic(type: tokenId, properties: [.read], value: nil, permissions: [.readable])
    ]
    peripheral.add(service)
  }

  func peripheralManagerDidUpdateState(_ peripheral: CBPeripheralManager) {
    publish(peripheral)
  }

  func peripheralManager(_ peripheral: CBPeripheralManager, didAdd service: CBService, error: Error?) {
    if error == nil && service.uuid == serviceId && Date() < deadline {
      peripheral.startAdvertising([CBAdvertisementDataServiceUUIDsKey: [serviceId]])
    }
  }

  func peripheralManager(_ peripheral: CBPeripheralManager, didReceiveRead request: CBATTRequest) {
    guard request.characteristic.uuid == tokenId, !token.isEmpty, Date() < deadline else {
      peripheral.respond(to: request, withResult: .readNotPermitted)
      return
    }
    guard request.offset <= token.count else {
      peripheral.respond(to: request, withResult: .invalidOffset)
      return
    }
    request.value = token.subdata(in: request.offset..<token.count)
    peripheral.respond(to: request, withResult: .success)
  }
}

public class ProximityAdvertiserModule: Module {
  private let advertiser = TradePeripheral()

  public func definition() -> ModuleDefinition {
    Name("ProximityAdvertiser")
    AsyncFunction("setToken") { (token: String) in self.advertiser.setToken(token) }.runOnQueue(.main)
    AsyncFunction("startAdvertising") { self.advertiser.start() }.runOnQueue(.main)
    AsyncFunction("stop") { self.advertiser.stop() }.runOnQueue(.main)
    OnDestroy { DispatchQueue.main.async { self.advertiser.stop() } }
  }
}
