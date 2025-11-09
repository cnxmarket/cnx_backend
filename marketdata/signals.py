from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserAccount
from marketdata.models import LedgerEntry, UserAccount
from decimal import Decimal
from django.db import transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver


REALIZED_KINDS = {"realized_pnl", "pnl", "realized"}
@receiver(post_save, sender=User)
def create_user_account(sender, instance, created, **kwargs):
    if created:
        UserAccount.objects.create(user=instance)

# @receiver(post_save, sender=User)
# def save_user_account(sender, instance, **kwargs):
#     try:
#         if hasattr(instance, 'account'):
#             instance.account.save()
#     except UserAccount.DoesNotExist:
#         # Account doesn't exist yet, ignore or log
#         pass


def _effect_on_balance(entry: LedgerEntry) -> Decimal:
    """
    Return the signed delta that this ledger entry applied to balance
    when it was created.
    """
    kind = (entry.kind or "").lower().strip()
    amt = Decimal(str(entry.amount or "0"))

    if kind in ("realized_pnl", "adj"):
        # stored signed: +profit / -loss / ±manual adj
        return amt
    if kind == "deposit":
        # deposits increase balance (amount should be +)
        return amt
    if kind == "withdrawal":
        # withdrawals decrease balance (amount should be +)
        return -amt
    if kind == "fee":
        # fees decrease balance (amount should be +)
        return -amt

    # default: treat as signed amount
    return amt


@receiver(pre_delete, sender=LedgerEntry)
def reverse_balance_on_ledger_delete(sender, instance: LedgerEntry, using, **kwargs):
    """
    Reverse the original ledger effect when a row is deleted.

    balance = balance - effect(entry)
    - If realized_pnl = +20  → effect=+20 → balance -= 20
    - If realized_pnl = -20  → effect=-20 → balance -= (-20) = +20
    - If deposit amount=100  → effect=+100 → balance -= 100 (delete removes deposit)
    - If withdrawal amount=50 → effect=-50 → balance -= (-50) = +50 (refunded)
    - If fee amount=7        → effect=-7  → balance -= (-7) = +7 (fee undone)
    """
    # If there is no linked user, nothing to do
    user_id = getattr(instance, "user_id", None)
    if not user_id:
        return

    delta = _effect_on_balance(instance)
    if delta == 0:
        return

    db_alias = using or "default"
    with transaction.atomic(using=db_alias):
        # Lock the row to prevent races with other balance updates
        ua = (
            UserAccount.objects
            .select_for_update()
            .using(db_alias)
            .get(user_id=user_id)
        )
        ua.balance = (ua.balance or Decimal("0")) - delta
        # If you want strict rounding to 4dp:
        # ua.balance = ua.balance.quantize(Decimal("0.0001"))
        ua.save(update_fields=["balance"])
