# GhostCanvas 3D - Stripe & Lemon Squeezy Automated Fulfillment Spec

## Overview
When a customer purchases a GhostCanvas 3D license on the website, the payment provider dispatches an HTTPS webhook to the license issuance API.

### Webhook Event Flow
1. **Event:** `order_created` / `payment_intent.succeeded`
2. **Payload:** Customer Email, Tier (`indie` / `studio_pro`), Seat Count.
3. **Generation:**
   ```python
   key = LicenseManager.generate_license_key(
       customer_id=customer_email,
       tier=tier,
       duration_days=365,
       max_vms=seats,
   )
   ```
4. **Fulfillment Email:** Sends customer their license key (`GC3D-XXXX-YYYY...`), download link for `GhostCanvas3D-Setup-v1.1.0.exe`, and MCP quickstart guide.

### Activation Endpoints
- `POST https://api.ghostcanvas3d.com/v1/license/activate`
  - Input: `{"license_key": "GC3D-...", "hwid": "BD688079E4D61D69"}`
  - Output: `{"status": "active", "tier": "indie", "expires_at": 1819124278}`
