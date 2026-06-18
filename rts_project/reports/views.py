from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    ClinicForm,
    MachineForm,
    ReturnToServiceReportForm,
)
from .models import Department, Machine, ReturnToServiceReport
from .pdf import build_report_pdf

from django.db.models.deletion import ProtectedError
from django.urls import reverse


@login_required
def report_list(request):
    qs = ReturnToServiceReport.objects.select_related(
        "machine", "machine__department"
    )
    query = request.GET.get("q", "").strip()
    dept = request.GET.get("department", "").strip()
    status = request.GET.get("status", "").strip()

    if query:
        qs = qs.filter(
            Q(machine__name__icontains=query)
            | Q(work_performed__icontains=query)
            | Q(approved_by__icontains=query)
            | Q(performed_by__icontains=query)
        )
    if dept:
        qs = qs.filter(machine__department_id=dept)
    if status:
        qs = qs.filter(status=status)

    context = {
        "reports": qs,
        "departments": Department.objects.all(),
        "status_choices": ReturnToServiceReport.Status.choices,
        "q": query,
        "selected_department": dept,
        "selected_status": status,
        "total": ReturnToServiceReport.objects.count(),
    }
    return render(request, "reports/report_list.html", context)


@login_required
def report_detail(request, pk):
    report = get_object_or_404(
        ReturnToServiceReport.objects.select_related(
            "machine", "machine__department", "created_by"
        ),
        pk=pk,
    )
    return render(request, "reports/report_detail.html", {"report": report})


@login_required
def report_create(request):
    if request.method == "POST":
        form = ReturnToServiceReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.created_by = request.user
            report.save()
            return redirect(report)
    else:
        form = ReturnToServiceReportForm()
    return render(
        request,
        "reports/report_form.html",
        {
            "form": form,
            "title": "New return-to-service report",
            "has_machines": Machine.objects.exists(),
            "has_clinics": Department.objects.exists(),
        },
    )


@login_required
def report_edit(request, pk):
    report = get_object_or_404(ReturnToServiceReport, pk=pk)
    if request.method == "POST":
        form = ReturnToServiceReportForm(request.POST, instance=report)
        if form.is_valid():
            form.save()
            return redirect(report)
    else:
        form = ReturnToServiceReportForm(instance=report)
    return render(
        request,
        "reports/report_form.html",
        {
            "form": form,
            "title": f"Edit {report.reference}",
            "report": report,
            "has_machines": True,
            "has_clinics": True,
        },
    )


@login_required
def report_pdf(request, pk):
    report = get_object_or_404(
        ReturnToServiceReport.objects.select_related(
            "machine", "machine__department", "created_by"
        ),
        pk=pk,
    )
    buffer = build_report_pdf(report)
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{report.reference}.pdf"'
    return response


# --- Clinic & machine management (selection options) ---

@login_required
def manage(request):
    clinics = (
        Department.objects.annotate(machine_count=Count("machines"))
        .prefetch_related("machines")
        .all()
    )
    return render(
        request,
        "reports/manage.html",
        {
            "clinics": clinics,
            "clinic_form": ClinicForm(),
            "machine_form": MachineForm(),
            "has_clinics": clinics.exists(),
        },
    )


@login_required
def clinic_create(request):
    if request.method == "POST":
        form = ClinicForm(request.POST)
        if form.is_valid():
            clinic = form.save()
            messages.success(request, f"Clinic “{clinic.name}” added.")
            return redirect("reports:manage")
        # Re-render manage page with errors in the clinic form.
        return render(
            request,
            "reports/manage.html",
            {
                "clinics": Department.objects.annotate(
                    machine_count=Count("machines")
                ).prefetch_related("machines"),
                "clinic_form": form,
                "machine_form": MachineForm(),
                "open_form": "clinic",
                "has_clinics": Department.objects.exists(),
            },
        )
    return redirect("reports:manage")

@login_required
def clinic_edit(request, pk):
    clinic = get_object_or_404(Department, pk=pk)
    if request.method == "POST":
        form = ClinicForm(request.POST, instance=clinic)
        if form.is_valid():
            form.save()
            messages.success(request, f"Clinic “{clinic.name}” updated.")
            return redirect("reports:manage")
    else:
        form = ClinicForm(instance=clinic)
    return render(
        request,
        "reports/object_form.html",
        {"form": form, "kind": "clinic", "title": f"Edit clinic — {clinic.name}"},
    )


