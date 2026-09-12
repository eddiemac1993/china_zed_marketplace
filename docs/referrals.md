# Referral rewards

Signed-in customers share products using the share button or WhatsApp button. Each link carries a signed product/referrer token. The most recent valid referral for a product is stored in the buyer's browser session for up to 30 days; clearing cookies or switching browsers loses attribution. The buyer must order that product. Self-referrals are ignored.

Both cart checkout and single-product checkout save the referrer on each order item. The reward is 5% of the actual item line total (quantity × purchased unit price, including wholesale discounts), rounded to two decimal places. Delivery fees are excluded. Existing orders are not retrospectively attributed.

Rewards remain pending until the order is `successful`, `deposit_confirmed` and `balance_paid`. Unavailable items, cancellations, deleted orders and refunds do not qualify. The successful state is the site's existing completed-delivery/collection state. Changing order or item records through their normal `save()` workflows synchronizes rewards. Do not use bulk `QuerySet.update()` for completion or refund changes, since that bypasses Django signals.

## Month-end payments

1. Open **Admin → Referral rewards**, filter status to **Awaiting month-end payment**, and review the payout due date and recipient.
2. Arrange and send payment outside the app using the agreed payment method. The app does not send bank or mobile-money transfers.
3. Enter the external transaction reference on each reward covered by that payment.
4. Select those entries and run **Record completed month-end payments (reference required)**. Only eligible entries due on or before today can be marked paid. The app records the administrator, date and transaction reference. Repeated actions cannot pay the same ledger entry twice.

Paid entries are immutable payment history. If a paid order is later cancelled or refunded, review recovery manually; the app does not silently remove completed payments or debit another reward.

Customers see pending, earned/unpaid and paid totals plus their latest 30 reward entries on `/profile/#referral-earnings`. No buyer identity or contact information is shown to the referrer.

## Deployment

Run `python manage.py migrate` and `python manage.py collectstatic --noinput`, then reload the production application. Migration `0053_orderitem_referrer_referralreward` adds the ledger and attribution field. Versioned icon URLs and service-worker cache `chinazed-app-v4-logo-20260912` update the supplied logo. Existing installed apps may require reopening or reinstalling to refresh OS-cached icons.

Tests: `python manage.py test core.tests.test_referrals core.tests.test_variants`
