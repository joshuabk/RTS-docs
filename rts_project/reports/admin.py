from django.contrib import admin

from .models import Department, Machine, ReturnToServiceReport


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "location")
    search_fields = ("name", "code", "location")


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "machine_type", "manufacturer", "model")
    list_filter = ("department", "machine_type")
    search_fields = ("name", "manufacturer", "model", "serial_number")


@admin.register(ReturnToServiceReport)
class ReturnToServiceReportAdmin(admin.ModelAdmin):
    list_display = (
        "reference", "machine", "status", "physics_status",
        "work_completed_at", "approved_by",
    )
    list_filter = ("status", "physics_status", "machine__department")
    search_fields = ("machine__name", "work_performed", "approved_by", "performed_by")
    readonly_fields = ("created_at", "updated_at", "approval_date")
    date_hierarchy = "work_completed_at"
