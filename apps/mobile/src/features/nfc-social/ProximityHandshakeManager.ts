import { PermissionsAndroid, Platform } from "react-native";
import { BleManager } from "react-native-ble-plx";
import NfcManager, { Ndef, NfcTech } from "react-native-nfc-manager";
import { requireOptionalNativeModule } from "expo-modules-core";
import { ImpactFeedbackStyle, impactAsync } from "expo-haptics";
import type { TradeSessionState } from "@deeptutor/shared-protocol";
import { post, type TutorClient } from "../../client";
import { mayInitiateBlePair, ProximityWindow } from "./proximityPolicy";

const SERVICE = "6e402810-1c65-44c7-94e7-5048e29b2210";
const TOKEN = "6e402811-1c65-44c7-94e7-5048e29b2210";
const ROOT = "/api/v1/trade";
type Native = {
  setToken(token: string): Promise<void>;
  startAdvertising(): Promise<void>;
  stop(): Promise<void>;
};
type Issued = {handshake_token: string; session_id: string; expires_in: number};
const advertiser = requireOptionalNativeModule<Native>("ProximityAdvertiser");

export class ProximityHandshakeManager {
  private ble: BleManager | null = null;
  private scanSubscription: {remove(): void} | undefined;
  private issued: Issued | null = null;
  private expires = 0;
  private poll: ReturnType<typeof setInterval> | undefined;
  private polling = false;
  private busy = false;
  private disposed = false;
  private complete = false;

  constructor(
    private readonly client: TutorClient,
    private readonly paired: (room: TradeSessionState) => void,
    private readonly status: (text: string) => void,
  ) {}

  async start() {
    if (this.disposed || this.issued) return;
    const issued = await this.client.json<Issued>(ROOT + "/token", post({}));
    if (this.disposed) return;
    this.issued = issued;
    this.expires = Date.now() + issued.expires_in * 1000;
    this.poll = setInterval(() => void this.pollRoom(), 750);
    await advertiser?.setToken(issued.handshake_token);
    this.status("已开启 NFC 分享，正在准备蓝牙");
    try {
      await this.scanBle();
    } catch {
      if (!this.disposed) this.status("蓝牙不可用，可使用 NFC 读取或分享");
    }
  }

  private async scanBle() {
    if (Platform.OS === "android") {
      const permissions = Number(Platform.Version) >= 31
        ? [PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN, PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
           PermissionsAndroid.PERMISSIONS.BLUETOOTH_ADVERTISE]
        : [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION];
      const grants = await PermissionsAndroid.requestMultiple(permissions);
      if (permissions.some(permission => grants[permission] !== PermissionsAndroid.RESULTS.GRANTED)) {
        throw new Error("Bluetooth permission denied");
      }
    }
    if (this.disposed) return;
    const manager = this.ble = new BleManager();
    await advertiser?.startAdvertising();
    if (this.disposed) return;
    const windows = new Map<string, ProximityWindow>();
    this.scanSubscription = manager.onStateChange(state => {
      if (state !== "PoweredOn" || this.disposed) return;
      this.scanSubscription?.remove();
      this.scanSubscription = undefined;
      void manager.startDeviceScan([SERVICE], {allowDuplicates: true}, (error, device) => {
        if (error) this.status("蓝牙扫描失败，可使用 NFC");
        if (this.disposed || this.complete || this.busy || !device || device.rssi == null) return;
        if (!windows.has(device.id)) {
          if (windows.size >= 64) windows.clear();
          windows.set(device.id, new ProximityWindow());
        }
        if (windows.get(device.id)?.add(device.rssi, Date.now())) void this.readBle(device.id);
      }).catch(() => this.status("蓝牙扫描失败，可使用 NFC"));
      this.status("正在等待附近设备，握手码 60 秒后失效");
    }, true);
  }

