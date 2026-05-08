from django.conf.urls import url
from django.urls import path
from . import views
from . import views_assignment7_additions as v7

urlpatterns = [
    # ── Existing endpoints (unchanged) ────────────────────────────────────────

    # to create a new indent file
    url(r'^create_proposal/', views.createProposal, name='create-proposal'),
    url(r'^create_draft/', views.createDraft, name='create-draft'),
    url(r'^delete_indent/', views.delete_indent, name='delete-indents'),
    url(r'^view_indent/', views.getOneFiledIndent, name='view-indent'),
    path('forward_indent/<int:id>/', views.forwardIndent, name='create-indent'),
    path('user-suggestions', views.user_suggestions, name='user-suggestions'),
    url(r'^getDesignations/', views.getDesignations, name='get-designations'),

    # to get the indent files created by the user
    path('indentview/<str:username>/', views.indentView, name='indent-view'),
    path('indentview2/<str:username>/', views.indentView2, name='indent-view2'),

    # to get the indent Files drafts by a user
    path('draftview/<str:username>/', views.draftView, name='draft-view'),

    # to get all the indent files inwarded to the user
    url(r'^inwardIndents/(?P<id>\d+)$', views.inwardIndents, name='inward-indents'),

    # to see the details of a specific indent file
    url(r'^indentFile/(?P<id>\d+)$', views.indentFile, name='indent-file'),

    # to forward a indent File
    url(r'^indentFile/forward/(?P<id>\d+)$', views.ForwardIndentFile, name='forward-indent-file'),

    # STOCKS API
    url(r'^entry/(?P<id>\d+)$', views.entry, name='entry'),
    url(r'^stock_entry_view/(?P<id>\d+)$', views.stockEntryView, name='stock-entry-view'),
    url(r'^current_stock_view/(?P<id>\d+)$', views.currentStockView, name='current-stock-view'),
    url(r'^stock_entry_item_view/(?P<id>\d+)$', views.stock_entry_item_view, name='stock-entry-item-view'),
    url(r'^stock_item_delete/(?P<id>\d+)$', views.stockDelete, name='stock-delete'),
    url(r'^stock_transfer/(?P<id>\d+)$', views.stockTransfer, name='stock-transfer'),
    url(r'^perform_transfer/(?P<id>\d+)$', views.performTransfer, name='perform-transfer'),

    url(r'^archieve_indent/(?P<id>\d+)/$', views.archieve_file, name='archieve-file'),

    path('archieveview/<str:username>/', views.archieveview, name='archievedview'),
    path('outboxview2/<str:username>/', views.outboxview2, name='outboxview2'),
    path('stockEntry/<str:username>/', views.stockEntry, name='stock-entry'),
    path('my-indents/<str:username>/', views.my_indents_view, name='my-indents-view'),
    path('approve-indent/', views.approve_indent, name='approve_indent'),

    # ── Assignment 7 endpoints ─────────────────────────────────────────────────

    # T-01: Soft cancel
    path('indents/<int:indent_id>/cancel/', v7.cancel_indent, name='cancel-indent'),

    # T-02: Rejection
    path('indents/<int:indent_id>/reject/', v7.reject_indent, name='reject-indent'),

    # T-15: Duplicate detection
    path('indents/check-duplicates/', v7.check_duplicates, name='check-duplicates'),

    # T-04: GRN endpoints
    path('grn/create/', v7.create_grn, name='create-grn'),
    path('grn/<int:grn_id>/confirm/', v7.confirm_delivery, name='confirm-delivery'),
    path('grn/', v7.list_grns, name='list-grns'),

    # T-05: Product return endpoints
    path('returns/create/', v7.create_return, name='create-return'),
    path('returns/<int:return_id>/process/', v7.process_return, name='process-return'),
    path('returns/', v7.list_returns, name='list-returns'),

    # T-08: Tender management endpoints
    path('tenders/create/', v7.create_tender, name='create-tender'),
    path('tenders/<int:tender_id>/publish/', v7.publish_tender, name='publish-tender'),
    path('tenders/<int:tender_id>/bid/', v7.submit_bid, name='submit-bid'),
    path('tenders/<int:tender_id>/award/', v7.award_tender, name='award-tender'),
    path('tenders/', v7.list_tenders, name='list-tenders'),

    # T-09: Vendor management endpoints
    path('vendors/create/', v7.create_vendor, name='create-vendor'),
    path('vendors/', v7.list_vendors, name='list-vendors'),
    path('vendors/<int:vendor_id>/', v7.get_vendor, name='get-vendor'),
    path('vendors/<int:vendor_id>/update/', v7.update_vendor, name='update-vendor'),

    # T-13: Stock reservation endpoints
    path('reservations/create/', v7.create_reservation, name='create-reservation'),
    path('reservations/<int:reservation_id>/release/', v7.release_reservation, name='release-reservation'),

    # T-23: Audit log endpoint
    path('audit-logs/', v7.list_audit_logs, name='list-audit-logs'),
]