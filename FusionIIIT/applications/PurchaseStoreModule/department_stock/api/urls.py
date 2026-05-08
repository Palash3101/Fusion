from django.urls import path

from psmodule.department_stock.api import views

urlpatterns = [
    path("stock/", views.StockListView.as_view(), name="stock_list"),
    path("stock/available/", views.AvailableStockListView.as_view(), name="stock_available"),
    path("request/", views.TransferRequestListCreateView.as_view(), name="transfer_request_list_create"),
    path("requests/", views.TransferRequestListCreateView.as_view(), name="transfer_request_list_create_alias"),
    path(
        "request/<int:pk>/approve/",
        views.TransferRequestApproveView.as_view(),
        name="transfer_request_approve",
    ),
    path(
        "request/<int:pk>/reject/",
        views.TransferRequestRejectView.as_view(),
        name="transfer_request_reject",
    ),
]
