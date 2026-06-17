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
    path("manage/machines/add/", views.machine_create, name="machine_create"),
    # Dependent dropdown data
    path("api/machines/", views.machines_for_clinic, name="machines_for_clinic"),
]