  private async readBle(deviceId: string) {
    const ble = this.ble;
    const issued = this.issued;
    if (!ble || !issued || this.busy || this.complete || this.disposed) return;
    this.busy = true;
    try {
      const connected = await ble.connectToDevice(deviceId, {timeout: 5000, requestMTU: 256});
      const device = await connected.discoverAllServicesAndCharacteristics();
      const characteristic = await device.readCharacteristicForService(SERVICE, TOKEN);
      if (!characteristic.value) return;
      const token = atob(characteristic.value);
      const encoded = token.split(".")[0].replace(/-/g, "+").replace(/_/g, "/");
      const nonce: unknown = JSON.parse(atob(encoded)).nonce;
      if (typeof nonce === "string" && mayInitiateBlePair(issued.session_id, nonce)) {
        await this.pair(token);
      }
    } catch {
      if (!this.disposed) this.status("蓝牙握手未完成，可重试或改用 NFC");
    } finally {
      await ble.cancelDeviceConnection(deviceId).catch(() => {});
      this.busy = false;
    }
  }

  async readNfc() {
    if (this.busy || this.disposed || this.complete) return;
    this.busy = true;
    try {
      await NfcManager.start();
      await NfcManager.requestTechnology(NfcTech.Ndef, {alertMessage: "将手机靠近同学的手机或临时交换卡贴"});
      const tag = await NfcManager.getTag();
      const record = tag?.ndefMessage?.[0];
      if (!record || !Ndef.isType(record, Ndef.TNF_WELL_KNOWN, Ndef.RTD_TEXT)) throw new Error("没有可读取的交换码");
      await this.pair(Ndef.text.decodePayload(Uint8Array.from(record.payload)));
    } finally {
      this.busy = false;
      await NfcManager.cancelTechnologyRequest().catch(() => {});
    }
  }

  async writeTag() {
    if (!this.issued || Date.now() >= this.expires || this.busy || this.disposed) throw new Error("请先获取有效握手码");
    this.busy = true;
    try {
      await NfcManager.start();
      await NfcManager.requestTechnology(NfcTech.Ndef, {alertMessage: "贴近可写入的 NFC 卡贴"});
      const bytes = Ndef.encodeMessage([Ndef.textRecord(this.issued.handshake_token)]);
      if (!bytes) throw new Error("无法编码临时交换码");
      await NfcManager.ndefHandler.writeNdefMessage(bytes);
      this.status("已写入一次性交换码");
    } finally {
      this.busy = false;
      await NfcManager.cancelTechnologyRequest().catch(() => {});
    }
  }

  private async pair(token: string) {
    if (this.disposed || this.complete || Date.now() >= this.expires) return;
    if (!/^[a-zA-Z0-9_=-]+\.[a-f0-9]{64}$/.test(token) || token.length > 2048) throw new Error("无效的交换码");
    const result = await this.client.json<TradeSessionState>(ROOT + "/pair", post({handshake_token: token}));
    await this.finish(result);
  }

  private async pollRoom() {
    if (!this.issued || this.disposed || this.complete || this.polling) return;
    if (Date.now() >= this.expires) {
      this.status("握手码已过期，请重新开始");
      await this.stop();
      return;
    }
    this.polling = true;
    try {
      const room = await this.client.json<TradeSessionState>(`${ROOT}/${this.issued.session_id}`);
      await this.finish(room);
    } catch {
      // The room does not exist until the peer pairs with this code.
    } finally {
      this.polling = false;
    }
  }

  private async finish(room: TradeSessionState) {
    if (this.disposed || this.complete) return;
    this.complete = true;
    await this.stop();
    void impactAsync(ImpactFeedbackStyle.Heavy).catch(() => {});
    this.paired(room);
  }

  async stop() {
    this.disposed = true;
    clearInterval(this.poll);
    this.scanSubscription?.remove();
    this.scanSubscription = undefined;
    const manager = this.ble;
    this.ble = null;
    await Promise.allSettled([
      advertiser?.stop(),
      manager?.destroy(),
      NfcManager.cancelTechnologyRequest(),
    ]);
  }
}
