# WhatsApp Business API Setup Guide

Complete step-by-step guide to set up WhatsApp Business Account and integrate with your newsletter app.

---

## Prerequisites

### What You Need

1. **Facebook Account** - For Meta Developer access
2. **Phone Number** - For WhatsApp Business registration
   - ⚠️ **IMPORTANT**: This number will be converted to WhatsApp Business
   - Cannot be used for regular WhatsApp on the same device afterward
   - **Recommended options**:
     - Google Voice number (free, US only)
     - Twilio number (~$1/month)
     - Old SIM card you don't use
     - Secondary phone number

3. **Business Information** (Optional but helpful)
   - Business name (can be personal: "John's Newsletter")
   - Business address (can use home address)
   - Business website (optional)

---

## Part 1: Create Meta Developer Account

### Step 1.1: Sign Up for Meta for Developers

1. Go to https://developers.facebook.com/
2. Click **"Get Started"** in top right
3. Log in with your Facebook account
4. Accept Terms of Service
5. Complete account verification (may require phone verification)

**Result**: You now have a Meta Developer account

---

## Part 2: Create Meta Business App

### Step 2.1: Create New App

1. Go to https://developers.facebook.com/apps
2. Click **"Create App"** button
3. Select **"Business"** as use case
   - Not "Consumer" or "Gaming"
4. Click **"Next"**

### Step 2.2: Configure App Details

Fill in the form:

| Field | Value |
|-------|-------|
| **App Name** | `My Daily Newsletter` (or your choice) |
| **App Contact Email** | Your email address |
| **Business Account** | Create new or select existing |

5. Click **"Create App"**
6. Complete security check (if prompted)

**Result**: You have a Meta Business App

---

## Part 3: Add WhatsApp Product

### Step 3.1: Add WhatsApp to Your App

1. In your app dashboard, scroll to **"Add products to your app"**
2. Find **"WhatsApp"** card
3. Click **"Set up"** button

### Step 3.2: Navigate to WhatsApp Settings

1. In left sidebar, click **"WhatsApp" → "API Setup"**
2. You'll see the "API Setup" screen with:
   - Phone number selection
   - Test number (provided by Meta)
   - Send message test interface

---

## Part 4: Register Your Phone Number

### Step 4.1: Add Your Phone Number

On the API Setup page:

1. Find **"Phone Numbers"** section
2. Click **"Add phone number"**
3. Select **"Register phone number you own"**

### Step 4.2: Enter Phone Number

1. Select country code (e.g., `+1` for US)
2. Enter phone number **without country code**
   - Example: If number is `+1-555-123-4567`, enter `5551234567`
3. Click **"Next"**

### Step 4.3: Choose Verification Method

Two options:

**Option A: SMS Verification** (Recommended)
- Select "Text message (SMS)"
- Click "Next"
- You'll receive a 6-digit code via SMS
- Enter the code
- Click "Verify"

**Option B: Voice Call Verification**
- Select "Phone call"
- You'll receive an automated call with the code
- Enter the code
- Click "Verify"

### Step 4.4: Set Display Name

1. Enter **Display Name**: This appears to recipients
   - Example: "Daily AI News", "John's Newsletter"
2. Select **Category**: Choose "Other" or "News"
3. Enter **Description**: Brief description of your newsletter
4. Click **"Next"**

### Step 4.5: Business Profile (Optional)

Fill in business details:
- Business address (can skip for personal use)
- Website (optional)
- Business hours (optional)

Click **"Submit"**

**Result**: Your phone number is now registered! You'll see:
- Phone Number ID (needed for .env)
- Phone number status: "Connected"

---

## Part 5: Get API Credentials

### Step 5.1: Get Phone Number ID

1. In **"API Setup"** page, find **"Phone number ID"**
2. Copy the number (looks like: `123456789012345`)
3. Save this for later: `WHATSAPP_PHONE_NUMBER_ID=123456789012345`

### Step 5.2: Get Temporary Access Token

On the same page:

1. Find **"Access Token"** section
2. Click **"Generate Token"** (or copy existing token)
3. Copy the token (starts with `EAA...`)
4. ⚠️ **This is temporary (24 hours)** - We'll create permanent token in Step 5.3

### Step 5.3: Create Permanent System User Token (IMPORTANT)

Temporary tokens expire in 24 hours. For production, create a permanent token:

#### 5.3.1: Navigate to Business Settings

1. Click your app name (top left)
2. Click **"Business Settings"** in dropdown
3. Or go directly to: https://business.facebook.com/settings

