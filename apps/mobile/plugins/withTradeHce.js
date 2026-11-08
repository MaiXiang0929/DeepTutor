const {withAndroidManifest, withDangerousMod} = require("@expo/config-plugins");
const {mkdir, writeFile} = require("node:fs/promises");
const path = require("node:path");
const SERVICE = "org.deeptutor.proximity.TradeNdefService";

module.exports = config => {
  config = withAndroidManifest(config, result => {
    const application = result.modResults.manifest.application[0];
    application.service ??= [];
    if (!application.service.some(service => service.$["android:name"] === SERVICE)) {
      application.service.push({
        $: {"android:name": SERVICE, "android:exported": "true", "android:permission": "android.permission.BIND_NFC_SERVICE"},
        "intent-filter": [{action: [{$: {"android:name": "android.nfc.cardemulation.action.HOST_APDU_SERVICE"}}]}],
        "meta-data": [{$: {"android:name": "android.nfc.cardemulation.host_apdu_service", "android:resource": "@xml/deeptutor_trade_apdu"}}],
      });
    }
    return result;
  });
  return withDangerousMod(config, ["android", async result => {
    const directory = path.join(result.modRequest.platformProjectRoot, "app/src/main/res/xml");
    await mkdir(directory, {recursive: true});
    await writeFile(path.join(directory, "deeptutor_trade_apdu.xml"), `<?xml version="1.0" encoding="utf-8"?>
<host-apdu-service xmlns:android="http://schemas.android.com/apk/res/android" android:description="@string/app_name" android:requireDeviceUnlock="true">
  <aid-group android:category="other" android:description="@string/app_name">
    <aid-filter android:name="D2760000850101" />
  </aid-group>
</host-apdu-service>
`);
    return result;
  }]);
};
