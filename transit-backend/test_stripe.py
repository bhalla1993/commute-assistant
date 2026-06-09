#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
import os
from dotenv import load_dotenv

load_dotenv()

import stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PREMIUM_PRICE_ID = os.getenv("STRIPE_PREMIUM_PRICE_ID")

print(f"API Key configured: {bool(stripe.api_key)}")
print(f"Price ID configured: {bool(STRIPE_PREMIUM_PRICE_ID)}")
print(f"Price ID value: {STRIPE_PREMIUM_PRICE_ID}")

# Try to create a test customer
try:
    customer = stripe.Customer.create(
        email="test-checkout@example.com",
        metadata={"test": "true"}
    )
    print(f"\n✅ Customer creation successful: {customer.id}")
    
    # Try to create a checkout session
    session = stripe.checkout.Session.create(
        customer=customer.id,
        payment_method_types=["card"],
        line_items=[{"price": STRIPE_PREMIUM_PRICE_ID, "quantity": 1}],
        mode="subscription",
        success_url="http://localhost:8000/?checkout=success",
        cancel_url="http://localhost:8000/?checkout=cancel",
    )
    print(f"✅ Checkout session creation successful: {session.url}")
    
except stripe.error.InvalidRequestError as e:
    print(f"❌ Invalid request error: {e}")
    print(f"   Code: {e.code}")
    print(f"   Param: {e.param}")
except stripe.StripeError as e:
    print(f"❌ Stripe error: {e}")
except Exception as e:
    print(f"❌ Unexpected error: {type(e).__name__}: {e}")
