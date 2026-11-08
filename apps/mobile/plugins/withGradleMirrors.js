const { withDangerousMod, withProjectBuildGradle } = require("@expo/config-plugins");
const { readFile, writeFile } = require("node:fs/promises");
const path = require("node:path");

const google = "https://maven.aliyun.com/repository/google";
const publicRepo = "https://maven.aliyun.com/repository/public";
const gradle8143Sha256 = "bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531";

module.exports = config => {
  config = withProjectBuildGradle(config, result => {
    const project = result.modResults;
    if (project.language === "groovy" && !project.contents.includes(google)) {
      project.contents = project.contents.replace(
        /((?:buildscript|allprojects)\s*\{\s*repositories\s*\{)/g,
        "$1\n    maven { url '" + google + "' }\n    maven { url '" + publicRepo + "' }",
      );
    }
    return result;
  });
  return withDangerousMod(config, ["android", async result => {
    const filename = path.join(result.modRequest.platformProjectRoot, "gradle/wrapper/gradle-wrapper.properties");
    let contents = await readFile(filename, "utf8");
    contents = contents
      .replace("services.gradle.org/distributions/", "mirrors.cloud.tencent.com/gradle/")
      .replace(/^networkTimeout=10000$/m, "networkTimeout=60000");
    if (contents.includes("gradle-8.14.3-bin.zip") && !contents.includes("distributionSha256Sum=")) {
      contents = contents.replace(/^(distributionUrl=.*)$/m, "$1\ndistributionSha256Sum=" + gradle8143Sha256);
    }
    await writeFile(filename, contents, "utf8");
    return result;
  }]);
};
