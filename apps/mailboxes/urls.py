from django.urls import path
from . import views

app_name = 'mailboxes'

urlpatterns = [
    # Categories
    path('categories/', views.category_list, name='category_list'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    
    # Email Addresses
    path('addresses/', views.address_list, name='address_list'),
    path('addresses/create/', views.address_create, name='address_create'),
    path('addresses/generate-random/', views.address_generate_api, name='address_generate_random'),
    path('addresses/<int:pk>/', views.address_detail, name='address_detail'),
    path('addresses/<int:pk>/toggle/', views.address_toggle, name='address_toggle'),
    path('addresses/<int:pk>/move/', views.address_move, name='address_move'),
    path('addresses/<int:pk>/delete/', views.address_delete, name='address_delete'),

    # Inbox & Email Viewer
    path('inbox/', views.inbox_list, name='inbox'),
    path('inbox/<int:pk>/', views.email_detail, name='email_detail'),
    path('inbox/<int:pk>/html/', views.email_html_raw, name='email_html_raw'),
    path('inbox/<int:pk>/toggle-read/', views.email_toggle_read, name='email_toggle_read'),
    path('inbox/<int:pk>/delete/', views.email_delete, name='email_delete'),
    path('inbox/bulk/', views.email_bulk_action, name='email_bulk_action'),
]
