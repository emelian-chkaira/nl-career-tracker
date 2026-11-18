# Firebase Authentication setup

With `CAREERS_FIREBASE_API_KEY` set, Firebase is the identity provider: sign-up, sign-in, password reset, e-mail verification and
**Continue with Google** all go through it. The API keeps profiles and issues its own sessions, so web and mobile need no Firebase SDK.
Existing accounts move to Firebase automatically the next time they sign in with their password.

## 1. Create the project (free Spark plan)
1. https://console.firebase.google.com -> **Add project** (Google Analytics is optional; skip it).
2. **Build -> Authentication -> Get started -> Sign-in method**:
   - enable **Email/Password** (leave "Email link" off);
   - enable **Google**, choose a support email, save.
3. Still on the Google provider, expand **Web SDK configuration** and copy the **Web client ID** (`123-abc.apps.googleusercontent.com`).
4. **Project settings (gear) -> General -> Web API key**: copy it.

## 2. Server settings (`.env`)
```
CAREERS_FIREBASE_API_KEY=<Web API key>
CAREERS_GOOGLE_CLIENT_ID=<Web client ID>[,<iOS client ID>][,<Android client ID>]
```
Restart the API. `GET /api/v1/auth/config` now answers `"provider":"firebase"` and the **Continue with Google** button appears on the web
app and in the mobile app.

## 3. Authorized domains
**Authentication -> Settings -> Authorized domains**: `localhost` is there by default; add your deployed domain (e.g. `careers.duckdns.org`).
In Google Cloud Console (same project) -> **APIs & Services -> Credentials -> Web client**: add the domain as an *Authorized JavaScript origin*
(`https://careers.duckdns.org`, plus `http://localhost:8787` for local testing).

## 4. E-mail templates
**Authentication -> Templates**: for *Email address verification* and *Password reset* set the sender name to "CareerNL" and
**customize action URL** to `https://<your-domain>/action`. The web app handles both links there. Until you deploy, leave the default
(Firebase's own hosted page works too).

## 5. Mobile Google button
The button uses the native Google account picker and asks for an ID token for the server's web client, so the server verifies it.
- **iOS**: Google Cloud Console -> Credentials -> *Create OAuth client ID* -> **iOS**, bundle ID `nl.careertracker.careerTracker`.
  Add its client ID to `CAREERS_GOOGLE_CLIENT_ID`. In `ios/Runner/Info.plist` add the **reversed** client ID as a URL scheme:
  ```xml
  <key>CFBundleURLTypes</key><array><dict><key>CFBundleURLSchemes</key><array><string>com.googleusercontent.apps.123-abc</string></array></dict></array>
  ```
  Build with `--dart-define=GOOGLE_IOS_CLIENT_ID=<iOS client ID>`.
- **Android**: *Create OAuth client ID* -> **Android**, package `nl.careertracker.career_tracker`, SHA-1 of your signing key
  (`cd android && ./gradlew signingReport`). Add its client ID to `CAREERS_GOOGLE_CLIENT_ID`. Use the release key's SHA-1 for Play Store builds too.
- Build against the deployed server: `flutter build ... --dart-define=API_URL=https://<your-domain>`.

## 6. Check it
- Register with e-mail/password: a verification mail arrives from Firebase; the banner on the web app / Me tab disappears after confirming.
- "Forgot password?" sends the reset mail; resetting signs the account out everywhere.
- Strict mode: `CAREERS_REQUIRE_VERIFIED_EMAIL=1` refuses sign-in until the address is confirmed.

## Limits worth knowing
- The free plan covers e-mail/password and Google sign-in; phone/SMS sign-in is not free. Check Firebase's pricing page for current numbers.
- Firebase sends the auth mails only. **Job-alert mails** still need `CAREERS_SMTP_*` (any relay).
