from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from decimal import Decimal
from marketdata.models import UserAccount

class Command(BaseCommand):
    help = "Add capital to a user"

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Username of the user")
        parser.add_argument("amount", type=str, help="Amount of capital to add")

    def handle(self, *args, **kwargs):
        username = kwargs["username"]
        amount = Decimal(kwargs["amount"])

        user = User.objects.get(username=username)
        account, _ = UserAccount.objects.get_or_create(user=user)
        account.balance += amount
        account.save()
        self.stdout.write(self.style.SUCCESS(f"Added {amount} capital to user {username}"))
