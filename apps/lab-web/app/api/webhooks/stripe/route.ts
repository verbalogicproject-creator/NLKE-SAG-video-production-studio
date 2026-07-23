import { NextResponse } from 'next/server';

// POST /api/webhooks/stripe — Stripe webhook handler.
// Signature verified via STRIPE_WEBHOOK_SECRET.
// Handled events: checkout.session.completed, invoice.paid, customer.subscription.deleted, customer.subscription.updated
export async function POST() {
  return NextResponse.json(
    {
      error: 'NotImplemented',
      message:
        'Verifies Stripe-Signature header, updates Workspace.plan + stripeCustomerId + stripeSubId.',
    },
    { status: 501 },
  );
}
