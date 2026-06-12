# Koda Changelog

## May 2026

### ✨ New Features

- **`/support` command**: Users can now reach out for help directly from the bot.
- **Smart input handling**: Koda now interprets vague or unclear messages more gracefully instead of getting confused — no more dead-end responses.
- **Dynamic user modes**: Koda adapts its response style based on how the user is engaging (grinding hard vs going quiet vs mid-slump).

### 🔧 Improvements

- **Nudge tone tuned**: Daily nudges are sharper and more context-aware — less generic, more Koda.
- **Admin alerts**: Internal alerting added for key events, making it easier to monitor bot health and user activity.
- **Onboarding polish**: Several rough edges in the onboarding flow smoothed out — cleaner conversation, better confirmations.
- **Webhook hardening**: Payment webhook handling made more robust and reliable.

---

## Late April 2026

### ✨ New Features

- **Premium via activation codes**: Users can now unlock premium access using a payment activation code — simpler flow, no redirect confusion.
- **Stripe payment flow**: Full end-to-end Stripe Checkout and webhook integration live. Pay on the landing page, bot activates automatically.
- **Per-user nudge scheduling**: Koda now sends daily check-ins at each user's preferred time, not a blanket broadcast.
- **LeetCode topic progress tracking**: Progress on specific LeetCode topics is now saved to the database and used in conversation context.
- **Onboarding nudge time**: Users can set their preferred check-in time during onboarding — Koda remembers it.
- **Admin reset command**: Admins can reset a user's onboarding state for debugging or support purposes.

### 🔧 Improvements

- **Onboarding fully revamped**: Rebuilt with an ML-based parser and intent classification — Koda now extracts profile data from natural conversation rather than rigid Q&A.
- **Onboarding completion enforcement**: Onboarding auto-completes after 8 exchanges so users don't get stuck mid-flow indefinitely.
- **Context separation**: Onboarding uses its own message history, keeping it clean from general conversation context.
- **Free message limit enforced**: Free-tier users now hit a limit, nudging upgrade to premium.
- **Railway deployment fix**: Server now correctly reads the `PORT` environment variable — deployment stability improved.

### 🐛 Fixes

- **iOS Safari landing page**: Fixed orb animation clipping on iOS Safari.
