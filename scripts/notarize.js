/**
 * macOS Notarization script for electron-builder afterSign hook.
 *
 * Prerequisites:
 *   - APPLE_ID          : your Apple ID email
 *   - APPLE_APP_SPECIFIC_PASSWORD : app-specific password from appleid.apple.com
 *   - APPLE_TEAM_ID     : 10-character Team ID from developer.apple.com
 *
 * config/electron-builder.yml references this via:
 *   afterSign: scripts/notarize.js
 */

'use strict'

const path = require('path')

module.exports = async function notarizeApp(context) {
  const { electronPlatformName, appOutDir } = context

  // Only notarize on macOS
  if (electronPlatformName !== 'darwin') return

  const appleId = process.env.APPLE_ID
  const appleIdPassword = process.env.APPLE_APP_SPECIFIC_PASSWORD
  const teamId = process.env.APPLE_TEAM_ID
  const keychainProfile = process.env.APPLE_KEYCHAIN_PROFILE

  if (!keychainProfile && (!appleId || !appleIdPassword || !teamId)) {
    console.warn(
      '[notarize] Skipping notarization — set APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, ' +
      'and APPLE_TEAM_ID to enable.\n' +
      '[notarize] Without notarization, macOS Gatekeeper will block the app for users ' +
      'who downloaded it from the internet. Keep system security protections enabled.'
    )
    return
  }

  const { notarize } = require('@electron/notarize')
  const appName = context.packager.appInfo.productFilename
  const appPath = path.join(appOutDir, `${appName}.app`)

  console.log(`[notarize] Submitting ${appPath} for notarization...`)

  await notarize({
    tool: 'notarytool',
    appPath,
    ...(keychainProfile ? { keychainProfile } : { appleId, appleIdPassword, teamId }),
  })

  console.log('[notarize] Notarization complete.')
}
