import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.db.models.financial_transaction import FinancialTransaction


class FinancialTransactionResponse(BaseModel):
    id: uuid.UUID
    transaction_type: str
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    reference_type: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, transaction: FinancialTransaction) -> "FinancialTransactionResponse":
        return cls(
            id=transaction.id,
            transaction_type=transaction.transaction_type,
            amount=transaction.amount,
            balance_before=transaction.balance_before,
            balance_after=transaction.balance_after,
            reference_type=transaction.reference_type,
            created_at=transaction.created_at,
        )
