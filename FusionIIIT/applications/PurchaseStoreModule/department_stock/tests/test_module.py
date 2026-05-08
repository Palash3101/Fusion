from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from psmodule.department_stock.api.views import StockListView
from psmodule.department_stock.models import Stock


class DepartmentStockAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.depadmin_user = User.objects.create_user(username="depadmin_cse", password="pass1234")
        self.depadmin_user.role = "depadmin_cse"
        self.non_depadmin_user = User.objects.create_user(username="employee", password="pass1234")
        self.non_depadmin_user.role = "employee"

        Stock.objects.create(stock_name="Laptop", department="dep_cse")
        Stock.objects.create(stock_name="Printer", department="dep_ece")

        self.factory = APIRequestFactory()

    def test_depadmin_can_list_own_department_stock(self):
        request = self.factory.get("/ps/api/stock/")
        force_authenticate(request, user=self.depadmin_user)

        response = StockListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["stock_name"], "Laptop")

    def test_non_depadmin_is_forbidden(self):
        request = self.factory.get("/ps/api/stock/")
        force_authenticate(request, user=self.non_depadmin_user)

        response = StockListView.as_view()(request)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.content.decode(), "Access Denied")
