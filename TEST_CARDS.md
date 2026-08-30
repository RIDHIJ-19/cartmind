# Razorpay Test Cards

For use only in TEST MODE (`rzp_test_...` keys). No real money moves. Use with
the phone/OTP values below when Razorpay Checkout asks for them.

| # | Card Number         | Network    | CVV | Expiry          | Result                              |
|---|----------------------|------------|-----|-----------------|--------------------------------------|
| 1 | 5267 3181 8797 5449  | Mastercard | 123 | any future, e.g. 12/28 | Success (domestic)             |
| 2 | 4012 8888 8888 1881  | Visa       | 123 | any future      | Success (domestic)                  |
| 3 | 4000 0000 0000 0002  | Visa       | 123 | any future      | Declined — generic decline          |
| 4 | 4000 0000 0000 0069  | Visa       | 123 | any future      | Declined — expired card             |
| 5 | 4000 0000 0000 0119  | Visa       | 123 | any future      | Declined — processing error         |
| 6 | 5104 0600 0000 0008  | Mastercard | 123 | any future      | Success, triggers 3D-Secure/OTP step |

## Common values

- Phone: `9876543219` (avoid all-repeated digits like `9999999999`, and note `9876543210` specifically gets rejected as "invalid" too — Razorpay's validation is pickier than it looks)
- OTP: `1234`
- Name: anything

## Suggested test plan

1. Card #1 or #2 — confirm the owner ledger shows `captured`, correct amount,
   and the hover timeline shows confirmation → auth → order → checkout → captured.
2. Card #3 — confirm it lands as `failed` with a reason, not stuck on `created`.
3. Dismiss the checkout modal without entering any card — confirm that also
   reports `failed` ("Checkout closed before completing payment.").
4. Run a few of these back to back and check that Success rate, Status
   breakdown, and Volume by day on the owner console update correctly.


pay with
card number 5267318187975449, expiry 12/28, cvv 123 name = test