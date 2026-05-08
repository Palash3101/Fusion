from django.http import HttpResponseForbidden
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from psmodule.department_stock.api.serializers import (
    StockSerializer,
    TransferRequestCreateSerializer,
    TransferRequestSerializer,
)
from psmodule.department_stock.services import (
    approve_transfer_request,
    available_stock_queryset_for_request,
    create_transfer_request_record,
    department_stock_queryset_for_request,
    reject_transfer_request,
    transfer_request_list_queryset,
)


class StockListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stock_qs = department_stock_queryset_for_request(request)
        if isinstance(stock_qs, HttpResponseForbidden):
            return stock_qs
        serializer = StockSerializer(stock_qs, many=True)
        return Response(serializer.data)


class AvailableStockListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stock_qs = available_stock_queryset_for_request(request)
        if isinstance(stock_qs, HttpResponseForbidden):
            return stock_qs
        serializer = StockSerializer(stock_qs, many=True)
        return Response(serializer.data)


class TransferRequestListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        requests_qs = transfer_request_list_queryset(request)
        if requests_qs is None:
            return HttpResponseForbidden("Access Denied")

        serializer = TransferRequestSerializer(requests_qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = TransferRequestCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        result = create_transfer_request_record(
            request,
            stock_id=serializer.validated_data["stock_id"],
            requested_from=serializer.validated_data["requested_from"],
            requested_quantity=serializer.validated_data.get("requested_quantity", 1),
        )
        if isinstance(result, HttpResponseForbidden):
            return result

        response_serializer = TransferRequestSerializer(result)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class TransferRequestApproveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        result = approve_transfer_request(request, pk)
        if isinstance(result, HttpResponseForbidden):
            return result
        if isinstance(result, tuple):
            return Response(result[0], status=result[1])

        serializer = TransferRequestSerializer(result)
        return Response(serializer.data)


class TransferRequestRejectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        result = reject_transfer_request(request, pk)
        if isinstance(result, HttpResponseForbidden):
            return result
        if isinstance(result, tuple):
            return Response(result[0], status=result[1])

        serializer = TransferRequestSerializer(result)
        return Response(serializer.data)
