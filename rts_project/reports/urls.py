from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_list, name="list"),
    path("new/", views.report_create, name="create"),
    path("<int:pk>/", views.report_detail, name="detail"),
    path("<int:pk>/edit/", views.report_edit, name="edit"),
    path("<int:pk>/pdf/", views.report_pdf, name="pdf"),
    # Clinic & machine management
    path("manage/", views.manage, name="manage"),
    path("manage/clinics/add/", views.clinic_create, name="clinic_create"),
    path("manage/clinics/<int:pk>/edit/", views.clinic_edit, name="clinic_edit"),
    path("manage/clinics/<int:pk>/delete/", views.clinic_delete, name="clinic_delete"),
    path("manage/machines/add/", views.machine_create, name="machine_create"),
    path("manage/machines/<int:pk>/edit/", views.machine_edit, name="machine_edit"),
    path("manage/machines/<int:pk>/delete/", views.machine_delete, name="machine_delete"),
    # Dependent dropdown data
    path("api/machines/", views.machines_for_clinic, name="machines_for_clinic"),
]
