const { getDefaultConfig } = require("expo/metro-config");
const path = require("node:path");

const config = getDefaultConfig(__dirname);
const sharedProtocol = path.resolve(__dirname, "../../packages/shared-protocol");
config.watchFolders = [...new Set([...config.watchFolders, sharedProtocol])];
module.exports = config;
