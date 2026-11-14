# Optional WhatsApp Cloud API connection

Implemented adapter: platform/backend/whatsapp.py. Disabled by default. No subscription, template, key or billing change has been created. Manual sharing remains available.

Configure only in Render Environment after the existing Business account and approved template are available:
- BIGBEN_WHATSAPP_ENABLED=1 (leave unset/0 until setup and messaging costs are explicitly accepted)
- WHATSAPP_ACCESS_TOKEN (secret)
- WHATSAPP_PHONE_NUMBER_ID (sender ID, not recipient phone)
- WHATSAPP_API_VERSION (explicit supported version, such as the version currently shown by Meta; no implicit latest endpoint)
- WHATSAPP_TEMPLATE_NAME (existing approved template name)
- WHATSAPP_TEMPLATE_LANGUAGE (approved language code, e.g. ar)

The recipient number is stored privately in dashboard settings, in E.164 format with +. It is not an API credential.

## Required template contract
The approved template must contain nine positional BODY text parameters, in exactly this order:
1. Market name and qualified symbol
2. BUY or SELL
3. Shared entry
4. Shared stop
5. Full original target
6. Alternative scalp 1R target
7. Signal source timestamp (ISO offset shown)
8. Strategy version
9. Attributed indicator checks received with the signal, bounded to512characters

Suggested template body for owner review (not submitted or approved):
BIG BEN AI PRO
{{1}} | {{2}}
Entry {{3}} | SL {{4}}
Full TP {{5}}
Alternative scalp TP {{6}}
Source time {{7}} | Strategy {{8}}
Indicator evidence: {{9}}
Choose either full or scalp; they share entry and stop. Analysis only, no broker execution.

Sending uses POST https://graph.facebook.com/{version}/{sender-id}/messages with a Bearer token in the header, never a URL query. No retries. A200response with a message ID records ACCEPTED, never DELIVERED. There is no delivery-status callback yet; delivery verification remains false. Invalid settings or missing recipient prevent requests. Provider errors are sanitized to numerical HTTP status.

Official reference: https://developers.facebook.com/documentation/business-messaging/whatsapp/overview

## Remaining owner-dependent setup
Existing Meta Business access/phone verification and an approved compatible template. If costs apply, a concrete cost approval is required under the owner's no-additional-cost instruction. Do not create accounts, templates or keys through unsupported browser automation.
