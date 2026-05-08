from django.core.management.base import BaseCommand

from psmodule.department_stock.models import Stock


class Command(BaseCommand):
    help = "Seed dummy stock data for the department_stock module."

    def handle(self, *args, **options):
        dummy_data = [
            {"stock_name": "Laptop", "department": "dep_cse", "quantity": 25},
            {"stock_name": "Projector", "department": "dep_ece", "quantity": 18},
            {"stock_name": "Router", "department": "dep_ece", "quantity": 20},
        ]

        for item in dummy_data:
            stock, created = Stock.objects.get_or_create(
                stock_name=item["stock_name"],
                department=item["department"],
                defaults={"quantity": item["quantity"]},
            )
            if not created and stock.quantity != item["quantity"]:
                stock.quantity = item["quantity"]
                stock.save(update_fields=["quantity"])
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created {stock.stock_name} ({stock.department})"))
            else:
                self.stdout.write(self.style.NOTICE(f"Already exists: {stock.stock_name} ({stock.department})"))

        self.stdout.write(self.style.SUCCESS("Department stock dummy data seeded."))
