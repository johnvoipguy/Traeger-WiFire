# Troubleshooting Guide

## Authentication Issues (400 Bad Request)

### Symptom
You're seeing errors like:
- `Cognito request failed: Connection closed`
- `Client error fetching data: 400, message='Bad Request'`
- Integration fails to load and devices are unavailable

### Root Cause
Traeger may have changed their AWS Cognito CLIENT_ID, which is used for authentication. The integration uses a hardcoded CLIENT_ID that may no longer be valid.

### Diagnosis
Check your Home Assistant logs for messages like:
```
Cognito authentication failed with 400 Bad Request. 
This may indicate that Traeger has changed their CLIENT_ID.
Current CLIENT_ID: 2fuohjtqv1e63dckp5v84rau0j
```

### Solution

#### Option 1: Check for Updates
1. Check the [GitHub issues](https://github.com/johnvoipguy/Traeger-WiFire/issues) page for updates
2. Look for an issue discussing CLIENT_ID changes
3. If a new CLIENT_ID has been discovered, use Option 2 below

#### Option 2: Use Custom CLIENT_ID
If you have access to the correct CLIENT_ID (e.g., extracted from the Traeger mobile app):

1. Go to **Settings** → **Devices & Services** in Home Assistant
2. Click **+ ADD INTEGRATION**
3. Search for and select **Traeger WiFIRE**
4. Enter your credentials:
   - **Email**: Your Traeger account email
   - **Password**: Your Traeger account password
   - **AWS Cognito Client ID**: Enter the new CLIENT_ID here (or leave blank to use default)
5. Click **Submit**

#### Option 3: Extract CLIENT_ID from Mobile App (Advanced)
This requires technical knowledge and tools:

1. **Android Method** (with rooted device or SSL proxy):
   - Install an SSL inspection tool like Charles Proxy or mitmproxy
   - Configure your device to use the proxy
   - Install the proxy's SSL certificate on your device
   - Open the Traeger app and log in
   - Look for HTTPS requests to `cognito-idp.us-west-2.amazonaws.com`
   - Inspect the request body for the `ClientId` field

2. **iOS Method** (requires jailbroken device or similar setup):
   - Similar to Android, use an SSL proxy
   - Capture authentication requests to AWS Cognito
   - Extract the `ClientId` from the request payload

3. **Alternative**: Decompile the APK/IPA:
   - Download the Traeger app APK (Android) or IPA (iOS)
   - Use tools like `apktool` or similar to decompile
   - Search for strings containing "ClientId" or similar AWS Cognito configuration

### Prevention
- Keep the integration updated through HACS
- Monitor the [GitHub repository](https://github.com/johnvoipguy/Traeger-WiFire) for announcements
- Consider subscribing to issue notifications

### Still Having Issues?
If you're still experiencing problems:
1. Enable debug logging for the integration
2. Check the full error logs in Home Assistant
3. [Open a new issue](https://github.com/johnvoipguy/Traeger-WiFire/issues/new) with:
   - Your error logs
   - Home Assistant version
   - Integration version
   - Steps you've already tried

## Other Common Issues

### Grill Not Responding
- Ensure your grill is powered on and connected to WiFi
- Check that your grill firmware is up to date via the Traeger app
- Verify your Home Assistant instance can reach the internet

### Entities Not Updating
- Check if the grill is sleeping (power switch on, screen off)
- Some entities only update when the grill is actively cooking
- Try refreshing the integration or restarting Home Assistant

### Integration Won't Load
- Check Home Assistant logs for specific errors
- Ensure your username and password are correct
- Try removing and re-adding the integration
