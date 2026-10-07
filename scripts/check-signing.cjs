/** Fail before building when resources for a signed release are missing. */
const {spawnSync} = require('node:child_process');
if (process.platform !== 'darwin') { console.error('Signed Mac builds require macOS.'); process.exit(1); }
const identities = spawnSync('security', ['find-identity', '-v', '-p', 'codesigning'], {encoding:'utf8'});
if (identities.status !== 0 || !/Developer ID Application:/.test(identities.stdout || '')) {
  console.error('No Developer ID Application identity. Configure your Apple Developer certificate in Keychain first.'); process.exit(1);
}
if (process.env.CSC_IDENTITY_AUTO_DISCOVERY === 'false') {
  console.error('Remove CSC_IDENTITY_AUTO_DISCOVERY=false for a signed build.'); process.exit(1);
}
if (!process.env.APPLE_KEYCHAIN_PROFILE && !(process.env.APPLE_ID && process.env.APPLE_APP_SPECIFIC_PASSWORD && process.env.APPLE_TEAM_ID)) {
  console.error('Configure a notarytool Keychain profile (APPLE_KEYCHAIN_PROFILE) or Apple notarization credentials securely.'); process.exit(1);
}
console.log('Signing resources present; this preflight is not proof of successful signing or notarization.');
