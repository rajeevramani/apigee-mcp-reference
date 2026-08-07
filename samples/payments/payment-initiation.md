---
api_id: payments
api_version: v1
document_id: payments-guide
section_id: payment-initiation
title: Payment initiation flow
content_type: text/markdown
---
# Payment initiation flow

Use the Payments API to create a payment and retrieve its latest status. The caller supplies an idempotency key so retrying a timed-out request does not create a duplicate payment.

## Sequence

```mermaid
sequenceDiagram
    participant Client
    participant Payments API
    participant Ledger
    Client->>Payments API: POST /payments
    Payments API->>Ledger: Validate and reserve funds
    Ledger-->>Payments API: Reservation confirmed
    Payments API-->>Client: 202 Accepted with payment ID
    Client->>Payments API: GET /payments/{payment_id}
    Payments API-->>Client: Current payment status
```

## Create a payment

Send `POST /payments` with an `Idempotency-Key` header and a JSON request containing the amount, currency and destination account.

```json
{
  "amount": "125.00",
  "currency": "USD",
  "destination_account": "example-account"
}
```

A successful request returns `202 Accepted`. Use the returned `payment_id` to retrieve status. A rejected request returns a problem-details response with a stable error type.