#### 5.3.2: Create System User

1. In left sidebar, click **"System users"**
2. Click **"Add"** button
3. Enter name: `newsletter-system-user`
4. Select role: **"Admin"**
5. Click **"Create system user"**

#### 5.3.3: Generate Permanent Token

1. Click on the system user you just created
2. Click **"Generate new token"** button
3. Select your app from dropdown
4. Select permissions:
   - ✅ `whatsapp_business_messaging`
   - ✅ `whatsapp_business_management`
5. Click **"Generate token"**
6. Copy the token (starts with `EAA...`)
7. ⚠️ **SAVE THIS TOKEN IMMEDIATELY** - It won't be shown again!

**Save for .env:**
```bash
WHATSAPP_ACCESS_TOKEN=EAAxxxxx...
```

### Step 5.4: Get App Secret

1. Go back to your app dashboard
2. In left sidebar, click **"Settings" → "Basic"**
3. Find **"App Secret"** field
4. Click **"Show"** button
5. Enter your Facebook password
6. Copy the app secret

**Save for .env:**
```bash
WHATSAPP_APP_SECRET=abc123def456...
```

---

## Part 6: Configure Webhooks

### Step 6.1: Create Verify Token

Before configuring webhook in Meta, decide on a verify token:

1. Generate a random string (20+ characters)
2. Example: `my_secure_verify_token_12345`
3. Or use this command:
   ```bash
   openssl rand -base64 32
   ```

**Save for .env:**
```bash
WHATSAPP_VERIFY_TOKEN=<your_random_string>
```

### Step 6.2: Get Your Public URL

Your webhook must be publicly accessible with HTTPS.

**Option A: Production (Oracle Cloud)**
- Example: `https://your-domain.com`
- Or: `https://<ORACLE_IP>.nip.io` (temporary)

**Option B: Development (Ngrok)**
```bash
# Install ngrok: https://ngrok.com/download
ngrok http 8000

# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
```

Your webhook URL will be:
```
https://your-domain.com/webhooks/whatsapp
```

### Step 6.3: Start Your Application

Make sure your app is running and accessible:

```bash
# On your server or local machine
cd /path/to/my-daily-newsletter/my-daily-newsletter
source .venv/bin/activate
uvicorn newsletter.app:app --host 0.0.0.0 --port 8000
```

Test that webhook is accessible:
```bash
# From another terminal
curl "https://your-domain.com/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=YOUR_VERIFY_TOKEN&hub.challenge=test123"

# Should return: test123
```

### Step 6.4: Configure Webhook in Meta Console

1. In your app dashboard, go to **"WhatsApp" → "Configuration"**
2. Find **"Webhook"** section
3. Click **"Edit"** button

#### Configure Callback URL

| Field | Value |
|-------|-------|
| **Callback URL** | `https://your-domain.com/webhooks/whatsapp` |
| **Verify Token** | (Same as `WHATSAPP_VERIFY_TOKEN` in .env) |

4. Click **"Verify and Save"**

**What Happens:**
- Meta sends a GET request to your webhook
- Your app verifies the token and returns the challenge
- If successful, webhook is connected ✅

**If Verification Fails:**
- Check app is running: `curl http://localhost:8000/health`
- Check logs: `journalctl -u newsletter -f`
- Verify WHATSAPP_VERIFY_TOKEN matches in both places
- Check firewall allows HTTPS (port 443)

### Step 6.5: Subscribe to Webhook Fields

After verification succeeds:

1. Still in **"Configuration"** page
2. Find **"Webhook fields"** section
3. Click **"Manage"** button
4. Subscribe to these fields:
   - ✅ **messages** - Incoming text messages
   - ✅ **message_reactions** - When user reacts to messages
5. Click **"Done"**

**Result**: Your webhook is now configured! 🎉

---

## Part 7: Add Recipient (Test Mode)

By default, WhatsApp Business API is in "test mode" - it can only send to specific numbers.

### Step 7.1: Add Your Personal Number

