# DeepTutor Companion

The app uses the same running DeepTutor backend and account as the desktop or Web learning workspace. Enter the reachable HTTPS origin on the connection screen. Enable backend authentication and create two separate accounts to test trading. Configure speech recognition and synthesis in the server's Voice settings.

The app includes Partner greetings based on recent study, voice chat, Skia minigames, an inventory and synthesis screen, proximity trading, and guardian limits and reports. `modules/proximity-advertiser` provides Android HCE and Android/iOS BLE advertising. The `plugins` directory applies the native NFC configuration and Gradle mirrors at prebuild time.

## Development build

```powershell
npm ci
npx tsc --noEmit
npm test
npx expo run:android
npm start
```

Use an Android phone that supports NFC host card emulation or an iPhone with Core NFC. Expo Go does not include the native Rive, NFC, Skia and GATT modules used here.

For a cloud build, use an Expo account and run `npx eas-cli build:configure` in this directory. Run `npx eas-cli build --profile development --platform android` for an internal APK, or `npx eas-cli build --profile development --platform ios` for a registered iPhone. The iOS signing profile must permit Core NFC Tag Reading. Use the preview profile for an internal build with bundled JavaScript.

## Local Android APKs on Windows

Install JDK 17 and the Android SDK, including the packages selected by the generated Gradle project. Set `JAVA_HOME` and `ANDROID_HOME`, then run from `apps/mobile`.

```powershell
npm ci
npx expo prebuild --platform android
Push-Location android
try {
    .\gradlew.bat :app:assembleDebug :app:assembleRelease '-PreactNativeArchitectures=arm64-v8a,x86_64'
    if ($LASTEXITCODE -ne 0) { throw 'Android build failed' }
} finally {
    Pop-Location
}
```

- `android/app/build/outputs/apk/debug/app-debug.apk` loads JS from Metro and supports a local HTTP backend.
- `android/app/build/outputs/apk/release/app-release.apk` embeds the JS bundle and opens directly. It is signed with the Debug key for device testing. Use an HTTPS backend origin for the Release build.

Expo prebuild applies the Tencent Cloud Gradle mirror, Aliyun Maven mirrors, HCE service and NFC/BLE permissions. The generated `android/` and `ios/` folders are disposable. Keep native changes in the config plugins or local Expo module.

## Local preview on Windows

From the repository root, start the backend and Web UI together, then leave Metro running for the Debug development client.

```powershell
Set-Location 'D:\Desktop\Venus\DeepTutor'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\deeptutor.exe start --dev --detach
if ($LASTEXITCODE -ne 0) { throw 'DeepTutor startup failed' }
Set-Location .\apps\mobile
npm start -- --lan
```

Open the installed Debug development client and scan the Metro QR code or enter `http://<computer-LAN-IP>:8081` in the Expo launcher. For an already-running Android emulator with the app installed, use `npm start -- --android` instead. In the DeepTutor connection screen, enter the backend origin on its own port. From a phone on the same Wi-Fi, use `http://<computer-LAN-IP>:<backend-port>`. From the standard Android emulator, use `http://10.0.2.2:<backend-port>`. Leave the username and password blank when backend authentication is disabled.

Press Ctrl+C to stop Metro. From the repository root, stop the detached Web and backend services with `.\.venv\Scripts\deeptutor.exe stop`.

Guardian controls have no default PIN. Enable account authentication, sign in as an authorized guardian, select the learner, and choose a six-digit PIN the first time you save their game and trade limits.

## Rive asset

Set `EXPO_PUBLIC_COMPANION_RIVE_URL` to an HTTPS URL for a `.riv` file. Its default artboard needs a default data-binding view model with a number property `emotion_state` (0 idle, 1 happy, 2 proud, 3 empathetic, 4 thinking, 5 excited), Boolean `is_speaking`, and triggers `on_head_pat` and `on_poke`. Without a compatible asset the app shows the emotion glyph. Native rendering and speech still need a device run.

## Two-device acceptance

1. Sign in on both phones against one backend. Use distinct accounts with one unequipped item each. Open proximity trading on both phones in the foreground.
2. On two iPhones, bring the phones close and wait for the BLE room. BLE discovery advertises a service UUID and reads the signed token through GATT. Signal strength depends on the phone and environment.
3. For NFC, leave the sender on the sharing screen and press **读取 NFC 交换码** on the reader. The sender must be Android with HCE support. On compatible writable tags, **将临时交换码写入卡贴** writes the same one-time 60-second code.
4. Submit offers, lock both sides and confirm both sides. Change a locked offer and verify both confirmations clear. Recheck both inventories after a completed exchange.
5. Start the shared quiz on both phones. Both see one question and one deadline. Submit each answer and confirm scores appear after both players answer or the deadline passes.
6. Sign in as an authorized guardian. Set the learner's PIN and limits, then verify that a learner at the limit cannot start another game or trade. Verify the seven-day report contains only daily aggregates.

The Python trade tests exercise both WebSocket participants and the mobile tests exercise RSSI filtering and single-initiator selection. They cannot validate radio behavior on real devices.