@login_required
def clinic_delete(request, pk):
    clinic = get_object_or_404(Department, pk=pk)
    machine_count = clinic.machines.count()
    if request.method == "POST":
        if machine_count:
            messages.error(
                request,
                f"Can’t delete “{clinic.name}” — it still has {machine_count} "
                f"machine{'s' if machine_count != 1 else ''}. Delete or reassign them first.",
            )
            return redirect("reports:manage")
        name = clinic.name
        try:
            clinic.delete()
            messages.success(request, f"Clinic “{name}” deleted.")
        except ProtectedError:
            messages.error(request, f"Can’t delete “{name}” — other records depend on it.")
        return redirect("reports:manage")

    blocked_reason = ""
    if machine_count:
        blocked_reason = (
            f"This clinic still has {machine_count} "
            f"machine{'s' if machine_count != 1 else ''}. "
            "Delete or reassign its machines before removing the clinic."
        )
    return render(
        request,
        "reports/confirm_delete.html",
        {
            "kind": "clinic",
            "object_name": clinic.name,
            "detail": clinic.location,
            "blocked_reason": blocked_reason,
            "action_url": reverse("reports:clinic_delete", args=[clinic.pk]),
        },
    )




@login_required
def machine_create(request):
    if request.method == "POST":
        form = MachineForm(request.POST)
        if form.is_valid():
            machine = form.save()
            messages.success(
                request, f"Machine “{machine.name}” added to {machine.department.name}."
            )
            return redirect("reports:manage")
        return render(
            request,
            "reports/manage.html",
            {
                "clinics": Department.objects.annotate(
                    machine_count=Count("machines")
                ).prefetch_related("machines"),
                "clinic_form": ClinicForm(),
                "machine_form": form,
                "open_form": "machine",
                "has_clinics": Department.objects.exists(),
            },
        )
    return redirect("reports:manage")

@login_required
def machine_edit(request, pk):
    machine = get_object_or_404(Machine, pk=pk)
    if request.method == "POST":
        form = MachineForm(request.POST, instance=machine)
        if form.is_valid():
            form.save()
            messages.success(request, f"Machine “{machine.name}” updated.")
            return redirect("reports:manage")
    else:
        form = MachineForm(instance=machine)
    return render(
        request,
        "reports/object_form.html",
        {"form": form, "kind": "machine", "title": f"Edit machine — {machine.name}"},
    )


@login_required
def machine_delete(request, pk):
    machine = get_object_or_404(Machine, pk=pk)
    report_count = machine.rts_reports.count()
    if request.method == "POST":
        if report_count:
            messages.error(
                request,
                f"Can’t delete “{machine.name}” — it is used by {report_count} "
                f"report{'s' if report_count != 1 else ''}. Those records must be kept.",
            )
            return redirect("reports:manage")
        name = machine.name
        try:
            machine.delete()
            messages.success(request, f"Machine “{name}” deleted.")
        except ProtectedError:
            messages.error(request, f"Can’t delete “{name}” — other records depend on it.")
        return redirect("reports:manage")

    blocked_reason = ""
    if report_count:
        blocked_reason = (
            f"This machine is referenced by {report_count} "
            f"return-to-service report{'s' if report_count != 1 else ''}, "
            "which must be preserved. It can’t be deleted."
        )
    return render(
        request,
        "reports/confirm_delete.html",
        {
            "kind": "machine",
            "object_name": machine.name,
            "detail": machine.department.name,
            "blocked_reason": blocked_reason,
            "action_url": reverse("reports:machine_delete", args=[machine.pk]),
        },
    )


@login_required
def machines_for_clinic(request):
    """JSON: machines belonging to a clinic, for the dependent dropdown."""
    clinic_id = request.GET.get("clinic")
    machines = []
    if clinic_id:
        machines = list(
            Machine.objects.filter(department_id=clinic_id)
            .order_by("name")
            .values("id", "name")
        )
    return JsonResponse({"machines": machines})