1. In **"API Setup"** page, find **"To"** field
2. Enter YOUR WhatsApp number (the one you'll receive messages on)
   - Include country code: `+1 555 123 4567`
3. Click **"Send message"** button
4. You should receive a test message on your WhatsApp

**Result**: Your personal number is now a test recipient

### Step 7.2: Add to .env

Save your personal WhatsApp number in .env:
```bash
USER_WHATSAPP_E164=+15551234567  # Format: +<country><number>, no spaces
```

---

## Part 8: Test the Integration

### Step 8.1: Send a Test Message

From your personal WhatsApp, send a message to the Business number:

```
Tomorrow I want news about GPT-5
```

**Expected Response (within 5 seconds):**
```
Got it — I'll fold that into the next digest generation. (stored as tomorrow_override)
```

### Step 8.2: Trigger a Manual Digest

```bash
curl -X POST https://your-domain.com/internal/run-digest \
  -H "X-Trigger-Secret: YOUR_TRIGGER_SECRET"
```

**Expected Result:**
1. Intro message on WhatsApp (2-3 paragraphs)
2. Multiple link messages (one per article)

### Step 8.3: Test Reaction Saving

1. React 👍 to one of the link messages
2. **Expected Response:**
   ```
   Saved for later: <article title>
   ```

3. Send message: `list saved`
4. **Expected Response:** Markdown list of saved links

---

## Part 9: Complete .env Configuration

After completing all steps, your `.env` should look like:

```bash
# --- App ---
ENV=production
PUBLIC_BASE_URL=https://your-domain.com
PORT=8000

# --- WhatsApp Cloud API ---
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_ACCESS_TOKEN=EAAxxxxx...  # System user token (permanent)
WHATSAPP_APP_SECRET=abc123def456...
WHATSAPP_VERIFY_TOKEN=my_secure_verify_token_12345

# --- Your Personal WhatsApp ---
USER_WHATSAPP_E164=+15551234567  # Your number (no spaces)

# --- LLM (OpenAI or compatible) ---
OPENAI_API_KEY=sk-proj-xxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5.4-mini

# --- Schedule ---
DIGEST_LOCAL_HOUR=8
DIGEST_LOCAL_MINUTE=30
DIGEST_TIMEZONE=America/Los_Angeles

# --- Database ---
DATABASE_URL=sqlite:////home/ubuntu/newsletter.sqlite3

# --- Security ---
TRIGGER_SECRET=random_secret_for_manual_triggers
```

---

## Part 10: Go to Production (Optional)

If you want to send to any WhatsApp number (not just test recipients):

### Step 10.1: Submit App for Review

1. Go to **"App Review" → "Requests"**
2. Click **"Submit for review"**
3. Select **"WhatsApp Business Messaging"**
4. Submit required information:
   - App description
   - Use case (personal newsletter)
   - Privacy policy URL (can use a simple Google Doc)
   - Terms of service URL (optional)

### Step 10.2: Review Process

- **Timeline**: 1-2 weeks
- **Requirements**:
  - Working webhook
  - Valid business use case
  - Privacy policy
- **Approval**: You'll receive email notification

### Step 10.3: After Approval

Once approved:
- Can send to any WhatsApp number
- Higher rate limits (1000 → unlimited conversations)
- Official "Verified" badge (optional)

**For Personal Use**: Test mode is sufficient! No need to go through review.

---

## Troubleshooting

### Webhook Verification Fails

**Problem**: "Webhook verification failed" error

**Solutions**:
1. Check app is running:
   ```bash
   curl http://localhost:8000/health
   # Should return: {"status":"ok"}
   ```

2. Check webhook responds correctly:
   ```bash
   curl "https://your-domain.com/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=test"
   # Should return: test
   ```

3. Check logs:
   ```bash
   journalctl -u newsletter -f
   ```

4. Verify WHATSAPP_VERIFY_TOKEN matches in:
   - .env file
   - Meta console webhook settings

5. Check HTTPS works:
   ```bash
   curl -I https://your-domain.com
   # Should return: HTTP/2 200
   ```

### Not Receiving Messages

**Problem**: Send message from WhatsApp, no response

**Solutions**:
1. Check webhook is subscribed to `messages` field:
   - Go to **"Configuration"** → **"Webhook fields"**
   - Ensure ✅ **messages** is checked

2. Check logs for incoming webhooks:
   ```bash
   journalctl -u newsletter -f
   # Look for: "POST /webhooks/whatsapp"
   ```

3. Verify signature validation isn't failing:
   - Check WHATSAPP_APP_SECRET is correct
   - Look for "Bad signature" in logs

4. Check USER_WHATSAPP_E164 matches your number:
   ```bash
   # In Python
   from newsletter.config import get_settings
   print(get_settings().user_whatsapp_e164)
   # Should match your WhatsApp number in E.164 format
   ```

### Cannot Send Messages

**Problem**: App tries to send, but fails

**Solutions**:
1. Check access token is valid:
   ```bash
   curl -X POST "https://graph.facebook.com/v21.0/me?access_token=YOUR_TOKEN"
   # Should return app info, not error
   ```

2. Check phone number ID is correct:
   ```bash
   curl "https://graph.facebook.com/v21.0/YOUR_PHONE_ID?access_token=YOUR_TOKEN"
   # Should return phone number info
   ```

3. Check recipient is added in test mode:
   - Go to **"API Setup"**
   - Verify your number is in test recipients list

4. Check rate limits:
   - Free tier: 1000 conversations/month
   - 1 conversation = 24-hour window with a user
   - If exceeded, wait or upgrade

### Reactions Not Saving

**Problem**: React to link, no "Saved for later" message

**Solutions**:
1. Check webhook subscribed to `message_reactions`:
   - **"Configuration"** → **"Webhook fields"** → ✅ **message_reactions**

2. Check OutgoingMessage table has entries:
   ```bash
   sqlite3 newsletter.sqlite3 "SELECT * FROM outgoing_messages ORDER BY created_at DESC LIMIT 5;"
   ```

3. Check logs for reaction events:
   ```bash
   journalctl -u newsletter -f
   # Look for: "Reaction: <emoji>"
   ```

---

## Cost & Limits

### Free Tier (Test Mode)

| Resource | Limit |
|----------|-------|
| **Conversations** | 1,000/month |
| **Conversations (Service)** | Unlimited |
| **Recipients** | Test numbers only |
| **Rate Limit** | 80 messages/second |
| **Message Length** | 4096 characters |

**Conversation Definition**: 24-hour window starting from first message

**Example**:
- Day 1, 8:30 AM: Bot sends digest → Start conversation #1
- Day 1, 10:00 AM: You reply → Still conversation #1
- Day 2, 8:30 AM: Bot sends digest → Start conversation #2 (24h passed)

### Paid Tier (Production)

After app review:
- **Conversations**: Unlimited
- **Cost**: ~$0.005-0.05 per conversation (varies by country)
- **Your use case**: ~30 conversations/month = **$0.15-1.50/month**

---

## Security Best Practices

### 1. Protect Your Tokens

```bash
# NEVER commit .env to git
echo ".env" >> .gitignore

# Set restrictive permissions
chmod 600 .env
```

### 2. Rotate Tokens Periodically

Every 6 months:
1. Generate new system user token
2. Update .env
3. Restart app

### 3. Use Trigger Secret

Always set TRIGGER_SECRET in production:
```bash
TRIGGER_SECRET=$(openssl rand -base64 32)
```

### 4. Monitor Webhook Activity

```bash
# Check for suspicious activity
journalctl -u newsletter | grep "Bad signature"
journalctl -u newsletter | grep "non-owner"
```

---

## Next Steps

After WhatsApp setup is complete:

1. ✅ **Test manually**:
   - Send preference message
   - Trigger digest
   - React to save links

2. ✅ **Set up daily schedule**:
   - Verify timezone in .env
   - Wait for scheduled digest (8:30 AM)
   - Or test with manual trigger

3. ✅ **Configure Oracle Cloud** (see DEPLOYMENT.md):
   - Deploy app to VM
   - Setup Nginx + SSL
   - Configure systemd service

4. ✅ **Monitor & iterate**:
   - Check logs daily
   - Refine preferences
   - Adjust digest format

---

## Quick Reference

### Useful Links

| Resource | URL |
|----------|-----|
| **Meta Developer Dashboard** | https://developers.facebook.com/apps |
| **Business Settings** | https://business.facebook.com/settings |
| **WhatsApp API Docs** | https://developers.facebook.com/docs/whatsapp/cloud-api |
| **Graph API Explorer** | https://developers.facebook.com/tools/explorer |
| **Webhook Tester** | https://webhook.site |

### Common Commands

```bash
# Test webhook verification
curl "https://your-domain.com/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=test"

# Trigger manual digest
curl -X POST https://your-domain.com/internal/run-digest -H "X-Trigger-Secret: YOUR_SECRET"

# Check app status
curl http://localhost:8000/health

# View logs
journalctl -u newsletter -f

# Restart service
sudo systemctl restart newsletter
```

---

## Conclusion

You now have a fully configured WhatsApp Business Account integrated with your newsletter app! 🎉

The app can:
- ✅ Receive your preference messages
- ✅ Send daily digests at 8:30 AM
- ✅ Save links via reactions
- ✅ Recall saved items on demand

**Total Setup Time**: ~45 minutes
**Monthly Cost**: $0 (test mode) or ~$0.15-1.50 (production)
