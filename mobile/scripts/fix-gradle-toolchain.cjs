const fs = require('node:fs');
const path = require('node:path');

// RN 0.83's Foojay 0.5 resolver uses a field removed in Expo 55's Gradle 9.
// Upstream: https://github.com/react/react-native/issues/55781
const file = path.join(
  path.dirname(require.resolve('@react-native/gradle-plugin/package.json')),
  'settings.gradle.kts',
);
const old = 'id("org.gradle.toolchains.foojay-resolver-convention").version("0.5.0")';
const fixed = 'id("org.gradle.toolchains.foojay-resolver-convention").version("1.0.0")';
const source = fs.readFileSync(file, 'utf8');
if (source.includes(old)) {
  fs.writeFileSync(file, source.replace(old, fixed));
  console.log('Applied React Native / Gradle 9 toolchain compatibility fix.');
} else if (!source.includes(fixed)) {
  throw new Error('Unexpected React Native toolchain configuration; review the compatibility fix.');
}

// WebView 13 still declares AGP 7.0.4 in its library buildscript. Expo supplies
// AGP/Kotlin at the root; use those versions rather than resolving a second old
// Android toolchain and its obsolete transitive dependencies.
const webview = path.join(path.dirname(require.resolve('react-native-webview/package.json')), 'android', 'build.gradle');
let webviewSource = fs.readFileSync(webview, 'utf8');
webviewSource = webviewSource.replace(/^\s*classpath\("com\.android\.tools\.build:gradle:7\.0\.4"\)\s*$/m, '\n        // Android Gradle plugin is supplied by the Expo root project.');
webviewSource = webviewSource.replace(/^\s*classpath\("org\.jetbrains\.kotlin:kotlin-gradle-plugin:\$\{safeExtGet\('kotlinVersion'\)\}"\)\s*$/m, '\n        // Kotlin Gradle plugin is supplied by the Expo root project.');
fs.writeFileSync(webview, webviewSource);
